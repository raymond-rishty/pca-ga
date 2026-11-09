"""Small adapters for scripts that still consume case rows in legacy shape.

The canonical source remains ``judicial_cases.jsonl``. These rows exist only to
keep older page extraction utilities readable while their fields are migrated.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_judicial_case_rows(root: str | Path) -> list[dict]:
    path = Path(root) / "data" / "cases" / "records" / "judicial_cases.jsonl"
    rows = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            case = json.loads(line)
            parties = case.get("parties") or ""
            if isinstance(parties, dict):
                parties = parties.get("raw") or ""
            dispositions = case.get("final_dispositions") or []
            disposition = case.get("disposition_detail") or "; ".join(dispositions)
            cited = case.get("bco_cited_as") or []
            rows.append({
                "rowid": len(rows) + 1,
                "case_id": case.get("case_id"),
                "canonical_number": case.get("case_id"),
                "case_number": case.get("legacy_case_id") or case.get("case_id"),
                "title": case.get("title") or "",
                "parties": parties,
                "body": case.get("body"),
                "ga_ordinal": case.get("source_assembly") or case.get("assembly"),
                "year": case.get("source_year") or case.get("decision_year"),
                "pdf_page_start": case.get("source_pdf_page_start"),
                "pdf_page_end": case.get("source_pdf_page_end"),
                "printed_page_start": case.get("source_printed_page_start"),
                "printed_page_end": case.get("source_printed_page_end"),
                "disposition": disposition,
                "vote": None,
                "has_dissent": int(bool(case.get("dissent"))),
                "bco_cited_as_s": "; ".join(str(value) for value in cited),
                "synopsis": case.get("summary") or "",
                "provenance": "",
            })
    return rows
