"""Canonical identifiers for physical and printed-page locations in GA Minutes."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Iterable


def page_identifiers(ga: str | int, pdf_page: int, printed_page: str | None,
                     printed_counts: Counter[str] | None = None) -> dict[str, str | None]:
    """Return stable PDF, printed, and compatibility IDs for one physical page."""
    ga_number = int(ga)
    pdf_id = f"ga{ga_number}-pdf-p{int(pdf_page)}"
    if printed_page is None or printed_page.lower() == "null":
        return {"pdf": pdf_id, "printed": None, "qualified": None}

    folio = printed_page.strip()
    safe_folio = re.sub(r"[^A-Za-z0-9.-]+", "-", folio).strip("-")
    if not safe_folio:
        return {"pdf": pdf_id, "printed": None, "qualified": None}
    counts = printed_counts or Counter()
    return {
        "pdf": pdf_id,
        "printed": f"ga{ga_number}-p{safe_folio}",
        "qualified": (f"ga{ga_number}-p{safe_folio}-at-pdf{int(pdf_page)}"
                      if counts[folio] > 1 else None),
    }


def count_printed_pages(pages: Iterable[tuple[str, str]]) -> Counter[str]:
    """Count folio occurrences from (printed_page, pdf_page) page records."""
    counts: Counter[str] = Counter()
    for printed, _pdf in pages:
        if printed and printed.lower() != "null":
            counts[printed.strip()] += 1
    return counts


_PAGE_RECORDS: dict[tuple[str, str], list[dict[str, object]]] = {}
_PAGE_RE = re.compile(
    r"<!--\s*PAGE\s+ga=(?P<ga>\d+)\s+pdf_page=(?P<pdf>\d+)"
    r"(?:\s+printed_page=(?P<printed>[^\s>]+))?[^>]*-->"
)
_ANCHOR_RE = re.compile(r'<a\s+id="(?P<anchor>ga\d+-p[^"]+)"')


def page_records(root: Path, volume: str) -> list[dict[str, object]]:
    """Read physical pages and their legacy boundary IDs from source Markdown."""
    key = (str(root.resolve()), volume)
    if key in _PAGE_RECORDS:
        return _PAGE_RECORDS[key]
    path = root / "markdown" / f"{volume}.md"
    if not path.is_file():
        _PAGE_RECORDS[key] = []
        return []
    ga_match = re.match(r"ga0*(\d+)[_-]", volume)
    ga = int(ga_match.group(1)) if ga_match else 0
    records: list[dict[str, object]] = []
    pending: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        pending.extend(match.group("anchor") for match in _ANCHOR_RE.finditer(line))
        marker = _PAGE_RE.search(line)
        if not marker:
            continue
        raw_printed = marker.group("printed")
        records.append({
            "ga": int(marker.group("ga")) or ga,
            "pdf_page": int(marker.group("pdf")),
            "printed_page": (raw_printed if raw_printed and raw_printed.lower() != "null"
                             else None),
            "legacy_anchors": tuple(pending),
        })
        pending = []
    _PAGE_RECORDS[key] = records
    return records


def resolve_legacy_page(root: Path, volume: str, anchor: str,
                        printed_page: str | int | None = None) -> dict[str, object] | None:
    """Resolve a pre-contract locator using its stored folio and source boundary."""
    records = page_records(root, volume)
    normalized = re.fullmatch(r"ga0*(\d+)-p(.+)", anchor or "")
    if not normalized:
        return None
    number = normalized.group(2)
    if number.startswith("pdf-p"):
        page = number[5:]
        return next((record for record in records
                     if str(record["pdf_page"]) == page), None)
    qualified = re.fullmatch(r"(.+)-at-pdf(\d+)", number)
    if qualified:
        folio, pdf_page = qualified.groups()
        return next((record for record in records
                     if str(record["pdf_page"]) == pdf_page
                     and str(record["printed_page"]) == folio), None)

    # Existing repository records may store the physical PDF coordinate in a
    # gaNN-pN fragment. When a printed folio is also recorded, prefer the
    # matching physical page among that folio's occurrences.
    if printed_page is not None:
        folio = str(printed_page)
        candidates = [record for record in records
                      if str(record["printed_page"]) == folio]
        physical = next((record for record in candidates
                         if str(record["pdf_page"]) == number), None)
        if physical:
            return physical
        if len(candidates) == 1:
            return candidates[0]

    # Before migration, the source file records exactly which physical page a
    # legacy empty anchor preceded. Use that association only as migration
    # evidence; new public bare fragments have printed-page meaning.
    legacy = next((record for record in records
                   if anchor in record["legacy_anchors"]), None)
    if legacy:
        return legacy

    candidates = [record for record in records
                  if str(record["printed_page"]) == number]
    return candidates[0] if candidates else None


def canonical_page_anchor(record: dict[str, object], printed_counts: Counter[str]) -> str:
    """Return the printed-page target, qualified when that folio recurs."""
    ga = int(record["ga"])
    pdf_page = int(record["pdf_page"])
    printed = record["printed_page"]
    if printed is None:
        return f"ga{ga}-pdf-p{pdf_page}"
    identifiers = page_identifiers(ga, pdf_page, str(printed), printed_counts)
    return str(identifiers["qualified"] or identifiers["printed"])
