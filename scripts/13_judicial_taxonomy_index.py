#!/usr/bin/env python3
"""Render the canonical judicial-case taxonomy as a human-readable index.

This is intentionally a separate catalogue from ``index/CASES.md``.  CASES.md
is the legacy extraction/index view; JUDICIAL-CASES.md is the one-row-per-
rostered-case editorial view produced by scripts/12_case_taxonomy.py.
"""
from __future__ import annotations

import argparse
import html
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


def esc(value):
    return html.escape(str(value or ""), quote=True)


def case_href(row):
    if row.get("case_page"):
        return f"../cases/{row['case_page']}.md"
    return row.get("official_pdf_url") or ""


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
    rows.sort(key=lambda row: (-int(str(row.get("case_id") or row.get("roster_id") or "0").split("-")[0]) if str(row.get("case_id") or row.get("roster_id") or "0").split("-")[0].isdigit() else 0, row.get("case_id") or row.get("roster_id") or ""))
    statuses = Counter(row.get("classification_status") for row in rows)
    lines = [
        "# Judicial cases",
        "",
        "Cases decided by the Standing Judicial Commission and its predecessor, the Committee on Judicial Business. Browse the docket by year, read the editorial synopsis, and open the details shelf for constitutional references and source identifiers.",
        "",
        '<section class="judicial-catalogue-tools" aria-label="Catalogue tools">',
        '<label for="judicialCaseSearch">Search cases</label>',
        '<input id="judicialCaseSearch" type="search" placeholder="Search titles, summaries, topics, provisions…" autocomplete="off">',
        '<label for="judicialYearJump">Jump to docket year</label>',
        '<select id="judicialYearJump"><option value="">Choose a year…</option></select>',
        '<output id="judicialResultCount" aria-live="polite"></output>',
        '</section>',
        '<details class="judicial-catalogue-about"><summary>About this catalogue</summary>',
        f'<p>{len(rows)} records · {statuses["classified"]} classified · {statuses["needs_review"]} need editorial review. Canonical docket IDs are zero-padded; legacy, era-based, and Minutes identifiers are retained in each case’s details.</p>',
        '<p><a href="../docs/JUDICIAL-CASE-TAXONOMY.md">Read the taxonomy specification</a>.</p></details>',
        '<div class="judicial-catalogue" id="judicialCatalogue">',
    ]
    if overlays:
        registry_display = os.path.relpath(registry_path, os.path.dirname(output_path)).replace("\\", "/")
        lines.extend([
            '<aside class="judicial-candidate-notice"><strong>Candidate review rendering:</strong> '
            f"{len(overlays)} model-generated candidates from "
            f"<a href=\"{registry_display}\">{esc(os.path.basename(registry_path))}</a> overlay the maintained "
            "summary, matter type, and disposition for review. They have not been source-audited, "
            "approved, or published to the canonical editorial overrides. Follow the "
            '<a href="synopsis_workflow/AUDIT-INSTRUCTIONS.md">audit instructions</a>.</aside>',
        ])
    groups = {}
    for row in rows:
        docket = str(row.get("case_id") or row.get("roster_id") or "")
        year = docket.split("-", 1)[0] if docket[:4].isdigit() else "other"
        groups.setdefault(year, []).append(row)
    for year, year_rows in groups.items():
        lines.append(f'<section class="judicial-year" data-judicial-year="{esc(year)}"><h2>{esc(year if year != "other" else "Other roster records")}</h2>')
        lines.append('<div class="judicial-year__records">')
        for row in year_rows:
            row = dict(row)
            record_id = row.get("case_id") or row.get("roster_id")
            candidate = overlays.get(record_id) or overlays.get("roster:" + row.get("roster_id", ""))
            if candidate:
                row["summary"] = candidate["summary"]
                row["matter_type"] = candidate["matter_type"] or row.get("matter_type")
                row["final_dispositions"] = candidate["final_dispositions"] or row.get("final_dispositions")
            docket = row.get("case_id") or row.get("roster_id") or "Unnumbered"
            title = row.get("title") or "Untitled case"
            href = case_href(row)
            disposition = final_disposition(row)
            topic_values = row.get("topic_tags") or []
            visible_topics = topic_values[:3]
            hidden_topics = topic_values[3:]
            topic_markup = "".join(f'<span class="judicial-pill">{esc(x)}</span>' for x in visible_topics)
            if hidden_topics:
                topic_noun = "topic" if len(hidden_topics) == 1 else "topics"
                topics_id = "judicial-topics-" + "".join(ch if ch.isalnum() else "-" for ch in str(record_id))
                hidden_topic_markup = "".join(
                    f'<span class="judicial-pill">{esc(x)}</span>' for x in hidden_topics
                )
                topic_markup += (
                    f'<span class="judicial-case__topics-extra" id="{topics_id}" hidden>{hidden_topic_markup}</span>'
                    f'<button type="button" class="judicial-topics__toggle" '
                    f'aria-controls="{topics_id}" aria-expanded="false" '
                    f'aria-label="Show {len(hidden_topics)} more {topic_noun}" '
                    f'data-topic-count="{len(hidden_topics)}">+{len(hidden_topics)} {topic_noun}</button>'
                )
            aliases_text = aliases(row)
            bco_values = row.get("bco_provisions") or []
            bco_markup = ", ".join(f"BCO {esc(x)}" for x in bco_values) or "None listed"
            source_markup = f'<a href="{esc(href)}">{"Read case" if row.get("case_page") else "Official PDF"} <span aria-hidden="true">→</span></a>' if href else '<span class="judicial-source-missing">Full text unavailable</span>'
            status_markup = '' if row.get("classification_status") == "classified" else '<p class="judicial-review-status">Classification needs review</p>'
            title_markup = f'<a href="{esc(href)}">{esc(title)}</a>' if href else esc(title)
            summary_id = "judicial-summary-" + "".join(ch if ch.isalnum() else "-" for ch in str(record_id))
            details_id = "judicial-details-" + "".join(ch if ch.isalnum() else "-" for ch in str(record_id))
            lines.extend([
                f'<article class="judicial-case" id="case-{esc(docket)}" data-judicial-record data-search-text="{esc(" ".join(map(str, [docket, title, row.get("summary", ""), row.get("matter_type", ""), disposition, review_basis(row), aliases_text, bco_markup, " ".join(topic_values)])))}">',
                f'<header class="judicial-case__header"><p class="judicial-case__docket"><code>{esc(docket)}</code> <span>· {esc(MATTER_TYPE_LABELS.get(row.get("matter_type"), row.get("matter_type")) or "Matter")}</span><span class="judicial-saved-state" data-judicial-saved hidden> · Saved</span></p><h3>{title_markup}</h3></header>',
                f'<p class="judicial-case__outcome"><span>Outcome</span> {esc(disposition)}</p>',
                '<div class="judicial-case__layout">',
                '<div class="judicial-case__content">',
                f'<div class="judicial-case__summary-wrap"><p class="judicial-case__summary" id="{summary_id}">{esc(row.get("summary") or "Synopsis not available")}</p><button type="button" class="judicial-case__summary-toggle" aria-controls="{summary_id}" aria-expanded="false" hidden>Show full synopsis</button></div>',
                f'<div class="judicial-case__topics" aria-label="Topic tags"><span class="judicial-case__topics-label">Topics</span>{topic_markup or "<span class=\"judicial-muted\">None listed</span>"}</div>',
                '</div>',
                f'<aside class="judicial-case__rail" aria-label="Case actions">{source_markup}<button type="button" class="judicial-details__toggle" aria-controls="{details_id}" aria-expanded="false">Case details</button><div class="judicial-actions"><button type="button" class="judicial-actions__button" aria-haspopup="menu" aria-expanded="false" aria-label="More actions for {esc(title)}">⋯</button><div class="judicial-actions__menu" role="menu" hidden><button type="button" role="menuitem" data-judicial-action="save">Save to bookshelf</button><button type="button" role="menuitem" data-judicial-action="cite">Copy citation</button><button type="button" role="menuitem" data-judicial-action="link">Copy link</button></div></div></aside>',
                '</div>',
                f'<div class="judicial-details" id="{details_id}" hidden><dl><div><dt>Matter type</dt><dd>{esc(MATTER_TYPE_LABELS.get(row.get("matter_type"), row.get("matter_type")) or "Matter")}</dd></div><div><dt>Final disposition</dt><dd>{esc(final_disposition(row))}</dd></div><div><dt>Review basis</dt><dd>{esc(review_basis(row))}</dd></div><div><dt>BCO provisions</dt><dd>{bco_markup}</dd></div><div><dt>Aliases</dt><dd>{esc(aliases_text)}</dd></div><div><dt>All topic tags</dt><dd>{", ".join(esc(x) for x in topic_values) or "None listed"}</dd></div></dl>{status_markup}</div>',
                '</article>',
            ])
        lines.append('</div></section>')
    lines.append('</div>')
    with open(output_path, "w", encoding="utf-8", newline="\n") as target:
        target.write("\n".join(lines) + "\n")
    mode = f" with {len(overlays)} candidate overlays" if overlays else ""
    print(f"[taxonomy-index] wrote {len(rows)} rows{mode} -> {output_path}")


if __name__ == "__main__":
    main()
