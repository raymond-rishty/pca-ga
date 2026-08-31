#!/usr/bin/env python3
"""Resolve canonical source metadata for extracted PCA corpus pages.

The registry is the durable identity layer.  This module is intentionally a
small resolver: it turns a known source identity plus a PDF page into the
metadata consumed by Markdown generators and the Jekyll templates.  It does
not discover or guess sources.
"""
from __future__ import annotations

import bisect
import json
import re
from pathlib import Path
from typing import Any

VOLUME_RE = re.compile(r"^ga(?P<ga>\d+)[_-](?P<year>\d{4})$")
PAGE_MARKER_RE = re.compile(
    r"<!--\s*PAGE\s+ga=(?P<ga>\d+)\s+pdf_page=(?P<pdf>\d+)(?P<rest>[^>]*)-->"
)
PRINTED_PAGE_RE = re.compile(r"\bprinted_page=(?P<page>[A-Za-z0-9.-]+)")
ANCHOR_RE = re.compile(r'<a\s+id="(?P<anchor>ga\d+-p[^"]+)"')
MINUTES_LINK_RE = re.compile(
    r"\[(?P<label>[^\]\n]+)\]\((?P<prefix>(?:\.\./)+)markdown/"
    r"(?P<volume>ga\d+_\d{4})\.md"
    r"(?:#(?P<anchor>ga\d+-p[A-Za-z0-9.-]+))?\)"
)
LINE_SPAN_RE = re.compile(r"(?i)\blines\s+(?P<start>\d+)[–-](?P<end>\d+)")
PRINTED_LABEL_RE = re.compile(r"(?i)\bpp?\.\s*(?P<page>\d+)")
MARKDOWN_PDF_RE = re.compile(r"\]\((?P<url>https?://[^)\s]+\.pdf(?:[?#][^)\s]*)?)\)", re.I)

_REGISTRY_CACHE: dict[str, dict[str, Any]] = {}
_PAGE_MAP_CACHE: dict[tuple[str, str], dict[str, int]] = {}
_PDF_MARKERS_CACHE: dict[tuple[str, str], list[tuple[int, int]]] = {}


def ordinal_suffix(value: int) -> str:
    if 10 <= value % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")


def volume_parts(volume: str) -> tuple[int, int]:
    match = VOLUME_RE.fullmatch(volume)
    if not match:
        raise ValueError(f"Not a minutes volume slug: {volume!r}")
    return int(match.group("ga")), int(match.group("year"))


def minutes_pdf_filename(volume: str) -> str:
    ga, year = volume_parts(volume)
    return f"{ga}{ordinal_suffix(ga)}_pcaga_{year}.pdf"


def minutes_pdf_url(volume: str, pdf_page: int | None = None) -> str:
    url = f"https://www.pcahistory.org/pca/ga/{minutes_pdf_filename(volume)}"
    return f"{url}#page={int(pdf_page)}" if pdf_page is not None else url


def normalize_anchor(anchor: str) -> str:
    match = re.fullmatch(r"ga0*(\d+)-p(.+)", anchor)
    if not match:
        return anchor
    return f"ga{int(match.group(1))}-p{match.group(2)}"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")


def fallback_source_id(url: str, kind: str = "dedicated") -> str:
    """Return a deterministic ID when a temporary/test root has no registry."""
    clean = url.split("#", 1)[0].split("?", 1)[0]
    basename = clean.rstrip("/").rsplit("/", 1)[-1]
    basename = re.sub(r"\.pdf$", "", basename, flags=re.I)
    return f"{kind}-pdf:{_slug(basename) or 'unknown'}"


def load_registry(root: Path) -> dict[str, Any]:
    key = str(root.resolve())
    if key in _REGISTRY_CACHE:
        return _REGISTRY_CACHE[key]
    path = root / "index" / "source_registry.json"
    if not path.exists():
        registry: dict[str, Any] = {"sources": [], "record_sources": {}}
    else:
        registry = json.loads(path.read_text(encoding="utf-8"))
    _REGISTRY_CACHE[key] = registry
    return registry


def _source_index(root: Path) -> dict[str, dict[str, Any]]:
    return {
        item["source_id"]: item
        for item in load_registry(root).get("sources", [])
        if item.get("source_id")
    }


def source_id_for_url(root: Path, url: str, kind: str = "dedicated") -> str:
    clean = url.split("#", 1)[0].split("?", 1)[0]
    for source in load_registry(root).get("sources", []):
        if source.get("url", "").split("#", 1)[0].split("?", 1)[0] == clean:
            return source["source_id"]
    return fallback_source_id(clean, kind)


def source_record(root: Path, source_id: str) -> dict[str, Any] | None:
    return _source_index(root).get(source_id)


