#!/usr/bin/env python3
"""Build source-located Assembly case-entry observations from reconciled extraction rows.

These entries preserve where the Minutes extraction found a case-like listing. They are not
canonical cases: renderers join verified matches to judicial_cases.jsonl and leave unresolved
or mis-extracted entries identified as source observations.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data/cases/derived/cases_reconciled.jsonl"
DEFAULT_OUTPUT = ROOT / "data/cases/derived/assembly_case_entries.jsonl"
DEFAULT_REVIEWS = ROOT / "data/cases/overrides/assembly_case_entry_reviews.json"


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value or "entry")


def build_entries(rows: list[dict], reviews: list[dict] | None = None) -> tuple[list[dict], int]:
    entries = []
    seen_ids: Counter[str] = Counter()
    skipped_unlocated = 0
    review_by_id = {review["entry_id"]: review for review in (reviews or [])}

    for row in rows:
        assembly = row.get("ga_ordinal")
        page_start = row.get("pdf_page_start")
        if assembly is None or page_start is None:
            skipped_unlocated += 1
            continue

        year = row.get("year")
        volume = f"ga{int(assembly):02d}_{year}" if year else f"ga{int(assembly):02d}"
        base_id = f"{volume}:p{int(page_start)}:{safe_id(row.get('case_id') or row.get('case_number'))}"
        seen_ids[base_id] += 1
        entry_id = base_id if seen_ids[base_id] == 1 else f"{base_id}:{seen_ids[base_id]}"

        parties = row.get("parties")
        if isinstance(parties, dict):
            parties = parties.get("raw") or "; ".join(
                str(value) for value in parties.values() if value
            )

        entry = {
            "entry_id": entry_id,
            "entry_kind": "extracted_case_entry",
            "review_status": "unreviewed",
            "index_decision": "include",
            "assembly": int(assembly),
            "assembly_year": year,
            "volume": volume,
            "pdf_page_start": int(page_start),
            "pdf_page_end": row.get("pdf_page_end"),
            "printed_page_start": row.get("printed_page_start"),
            "printed_page_end": row.get("printed_page_end"),
            "source_pdf": row.get("source_pdf"),
            "extraction_id": row.get("case_id"),
            "observed_docket": row.get("case_number"),
            "raw_title": row.get("title"),
            "parties": parties,
            "observed_disposition": row.get("disposition"),
            "observed_vote": row.get("vote"),
            "observed_dissent": bool(row.get("has_dissent")),
            "observed_synopsis": row.get("synopsis"),
            "provenance": row.get("provenance") or {},
        }
        review = review_by_id.get(entry_id)
        if review:
            if review.get("decision") not in {"include", "exclude"}:
                raise ValueError(f"Unsupported decision for {entry_id}: {review.get('decision')!r}")
            entry["review_status"] = "reviewed"
            entry["index_decision"] = review["decision"]
            entry["review_reason"] = review.get("reason")
        entries.append(entry)

    unmatched_reviews = set(review_by_id) - {entry["entry_id"] for entry in entries}
    if unmatched_reviews:
        raise ValueError(f"Assembly-entry reviews did not match extracted entries: {sorted(unmatched_reviews)}")
    return entries, skipped_unlocated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    reviews = json.loads(args.reviews.read_text(encoding="utf-8")) if args.reviews.exists() else []
    entries, skipped = build_entries(rows, reviews)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        for entry in entries:
            output.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"wrote {len(entries)} located Assembly case entries -> {args.output}")
    print(f"skipped {skipped} records without an Assembly/page locator")


if __name__ == "__main__":
    main()
