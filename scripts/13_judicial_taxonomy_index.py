#!/usr/bin/env python3
"""Render the canonical judicial-case taxonomy as a human-readable index.

This is intentionally a separate catalogue from ``index/CASES.md``.  CASES.md
is the legacy extraction/index view; JUDICIAL-CASES.md is the one-row-per-
rostered-case editorial view produced by scripts/12_case_taxonomy.py.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter


ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(ROOT, "index")
SOURCE = os.path.join(IDX, "judicial_cases.jsonl")
OUTPUT = os.path.join(IDX, "JUDICIAL-CASES.md")


def md(value):
    """Keep generated table rows valid when source metadata contains pipes."""
    return str(value or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def linked_source(row):
    page = row.get("case_page")
    if page:
        return f"[case page](../cases/{page}.md)"
    if row.get("official_pdf_url"):
        return f"[official PDF]({row['official_pdf_url']})"
    return "—"


def aliases(row):
    values = []
    if row.get("legacy_case_id") and row["legacy_case_id"] != row.get("case_id"):
        values.append(f"legacy `{row['legacy_case_id']}`")
    if row.get("era_label"):
        values.append(f"`{row['era_label']}`")
    if row.get("minute_ids"):
        values.append("Minutes " + ", ".join(f"`{x}`" for x in row["minute_ids"]))
    return "; ".join(values) or "—"


def main():
    with open(SOURCE, encoding="utf-8") as source:
        rows = [json.loads(line) for line in source if line.strip()]
    rows.sort(key=lambda row: (row.get("case_id") is None, row.get("case_id") or row.get("roster_id") or ""))
    statuses = Counter(row.get("classification_status") for row in rows)
    lines = [
        "# Canonical judicial cases",
        "",
        "One row per unique case in the official SJC/CJB roster. The canonical `case_id` is a "
        "zero-padded docket such as `2023-07`; legacy, era-based, and Minutes identifiers are "
        "preserved as aliases. See [the taxonomy specification](../docs/JUDICIAL-CASE-TAXONOMY.md) "
        "for controlled vocabularies and source rules.",
        "",
        f"**{len(rows)} records** · classified {statuses['classified']} · "
        f"needs review {statuses['needs_review']} · roster only {statuses['roster_only']}",
        "",
        "| Case ID | Title | Proceeding | Outcome | Review basis | Aliases | Summary | BCO provisions | Topic tags | Status | Source |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        bco = ", ".join(f"`BCO {x}`" for x in row.get("bco_provisions") or []) or "—"
        topics = ", ".join(f"`{md(x)}`" for x in row.get("topic_tags") or []) or "—"
        standards = ", ".join(f"`{md(x)}`" for x in row.get("review_standards") or []) or f"`{md(row.get('standard_of_review'))}`"
        title = md(row.get("title")) or "—"
        summary = md(row.get("summary")) or "—"
        case_id = f"`{row['case_id']}`" if row.get("case_id") else f"`{row.get('roster_id')}`"
        lines.append(
            f"| {case_id} | {title} | `{md(row.get('proceeding_type'))}` | "
            f"`{md(row.get('outcome'))}` | {standards} | {aliases(row)} | {summary} | {bco} | {topics} | "
            f"`{md(row.get('classification_status'))}` | {linked_source(row)} |"
        )
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as target:
        target.write("\n".join(lines) + "\n")
    print(f"[taxonomy-index] wrote {len(rows)} rows -> {OUTPUT}")


if __name__ == "__main__":
    main()