def record_source_ids(root: Path, record_type: str, record_id: str | int) -> list[str]:
    registry = load_registry(root)
    mapping = registry.get("record_sources", {})
    candidates = [f"{record_type}:{record_id}", str(record_id)]
    if record_type == "case":
        number = re.search(r"\d{2,4}-\d{1,3}", str(record_id))
        if number:
            raw_year, raw_n = number.group(0).split("-", 1)
            year = raw_year
            if len(year) == 2:
                year = ("19" if int(year) >= 70 else "20") + year
            candidates.insert(0, f"case:{year}-{int(raw_n)}")
    for candidate in candidates:
        values = mapping.get(candidate)
        if values:
            return list(dict.fromkeys(values))
    return []


def _pdf_markers(root: Path, volume: str) -> list[tuple[int, int]]:
    cache_key = (str(root.resolve()), volume)
    if cache_key in _PDF_MARKERS_CACHE:
        return _PDF_MARKERS_CACHE[cache_key]

    path = root / "markdown" / f"{volume}.md"
    if not path.exists():
        _PDF_MARKERS_CACHE[cache_key] = []
        return _PDF_MARKERS_CACHE[cache_key]

    markers = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        marker = PAGE_MARKER_RE.search(line)
        if marker:
            markers.append((number, int(marker.group("pdf"))))
    _PDF_MARKERS_CACHE[cache_key] = markers
    return markers


def _page_map(root: Path, volume: str) -> dict[str, int]:
    """Map rendered minutes anchors (gaN-pPRINTED) to PDF page numbers.

    A printed folio can recur later in an appendix.  An extracted page's
    existing ``#gaN-pPRINTED`` source link refers to the first matching body
    location, so retain the first coordinate rather than allowing a later
    duplicate to overwrite it.
    """
    cache_key = (str(root.resolve()), volume)
    if cache_key in _PAGE_MAP_CACHE:
        return _PAGE_MAP_CACHE[cache_key]

    path = root / "markdown" / f"{volume}.md"
    if not path.exists():
        _PAGE_MAP_CACHE[cache_key] = {}
        return _PAGE_MAP_CACHE[cache_key]

    mapping: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = PAGE_MARKER_RE.search(line)
        if marker:
            pdf_page = int(marker.group("pdf"))
            printed = PRINTED_PAGE_RE.search(marker.group("rest"))
            if printed:
                mapping.setdefault(
                    f"ga{int(marker.group('ga'))}-p{printed.group('page')}",
                    pdf_page,
                )

        for anchor in ANCHOR_RE.finditer(line):
            if marker:
                mapping.setdefault(
                    normalize_anchor(anchor.group("anchor")),
                    int(marker.group("pdf")),
                )

    _PAGE_MAP_CACHE[cache_key] = mapping
    return mapping


def first_marked_pdf_page(text: str) -> int | None:
    match = PAGE_MARKER_RE.search(text)
    return int(match.group("pdf")) if match else None


def pdf_page_for_anchor(root: Path, volume: str, anchor: str) -> int | None:
    return _page_map(root, volume).get(normalize_anchor(anchor))


def pdf_page_for_printed(root: Path, volume: str, printed_page: str) -> int | None:
    ga, _ = volume_parts(volume)
    return _page_map(root, volume).get(f"ga{ga}-p{printed_page}")


def line_to_pdf_page(root: Path, volume: str, line_number: int) -> int | None:
    markers = _pdf_markers(root, volume)
    if not markers:
        return None
    index = bisect.bisect_right([number for number, _ in markers], int(line_number)) - 1
    return markers[index][1] if index >= 0 else markers[0][1]


def _yaml_quote(value: Any) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _entry_from_source(root: Path, source_id: str, pdf_page: int | None = None,
                       label: str | None = None) -> dict[str, Any] | None:
    source = source_record(root, source_id)
    if source is None:
        if source_id.startswith("minutes:"):
            volume = source_id.split(":", 1)[1]
            source = {
                "source_id": source_id,
                "kind": "minutes",
                "volume": volume,
                "pdf_path": f"pca/ga/{minutes_pdf_filename(volume)}",
                "url": minutes_pdf_url(volume),
            }
        else:
            return None
    kind = source.get("kind")
    if kind == "minutes":
        volume = source.get("volume") or source_id.split(":", 1)[-1]
        page = int(pdf_page) if pdf_page is not None else None
        return {
            "type": "minutes",
            "source_id": source_id,
            "label": label or (f"Minutes PDF · p. {page}" if page is not None else "Minutes PDF"),
            "file": source.get("pdf_path", "").rsplit("/", 1)[-1] or minutes_pdf_filename(volume),
            "volume": volume,
            "pdf_page": page,
            "url": minutes_pdf_url(volume, page),
        }
    url = source.get("url")
    if not url:
        return None
    return {
        "type": "dedicated",
        "source_id": source_id,
        "label": label or "Dedicated source PDF",
        "file": source.get("pdf_path", "").rsplit("/", 1)[-1] or url.rsplit("/", 1)[-1],
        "url": url,
    }


