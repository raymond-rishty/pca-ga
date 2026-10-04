#!/usr/bin/env python3
"""Build a stable research ledger from the reconciled overture catalogue.

The published, reconciled index/OVERTURES.md is the scope for action-trail research.
The underlying structure and disposition extracts have different record counts, so this
ledger deliberately starts from the reader-facing catalogue and preserves its source-page
identity. Existing review state is retained by record_id when the ledger is regenerated.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
IDX = ROOT / "index"
CATALOGUE = IDX / "OVERTURES.md"
LEDGER = IDX / "overture_action_research.jsonl"
EVENTS = IDX / "overture_events.jsonl"

HEADING = re.compile(r"^## .*\((\d{4})\).*`(ga\d+_\d{4})`$")
NUMBER = re.compile(r"\d+")
PAGE = re.compile(r"\[p\.(\d+)\]\([^)]*#ga\d+-p(\d+)\)")


def _cells(line: str) -> list[str]:
    """Split a markdown table row on unescaped pipes and unescape literal pipes."""
    cells = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return [cell.replace(r"\|", "|").strip() for cell in cells]


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _existing_status() -> dict[str, dict]:
    prior = {row["record_id"]: row for row in _jsonl(LEDGER) if row.get("record_id")}
    # The first prototype used only volume and number. Migrate it only when that pair names
    # exactly one row in the published catalogue; ambiguous legacy rows must be reviewed.
    legacy = [row for row in _jsonl(EVENTS) if not row.get("record_id")]
    by_pair: dict[tuple[str, int], list[dict]] = {}
    for row in _parse_catalogue():
        by_pair.setdefault((row["vol"], row["number"]), []).append(row)
    for event_row in legacy:
        pair = (str(event_row.get("vol") or ""), int(event_row.get("number") or 0))
        matches = by_pair.get(pair, [])
        if len(matches) != 1:
            raise ValueError(f"legacy event identity {pair} maps to {len(matches)} catalogue rows")
        rid = matches[0]["record_id"]
        prior.setdefault(rid, {
            "research_status": "in_progress",
            "sources_searched": sorted({
                f"{event.get('source_volume') or pair[0]} p.{event.get('source_pdf_page')}"
                for event in event_row.get("events", []) if event.get("source_pdf_page")
            }),
            "search_through_assembly": max((
                int(match.group(1)) for event in event_row.get("events", [])
                if (match := re.match(r"ga(\d+)", event.get("source_volume") or pair[0]))
            ), default=None),
            "gap_note": "Prototype history exists; review completeness against the action-trail research standard.",
        })
    return prior


def _parse_catalogue() -> list[dict]:
    if not CATALOGUE.exists():
        raise FileNotFoundError(f"missing reconciled overture catalogue: {CATALOGUE}")
    records: list[dict] = []
    vol = None
    year = None
    ga = None
    for line in CATALOGUE.read_text(encoding="utf-8").splitlines():
        heading = HEADING.match(line)
        if heading:
            year, vol = int(heading.group(1)), heading.group(2)
            ga = int(re.match(r"ga(\d+)", vol).group(1))
            continue
        if not vol or not line.startswith("|") or line.startswith(("|---", "| Overture")):
            continue
        cells = _cells(line)
        if len(cells) != 5:
            continue
        n = NUMBER.search(cells[0])
        page_links = PAGE.findall(cells[4])
        if not n or not page_links:
            continue
        number = int(n.group())
        pages = list(dict.fromkeys(int(pdf_page) for _, pdf_page in page_links))
        source_page = pages[0]
        record_id = f"overture:{vol}:{number}:p{source_page}"
        records.append({
            "record_id": record_id,
            "vol": vol,
            "ga_ordinal": ga,
            "year": year,
            "number": number,
            "source_page": source_page,
            "catalogue_pages": pages,
            "title": cells[1],
            "source": cells[3],
            "disposition": cells[2],
        })
    ids = [row["record_id"] for row in records]
    duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
    if duplicates:
        raise ValueError(f"duplicate stable record IDs in reconciled catalogue: {duplicates[:12]}")
    return records


def main() -> None:
    status = _existing_status()
    records = _parse_catalogue()
    with LEDGER.open("w", encoding="utf-8", newline="\n") as out:
        for row in records:
            prior = status.get(row["record_id"], {})
            row.update({
                "research_status": prior.get("research_status", "not_researched"),
                "sources_searched": prior.get("sources_searched", []),
                "search_through_assembly": prior.get("search_through_assembly"),
                "gap_note": prior.get("gap_note"),
            })
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} overture action-research records -> {LEDGER}")


if __name__ == "__main__":
    main()
