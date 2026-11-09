#!/usr/bin/env python3
"""Report case pages and docket numbers not represented in the canonical case catalogue.

The Historical Center roster is intentionally not used to define coverage:
its omissions and incorrect docket numbers make it an unsuitable sequence
authority. This audit compares the Minutes-derived case corpus, canonical
catalogue, and case-page map. It reports candidates for review and never edits
case records.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()]


def case_id(value: Any) -> str | None:
    match = re.fullmatch(r"\s*(\d{4})-(\d{1,3})([a-z]?)\s*", str(value or ""), re.I)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}{match.group(3).lower()}"


def main() -> None:
    extracted = read_jsonl(ROOT / "data/cases/records/cases.jsonl")
    canonical = read_jsonl(ROOT / "data/cases/records/judicial_cases.jsonl")
    coverage_reviews = json.loads(
        (ROOT / "data/cases/overrides/case_coverage_reviews.json")
        .read_text(encoding="utf-8-sig")
    )
    page_map_path = ROOT / "index/case_pages_map.json"
    page_map = json.loads(page_map_path.read_text(encoding="utf-8-sig"))

    canonical_ids = {case_id(row.get("case_id")) for row in canonical}
    canonical_pages = {str(row.get("case_page") or "").strip() for row in canonical}
    extracted_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in extracted:
        normalized = case_id(row.get("case_id") or row.get("case_number"))
        if normalized:
            extracted_by_id[normalized].append(row)

    pages: dict[str, set[str]] = defaultdict(set)
    page_titles: dict[str, str] = {}
    for raw_id, entry in page_map.items():
        if not isinstance(entry, dict) or not entry.get("file"):
            continue
        file = str(entry["file"])
        normalized = case_id(raw_id)
        if normalized:
            pages[file].add(normalized)
        for number in entry.get("numbers", []):
            normalized = case_id(number)
            if normalized:
                pages[file].add(normalized)
        if entry.get("title"):
            page_titles[file] = str(entry["title"])

    missing_pages = []
    for file, docket_ids in sorted(pages.items()):
        if file in canonical_pages or docket_ids & canonical_ids:
            continue
        page_path = ROOT / "cases" / f"{file}.md"
        if not page_path.exists():
            continue
        dispositions = sorted({
            str(row.get("disposition") or "unspecified")
            for docket in docket_ids for row in extracted_by_id.get(docket, [])
        })
        missing_pages.append({
            "file": file,
            "dockets": sorted(docket_ids),
            "title": page_titles.get(file, ""),
            "dispositions": dispositions,
        })

    lines = [
        "# Judicial case coverage audit",
        "",
        "This report compares the Minutes-derived case corpus, the canonical catalogue, and the case-page map.",
        "The Historical Center roster is not used to define coverage because it can omit cases or list wrong docket numbers.",
        "",
        "A page is treated as represented when a canonical record points to it or a companion docket on the same mapped page has a canonical record. Only explicit docket identities from the Minutes-derived corpus and case-page map count as coverage evidence; a number missing between two others is not presumed to be an assigned docket. A shared-page docket alias counts as represented.",
        "",
        f"- Canonical records: {len(canonical)}",
        f"- Mapped case pages without a canonical record: {len(missing_pages)}",
        "",
        "## Case pages without canonical records",
        "",
        "| Docket ID(s) | Page | Caption | Extracted disposition(s) |",
        "|---|---|---|---|",
    ]
    for item in missing_pages:
        dockets = ", ".join(f"`{d}`" for d in item["dockets"])
        page = f"[case page](../../cases/{item['file']}.md)"
        title = item["title"].replace("|", "\\|")
        dispositions = ", ".join(item["dispositions"]) or "no extracted row"
        lines.append(f"| {dockets} | {page} | {title} | {dispositions} |")
    lines.extend([
        "",
        "## Reviewed docket-number findings",
        "",
        "These reviewed findings are retained as source input in `data/cases/overrides/case_coverage_reviews.json`; this section is generated from that file, not entered only in this report.",
        "",
        "| Docket ID | Status | Reviewed | Finding | Evidence |",
        "|---|---|---|---|---|",
    ])
    for review in coverage_reviews.get("not_found_candidates", []):
        docket = str(review.get("candidate_id", "")).strip()
        status = str(review.get("status", "unreviewed")).replace("|", "\\|")
        reviewed = str(review.get("reviewed_at", ""))
        finding = str(review.get("finding", "")).replace("|", "\\|")
        evidence = "<br>".join(str(item).replace("|", "\\|") for item in review.get("evidence", []))
        lines.append(f"| `{docket}` | `{status}` | {reviewed} | {finding} | {evidence} |")
    lines.extend([
        "",
        "## Checkpoint",
        "",
        f"`2021-09` is present in `judicial_cases.jsonl`: {'yes' if '2021-09' in canonical_ids else 'no'}.",
        "",
    ])
    output = ROOT / "docs/audits/CASE-COVERAGE-AUDIT.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"canonical records: {len(canonical)}")
    print(f"mapped pages without a canonical record: {len(missing_pages)}")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
