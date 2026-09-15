#!/usr/bin/env python3
"""Render the canonical judicial-case taxonomy as a human-readable index.

This is intentionally a separate catalogue from ``index/CASES.md``.  CASES.md
is the legacy extraction/index view; JUDICIAL-CASES.md is the one-row-per-
rostered-case editorial view produced by scripts/12_case_taxonomy.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter


DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def candidate_overlays(root, registry_name):
    if not registry_name:
        return {}, None
    registry_path = os.path.abspath(
        registry_name if os.path.isabs(registry_name)
        else os.path.join(root, registry_name)
    )
    root_path = os.path.abspath(root)
    if os.path.commonpath([root_path, registry_path]) != root_path:
        raise ValueError("Candidate registry is outside the repository")
    with open(registry_path, encoding="utf-8") as source:
        registry = json.load(source)
    if registry.get("publication_authorized") is not False:
        raise ValueError("Candidate registry must explicitly deny publication")
    overlays = {}
    for item in registry.get("candidates") or []:
        case_id = item["case_id"]
        if case_id in overlays:
            raise ValueError(f"Duplicate candidate registry case: {case_id}")
        selected = item["selected"]
        candidate_path = os.path.abspath(os.path.join(root, selected["path"]))
        if os.path.commonpath([root_path, candidate_path]) != root_path:
            raise ValueError(f"Candidate is outside the repository: {case_id}")
        with open(candidate_path, encoding="utf-8") as source:
            candidate = json.load(source)
        candidate_case_id = candidate.get("case_id")
        if candidate_case_id != case_id:
            if selected.get("identity_remapped_from") != candidate_case_id:
                raise ValueError(f"Candidate identity mismatch: {case_id}")
        overlays[case_id] = {
            "summary": candidate["summary"],
            "matter_type": candidate.get("matter_type"),
            "final_dispositions": candidate.get("final_dispositions"),
            "provider": selected["provider"],
            "model": selected["model"],
            "path": selected["path"],
        }
    return overlays, registry_path


def candidate_review_label(candidate):
    path = candidate["path"]
    # JUDICIAL-CASES.md is in index/, so keep its candidate links relative.
    link = path[len("index/"):] if path.startswith("index/") else "../" + path
    provider = "Sol" if candidate["provider"] == "openai" else "DeepSeek"
    return f"[Candidate — {provider}; needs source audit]({link})"


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=DEFAULT_ROOT)
    parser.add_argument(
        "--candidate-registry",
        help="Overlay unapproved candidates for a working-tree review rendering",
    )
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    source_path = os.path.join(root, "index", "judicial_cases.jsonl")
    output_path = os.path.join(root, "index", "JUDICIAL-CASES.md")
    overlays, registry_path = candidate_overlays(root, args.candidate_registry)

    with open(source_path, encoding="utf-8") as source:
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
    ]
    if overlays:
        registry_display = os.path.relpath(registry_path, os.path.dirname(output_path)).replace("\\", "/")
        lines.extend([
            "> **Candidate review rendering:** "
            f"{len(overlays)} model-generated candidates from "
            f"[{os.path.basename(registry_path)}]({registry_display}) overlay the maintained "
            "summary, matter type, and disposition for review. They have not been source-audited, "
            "approved, or published to the canonical editorial overrides. Follow the "
            "[audit instructions](synopsis_workflow/AUDIT-INSTRUCTIONS.md).",
            "",
            "| Case ID | Title | Matter type | Final disposition | Review basis | Aliases | Candidate synopsis | Synopsis review | BCO provisions | Topic tags | Status | Source |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ])
    else:
        lines.extend([
            "| Case ID | Title | Matter type | Final disposition | Review basis | Aliases | Summary | BCO provisions | Topic tags | Status | Source |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ])
    for row in rows:
        row = dict(row)
        record_id = row.get("case_id") or row.get("roster_id")
        candidate = overlays.get(record_id)
        if not candidate and not row.get("case_id") and row.get("roster_id"):
            candidate = overlays.get("roster:" + row["roster_id"])
        if candidate:
            row["summary"] = candidate["summary"]
            if candidate["matter_type"]:
                row["matter_type"] = candidate["matter_type"]
            if candidate["final_dispositions"]:
                row["final_dispositions"] = candidate["final_dispositions"]
        bco = ", ".join(f"`BCO {x}`" for x in row.get("bco_provisions") or []) or "—"
        topics = ", ".join(f"`{md(x)}`" for x in row.get("topic_tags") or []) or "—"
        standards = review_basis(row)
        title = md(row.get("title")) or "—"
        summary = md(row.get("summary")) or "—"
        case_id = f"`{row['case_id']}`" if row.get("case_id") else f"`{row.get('roster_id')}`"
        prefix = (
            f"| {case_id} | {title} | "
            f"{md(MATTER_TYPE_LABELS.get(row.get('matter_type'), row.get('matter_type'))) or '—'} | "
            f"{final_disposition(row)} | {standards} | {aliases(row)} | {summary} |"
        )
        if overlays:
            synopsis_review = (
                candidate_review_label(candidate) if candidate
                else md(row.get("summary_review_status") or "No candidate")
            )
            lines.append(
                f"{prefix} {synopsis_review} | {bco} | {topics} | "
                f"{md(STATUS_LABELS.get(row.get('classification_status'), row.get('classification_status'))) or '—'} | {linked_source(row)} |"
            )
        else:
            lines.append(
                f"{prefix} {bco} | {topics} | "
                f"{md(STATUS_LABELS.get(row.get('classification_status'), row.get('classification_status'))) or '—'} | {linked_source(row)} |"
            )
    with open(output_path, "w", encoding="utf-8", newline="\n") as target:
        target.write("\n".join(lines) + "\n")
    mode = f" with {len(overlays)} candidate overlays" if overlays else ""
    print(f"[taxonomy-index] wrote {len(rows)} rows{mode} -> {output_path}")


if __name__ == "__main__":
    main()
