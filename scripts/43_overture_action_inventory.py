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
from overture_identity import load_reconciled_overture_records


ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
IDX = ROOT / "index"
CATALOGUE = IDX / "OVERTURES.md"
LEDGER = IDX / "overture_action_research.jsonl"
EVENTS = IDX / "overture_events.jsonl"

def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _existing_status() -> dict[str, dict]:
    prior = {row["record_id"]: row for row in _jsonl(LEDGER) if row.get("record_id")}
    # A previously researched record can be temporarily absent from the reconciled
    # catalogue while its source occurrence is being repaired. Preserve its progress
    # from the event trail so the next catalogue regeneration does not reset it.
    for event_row in _jsonl(EVENTS):
        rid = event_row.get("record_id")
        if rid and rid not in prior:
            prior[rid] = {
                "research_status": event_row.get("research_status", "not_researched"),
                "sources_searched": event_row.get("sources_searched", []),
                "search_through_assembly": event_row.get("search_through_assembly"),
                "gap_note": event_row.get("gap_note"),
            }
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
    return load_reconciled_overture_records(IDX)


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
