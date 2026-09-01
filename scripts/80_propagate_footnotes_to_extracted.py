"""Propagate materialized footnotes from minutes into extracted documents.

The published ``markdown/`` volumes are authoritative.  This pass carries
only footnotes that are already present in those volumes into page-backed
documents under ``cases/``, ``cases-rebuilt/``, ``inquiries/``, and
``studies/``.  It reuses the scan report's marker/context witnesses, so a
number is never replaced merely because it happens to occur in an extracted
document.

The default is a dry run.  Use ``--apply`` after reviewing the JSON report::

    python scripts/80_propagate_footnotes_to_extracted.py \
      --report ocr-bakeoff/reports/footnote_scan_ga14_v3.json \
      --report ocr-bakeoff/reports/footnote_scan_all_52_scoped_review_v3.json \
      --gold ocr-bakeoff/benchmark/footnote_gold_marker_sample.json \
      --apply
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location(
    "footnote_application", ROOT / "scripts" / "79_apply_footnotes.py"
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError("could not load footnote application module")
FOOTNOTES = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = FOOTNOTES
MODULE_SPEC.loader.exec_module(FOOTNOTES)


def load_reports(paths: list[Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reports.extend(payload.get("reports", [payload]))
    return reports


def load_gold_paths(raw_paths: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in raw_paths:
        paths.extend(Path(item).resolve() for item in raw.split(",") if item.strip())
    if not paths:
        raise ValueError("--gold requires at least one adjudicated gold file")
    return paths


def root_has_footnote(text: str, footnote_id: str) -> bool:
    return (
        f"[^{footnote_id}]" in text
        or f'id="fnref-{footnote_id}"' in text
        or f'<a id="{footnote_id}"></a>' in text
    )


def root_definition_body(root_page: FOOTNOTES.PageChunk, footnote_id: str, value: str, html_style: bool) -> str:
    """Return the first-line note body from the already materialized root."""
    if html_style:
        pattern = rf'<a id="{footnote_id}"></a><sup>{re.escape(value)}</sup>\s*(?P<body>[^\r\n]*)'
    else:
        pattern = rf'^\[\^{re.escape(footnote_id)}\]:\s*(?P<body>[^\r\n]*)'
    match = re.search(pattern, root_page.text, re.MULTILINE)
    if not match:
        return ""
    body = match.group("body").strip()
    # Keep a concatenated following note out of the authoritative body
    # anchor (for example ``57 Ibid. p. 487. 58 Ibid...``).
    return re.split(r"\s+[1-9]\d{0,2}[,.)]?\s+(?=[A-Za-z\"'])", body, maxsplit=1)[0].strip()

def definition_change_from_root(
    page: FOOTNOTES.PageChunk,
    root_page: FOOTNOTES.PageChunk,
    footnote_id: str,
    value: str,
    html_style: bool,
) -> FOOTNOTES.Change | None:
    """Relabel an extracted note using the root note body as the anchor.

    Extracted documents can preserve the note body while OCR mangles its
    numeric label (for example ``4,The`` for ``43The``).  The body is a much
    safer anchor than searching for the number alone, and this function still
    requires a numeric label at the beginning of the extracted note line (or
    on the immediately preceding label-only line).  This accommodates the
    page extractors that preserve a line break between the label and body.
    """
    body = root_definition_body(root_page, footnote_id, value, html_style)
    if len(FOOTNOTES.canonical(body)) < 8:
        return None
    source = FOOTNOTES.CanonicalText(page.text)
    matches = list(source.find(body))
    candidates: list[tuple[int, int]] = []
    numeric_candidates: list[tuple[int, int]] = []
    for body_start, _ in matches:
        line_start = page.text.rfind("\n", 0, body_start) + 1
        leading = page.text[line_start:body_start]
        prefix_shadow = FOOTNOTES.CanonicalText(leading)
        exact_label = re.search(
            rf"(?<!\w){re.escape(FOOTNOTES.canonical(value))}[,.)]?\s*$",
            prefix_shadow.text,
        )
        if exact_label:
            candidates.append((line_start + prefix_shadow.positions[exact_label.start()], body_start))
        elif re.search(r"(?<!\w)\d{1,3}[,.)]?\s*$", prefix_shadow.text):
            # The extracted note label can be OCR-damaged (for example
            # ``4,The`` where the authoritative root says ``43The``).  The
            # root body is already an exact anchor, so accept a single
            # numeric-label candidate when no exact value candidate exists.
            numeric_label = re.search(r"(?<!\w)\d{1,3}[,.)]?\s*$", prefix_shadow.text)
            assert numeric_label is not None
            numeric_candidates.append((line_start + prefix_shadow.positions[numeric_label.start()], body_start))

        # Some extractors put a label on a line by itself, then start the note
        # body on the next line.  Consume that separator when replacing the
        # label so the result remains one valid definition line.
        if not prefix_shadow.text.strip().strip("> "):
            previous_end = line_start
            previous_start = page.text.rfind("\n", 0, max(0, previous_end - 1)) + 1
            previous_line = page.text[previous_start:previous_end]
            previous_shadow = FOOTNOTES.CanonicalText(previous_line)
            exact_previous = re.search(
                rf"(?<!\w){re.escape(FOOTNOTES.canonical(value))}[,.)]?\s*$",
                previous_shadow.text,
            )
            numeric_previous = re.search(r"(?<!\w)\d{1,3}[,.)]?\s*$", previous_shadow.text)
            label = exact_previous or numeric_previous
            if label:
                target = candidates if exact_previous else numeric_candidates
                target.append((previous_start + previous_shadow.positions[label.start()], body_start))
    if not candidates and len(numeric_candidates) == 1:
        candidates = numeric_candidates
    if len(candidates) != 1:
        return None
    start, end = candidates[0]
    replacement = (
        f'<a id="{footnote_id}"></a><sup>{value}</sup>'
        if html_style
        else f"[^{footnote_id}]:"
    )
    return FOOTNOTES.Change(start, end, replacement, "definition", f"{page.page}:{value}")


def selected_links(
    reports: list[dict[str, Any]],
    allowed: dict[tuple[str, int], set[str]],
) -> dict[str, list[dict[str, Any]]]:
    """Return one evidence link per materialized footnote id and volume."""
    result: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        volume = FOOTNOTES.volume_from_report(report)
        links = FOOTNOTES.confirmed_links(report, allowed)
        grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
        for link in links:
            grouped.setdefault(FOOTNOTES.link_key(link), []).append(link)
        seen_ids: set[str] = set()
        root_path = FOOTNOTES.markdown_path(volume)
        root_text = root_path.read_text(encoding="utf-8")
        for marker_links in grouped.values():
            selected, reason = FOOTNOTES.choose_note_target(marker_links)
            if reason or selected is None:
                continue
            note_page = int(selected["note_page"])
            value = str(selected["marker_value"])
            footnote_id = f"fn-{volume}-p{note_page}-n{value}"
            if footnote_id in seen_ids or not root_has_footnote(root_text, footnote_id):
                continue
            seen_ids.add(footnote_id)
            row = dict(selected)
            row["volume"] = volume
            row["footnote_id"] = footnote_id
            row["html_style"] = f'id="fnref-{footnote_id}"' in root_text
            result.setdefault(volume, []).append(row)
    return result


def extracted_files(directories: list[Path]) -> list[Path]:
    files: list[Path] = []
    for directory in directories:
        if directory.is_dir():
            files.extend(sorted(directory.rglob("*.md")))
    return files


def propagate_file(
    path: Path,
    links: list[dict[str, Any]],
    root_pages: dict[int, FOOTNOTES.PageChunk],
    apply: bool,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        pages = FOOTNOTES.page_chunks(text)
    except ValueError:
        return {"file": str(path), "status": "no_page_markers"}

    changes: dict[int, list[FOOTNOTES.Change]] = {}
    marker_links: list[tuple[dict[str, Any], int, str]] = []
    failures: list[dict[str, Any]] = []
    definitions: dict[tuple[int, str], tuple[str, dict[str, Any], bool]] = {}

    for link in links:
        marker_page = int(link["marker_page"])
        note_page = int(link["note_page"])
        footnote_id = str(link["footnote_id"])
        if marker_page not in pages:
            continue
        # The link is already gold-filtered and the authoritative root has the
        # corresponding marker.  Allow the same context-only insertion here
        # when an extracted document dropped the visible marker.
        marker = FOOTNOTES.marker_change(
            pages[marker_page], link, footnote_id, allow_missing_marker=True
        )
        if marker is None:
            continue
        marker_links.append((link, note_page, footnote_id))
        definitions.setdefault(
            (note_page, str(link["marker_value"])),
            (footnote_id, link, bool(link.get("html_style"))),
        )

    failed_definitions: set[tuple[int, str]] = set()
    for (note_page, value), (footnote_id, link, html_style) in definitions.items():
        if note_page not in pages:
            failures.append({"kind": "definition", "page": note_page, "value": value})
            failed_definitions.add((note_page, value))
            continue
        definition = definition_change_from_root(
            pages[note_page], root_pages[note_page], footnote_id, value, html_style
        ) if note_page in root_pages else None
        if definition is None:
            failures.append({"kind": "definition", "page": note_page, "value": value})
            failed_definitions.add((note_page, value))
            continue
        changes.setdefault(note_page, []).append(definition)

    for link, note_page, footnote_id in marker_links:
        value = str(link["marker_value"])
        if (note_page, value) not in failed_definitions:
            marker_page = int(link["marker_page"])
            marker = FOOTNOTES.marker_change(
                pages[marker_page], link, footnote_id, allow_missing_marker=True
            )
            if marker is not None:
                changes.setdefault(marker_page, []).append(marker)

    applied_markers = 0
    applied_definitions = 0
    changed_pages = 0
    updated = text
    for page_number in sorted(changes, reverse=True):
        page_changes = changes[page_number]
        try:
            new_chunk = FOOTNOTES.apply_changes(pages[page_number].text, page_changes)
        except ValueError as exc:
            failures.append({"kind": "overlapping_changes", "page": page_number, "reason": str(exc)})
            continue
        if new_chunk == pages[page_number].text:
            continue
        changed_pages += 1
        applied_markers += sum(change.kind.startswith("marker") for change in page_changes)
        applied_definitions += sum(change.kind == "definition" for change in page_changes)
        if apply:
            page = pages[page_number]
            updated = updated[:page.start] + new_chunk + updated[page.end:]
            pages = FOOTNOTES.page_chunks(updated)

    if apply and updated != text:
        path.write_text(updated, encoding="utf-8")
    return {
        "file": str(path),
        "status": "changed" if changed_pages else "unchanged",
        "changed_pages": changed_pages,
        "applied_markers": applied_markers,
        "applied_definitions": applied_definitions,
        "failures": failures,
        "applied": apply,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--gold", action="append", required=True, help="Adjudicated gold JSON file(s).")
    parser.add_argument(
        "--directory",
        type=Path,
        action="append",
        help="Extracted Markdown directory; defaults to cases, cases-rebuilt, inquiries, and studies.",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "ocr-bakeoff" / "reports" / "footnote_propagation.json")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reports = load_reports(args.report)
    gold_paths = load_gold_paths(args.gold)
    allowed = FOOTNOTES.load_gold_markers(gold_paths)
    links_by_volume = selected_links(reports, allowed)
    root_pages_by_volume: dict[str, dict[int, FOOTNOTES.PageChunk]] = {}
    for volume in links_by_volume:
        root_path = FOOTNOTES.markdown_path(volume)
        root_pages_by_volume[volume] = FOOTNOTES.page_chunks(root_path.read_text(encoding="utf-8"))
    directories = args.directory or [ROOT / name for name in ("cases", "cases-rebuilt", "inquiries", "studies")]
    files = extracted_files(directories)
    results: list[dict[str, Any]] = []
    for path in files:
        volume = next((volume for volume in links_by_volume if f"ga{int(volume[2:]):02d}_" in path.name), None)
        if volume:
            results.append(propagate_file(path, links_by_volume[volume], root_pages_by_volume[volume], args.apply))
    changed = [row for row in results if row.get("changed_pages")]
    payload = {
        "schema": "pca-ga.footnote-propagation.v1",
        "reports": [str(path) for path in args.report],
        "gold": [str(path) for path in gold_paths],
        "directories": [str(path) for path in directories],
        "apply": args.apply,
        "files_scanned": len(results),
        "files_changed": len(changed),
        "applied_markers": sum(int(row.get("applied_markers", 0)) for row in results),
        "applied_definitions": sum(int(row.get("applied_definitions", 0)) for row in results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("apply", "files_scanned", "files_changed", "applied_markers", "applied_definitions")}, indent=2))


if __name__ == "__main__":
    main()