def minutes_source_entry(root: Path, volume: str, pdf_page: int | None) -> dict[str, Any] | None:
    if not volume or pdf_page is None:
        return None
    return _entry_from_source(root, f"minutes:{volume}", int(pdf_page))


def source_entries_for_record(
    root: Path,
    record_type: str,
    record_id: str | int,
    volume: str | None = None,
    pdf_page: int | None = None,
    dedicated_url: str | None = None,
) -> list[dict[str, Any]]:
    """Return dedicated sources first, then the known minutes fallback."""
    ids = record_source_ids(root, record_type, record_id)
    if dedicated_url:
        ids.insert(0, source_id_for_url(root, dedicated_url))
    entries: list[dict[str, Any]] = []
    for source_id in ids:
        page = pdf_page if source_id.startswith("minutes:") else None
        entry = _entry_from_source(root, source_id, page)
        if entry and entry["source_id"] not in {x["source_id"] for x in entries}:
            entries.append(entry)
    if volume and pdf_page is not None:
        entry = minutes_source_entry(root, volume, int(pdf_page))
        if entry and entry["source_id"] not in {x["source_id"] for x in entries}:
            entries.append(entry)
    return entries


def source_front_matter(entries: list[dict[str, Any]]) -> list[str]:
    """Return YAML front-matter lines for normalized source-link entries."""
    if not entries:
        return []
    lines = ["---", "source_links:"]
    for entry in entries:
        lines.append(f"  - type: {_yaml_quote(entry['type'])}")
        lines.append(f"    source_id: {_yaml_quote(entry['source_id'])}")
        lines.append(f"    label: {_yaml_quote(entry['label'])}")
        if entry.get("file"):
            lines.append(f"    file: {_yaml_quote(entry['file'])}")
        if entry.get("volume"):
            lines.append(f"    volume: {_yaml_quote(entry['volume'])}")
        if entry.get("pdf_page") is not None:
            lines.append(f"    pdf_page: {int(entry['pdf_page'])}")
        if entry.get("url"):
            lines.append(f"    url: {_yaml_quote(entry['url'])}")
    lines += ["---", ""]
    return lines


def extract_source_links(root: Path, text: str) -> list[dict[str, Any]]:
    """Extract explicit source links and verified minutes page locations."""
    entries: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for match in MARKDOWN_PDF_RE.finditer(text):
        url = match.group("url")
        source_id = source_id_for_url(root, url)
        key = ("dedicated", source_id)
        if key in seen:
            continue
        seen.add(key)
        source = source_record(root, source_id) or {}
        entries.append({
            "type": "dedicated",
            "source_id": source_id,
            "label": "Dedicated source PDF",
            "file": source.get("pdf_path", "").rsplit("/", 1)[-1] or url.rsplit("/", 1)[-1],
            "url": url,
        })

    minutes_matches = list(MINUTES_LINK_RE.finditer(text))
    if minutes_matches:
        for match in minutes_matches:
            volume = match.group("volume")
            anchor = match.group("anchor")
            if anchor:
                pdf_page = pdf_page_for_anchor(root, volume, anchor)
                if pdf_page is None:
                    printed = re.search(r"-p(?P<page>[A-Za-z0-9.-]+)$", anchor)
                    if printed:
                        pdf_page = pdf_page_for_printed(root, volume, printed.group("page"))
            else:
                label = match.group("label")
                span = LINE_SPAN_RE.search(label)
                printed = PRINTED_LABEL_RE.search(label)
                pdf_page = (
                    line_to_pdf_page(root, volume, int(span.group("start")))
                    if span
                    else pdf_page_for_printed(root, volume, printed.group("page"))
                    if printed
                    else first_marked_pdf_page(text)
                )
            if pdf_page is None:
                continue
            source_id = f"minutes:{volume}"
            key = ("minutes", source_id, pdf_page)
            if key in seen:
                continue
            seen.add(key)
            entries.append({
                "type": "minutes",
                "source_id": source_id,
                "label": f"Minutes PDF · p. {pdf_page}",
                "file": minutes_pdf_filename(volume),
                "volume": volume,
                "pdf_page": pdf_page,
                "url": minutes_pdf_url(volume, pdf_page),
            })
    elif first_marked_pdf_page(text) is not None:
        marker = PAGE_MARKER_RE.search(text)
        assert marker is not None
        try:
            year = _volume_year_from_text(text)
        except ValueError:
            return entries
        volume = f"ga{int(marker.group('ga'))}_{year}"
        pdf_page = int(marker.group("pdf"))
        source_id = f"minutes:{volume}"
        key = ("minutes", source_id, pdf_page)
        if key not in seen:
            entries.append({
                "type": "minutes",
                "source_id": source_id,
                "label": f"Minutes PDF · p. {pdf_page}",
                "file": minutes_pdf_filename(volume),
                "volume": volume,
                "pdf_page": pdf_page,
                "url": minutes_pdf_url(volume, pdf_page),
            })

    return entries


