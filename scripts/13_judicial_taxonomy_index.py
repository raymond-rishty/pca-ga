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

MATTER_TYPE_LABELS = {
    "complaint": "Complaint",
    "appeal": "Appeal",
    "judicial_reference": "Judicial reference",
    "original_jurisdiction_request": "Original-jurisdiction request",
    "bco_40_5_matter": "BCO 40-5 matter",
    "review_and_control": "Review and control",
    "other": "Other",
}
FINAL_DISPOSITION_LABELS = {
    "sustained": "Sustained",
    "partially_sustained": "Partially sustained",
    "not_sustained": "Not sustained",
    "denied": "Denied",
    "granted": "Granted",
    "guilty": "Guilty",
    "not_guilty": "Not guilty",
    "administratively_out_of_order": "Administratively out of order",
    "judicially_out_of_order": "Judicially out of order",
    "out_of_order": "Out of order (type not stated)",
    "dismissed": "Dismissed",
    "withdrawn": "Withdrawn",
    "abandoned": "Abandoned",
    "moot": "Moot",
    "affirmed": "Affirmed",
    "reversed": "Reversed",
    "vacated": "Vacated",
    "annulled": "Annulled",
    "remanded": "Remanded",
    "referred": "Referred",
    "in_order": "In order",
    "no_final_disposition": "No final disposition in available record",
    "other": "Other",
}
REVIEW_BASIS_LABELS = {
    "factual_findings": "Great deference unless clear error (factual findings)",
    "discretion_and_judgment": "Great deference unless clear error (discretion and judgment)",
    "constitutional_interpretation": "Independent review (constitutional interpretation)",
    "important_delinquency_or_grossly_unconstitutional_proceeding": (
        "BCO 40-5 — important delinquency or grossly unconstitutional proceeding"
    ),
    "mixed": "Multiple review bases",
    "not_reached": "Not reached",
    "not_applicable": "Not applicable",
    "not_stated": "Not stated",
    "unknown": "Unknown",
}
STATUS_LABELS = {
    "classified": "Classified",
    "needs_review": "Needs review",
    "roster_only": "Roster only",
}


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


def review_basis(row):
    values = list(dict.fromkeys(row.get("review_standards") or []))
    if values:
        parts = []
        deferential = [
            label for value, label in (
                ("factual_findings", "factual findings"),
                ("discretion_and_judgment", "discretion and judgment"),
            ) if value in values
        ]
        if deferential:
            parts.append(f"Great deference unless clear error ({'; '.join(deferential)})")
        parts.extend(
            md(REVIEW_BASIS_LABELS.get(value, value))
            for value in values
            if value not in {"factual_findings", "discretion_and_judgment"}
        )
        return "; ".join(parts)
    value = row.get("standard_of_review")
    return md(REVIEW_BASIS_LABELS.get(value, value)) or "—"


def final_disposition(row):
    values = row.get("final_dispositions") or []
    return "; ".join(
        md(FINAL_DISPOSITION_LABELS.get(value, value)) for value in values
    ) or "—"


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
        "| Case ID | Title | Matter type | Final disposition | Review basis | Aliases | Summary | BCO provisions | Topic tags | Status | Source |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        bco = ", ".join(f"`BCO {x}`" for x in row.get("bco_provisions") or []) or "—"
        topics = ", ".join(f"`{md(x)}`" for x in row.get("topic_tags") or []) or "—"
        standards = review_basis(row)
        title = md(row.get("title")) or "—"
        summary = md(row.get("summary")) or "—"
        case_id = f"`{row['case_id']}`" if row.get("case_id") else f"`{row.get('roster_id')}`"
        lines.append(
            f"| {case_id} | {title} | {md(MATTER_TYPE_LABELS.get(row.get('matter_type'), row.get('matter_type'))) or '—'} | "
            f"{final_disposition(row)} | {standards} | {aliases(row)} | {summary} | {bco} | {topics} | "
            f"{md(STATUS_LABELS.get(row.get('classification_status'), row.get('classification_status'))) or '—'} | {linked_source(row)} |"
        )
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as target:
        target.write("\n".join(lines) + "\n")
    print(f"[taxonomy-index] wrote {len(rows)} rows -> {OUTPUT}")


if __name__ == "__main__":
    main()