def _volume_year_from_text(text: str) -> int:
    year = re.search(
        r"(?i)(?:assembly|general assembly)[^\n]{0,40}\((?P<year>(?:19|20)\d{2})\)",
        text,
    ) or re.search(r"\b(?:19|20)\d{2}\b", text)
    if not year:
        raise ValueError("Cannot determine minutes volume year from extracted page")
    return int(year.groupdict().get("year") or year.group(0))


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for entry in entries:
        key = (entry.get("source_id"), entry.get("pdf_page"), entry.get("url"))
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def source_entries_for_path(root: Path, path: Path, text: str) -> list[dict[str, Any]]:
    """Resolve explicit links and registry sources for a committed page path."""
    entries = extract_source_links(root, text)
    if not entries:
        legacy = re.search(
            r'(?i)file:\s*["\'](?P<file>\d+)(?:st|nd|rd|th)_pcaga_(?P<year>\d{4})\.pdf',
            text,
        )
        if legacy:
            volume = f"ga{int(legacy.group('file'))}_{legacy.group('year')}"
            page_match = re.search(r"(?im)^\s*(?:pdf_page|page):\s*(\d+)", text)
            page = int(page_match.group(1)) if page_match else None
            entry = minutes_source_entry(root, volume, page)
            if entry:
                entries.append(entry)
    if path.parent.name == "cases":
        match = re.search(r"(?<!\d)((?:19|20)\d{2}-\d{1,3})(?!\d)", path.stem)
        if match:
            minutes = next((entry for entry in entries if entry.get("type") == "minutes"), None)
            volume = minutes.get("volume") if minutes else None
            pdf_page = minutes.get("pdf_page") if minutes else None
            inferred = source_entries_for_record(
                root, "case", match.group(1), volume, pdf_page
            )
            entries = inferred + entries
    return _dedupe_entries(entries)


def _replace_source_front_matter(text: str, entries: list[dict[str, Any]]) -> str:
    front_end = text.find("\n---\n", 4)
    if front_end < 0:
        return "\n".join(source_front_matter(entries)) + text

    existing_lines = text[:front_end].splitlines()
    kept: list[str] = []
    skipping = False
    for line in existing_lines:
        if not skipping and line.strip() == "source_links:":
            skipping = True
            continue
        if skipping:
            if line.startswith("  ") or not line.strip():
                continue
            skipping = False
        if not skipping:
            kept.append(line)
    new_front = kept + source_front_matter(entries)[1:-2]
    return "\n".join(new_front) + "\n---\n" + text[front_end + 5:]


def normalize_text(root: Path, text: str, path: Path | None = None) -> tuple[str, bool]:
    """Add or refresh source_links front matter while preserving page content."""
    entries = source_entries_for_path(root, path or Path(), text)
    if not entries:
        return text, False

    if re.search(r"(?m)^source_links:\s*$", text):
        if all(str(entry.get("source_id")) in text for entry in entries):
            return text, False
        return _replace_source_front_matter(text, entries), True

    front = "\n".join(source_front_matter(entries))
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            return text[:end] + "\n" + "\n".join(source_front_matter(entries)[1:-2]) + text[end:], True

    return front + text, True

def extracted_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in ("cases", "inquiries", "overtures", "studies"):
        paths.extend(sorted((root / directory).glob("*.md")))
    paths.extend(sorted((root / "rpr").glob("*.md")))
    paths.extend(sorted((root / "rpr" / "exc").glob("*.md")))
    return paths


def run(root: Path, check: bool = False) -> int:
    changed: list[Path] = []
    for path in extracted_paths(root):
        original = path.read_text(encoding="utf-8")
        normalized, did_change = normalize_text(root, original, path)
        if not did_change:
            continue
        changed.append(path)
        if not check:
            path.write_text(normalized, encoding="utf-8")

    if changed:
        action = "would add" if check else "added"
        print(f"{action} source-PDF metadata to {len(changed)} extracted pages")
        for path in changed[:20]:
            print(f"  {path.relative_to(root)}")
        if len(changed) > 20:
            print(f"  ... and {len(changed) - 20} more")
        return 1 if check else 0

    print("All extracted pages already have source-PDF metadata or no resolved source")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.root, args.check))
