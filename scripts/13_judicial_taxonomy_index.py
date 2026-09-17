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
import re
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


SITE_BASEURL = "/pca-ga"


def case_href(row):
    if row.get("case_page"):
        # This catalogue is also previewed from the site root.  A parent-relative
        # link therefore drops GitHub Pages' /pca-ga base path; use the deployed
        # path explicitly and point at the rendered case page.
        return f"{SITE_BASEURL}/cases/{row['case_page']}.html"
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
        values.append(f"legacy {row['legacy_case_id']}")
    if row.get("era_label"):
        values.append(str(row["era_label"]))
    if row.get("minute_ids"):
        values.append("Minutes " + ", ".join(str(x) for x in row["minute_ids"]))
    return "; ".join(values) or "—"


def citation_title(title):
    """Return the compact party caption used in copied case citations.

    The catalogue keeps the full editorial title in the heading, but copied
    citations follow the convention used in the printed indexes: surnames and
    presbytery names are enough to identify the case without repeating a long
    caption.
    """
    text = re.sub(r"\s+Presbytery\b", "", str(title or ""), flags=re.I)
    match = re.split(r"\s+v(?:s?\.)?\s+", text, maxsplit=1, flags=re.I)
    if len(match) != 2:
        return text.strip()

    def party(value):
        value = re.sub(r"^\s*(?:TE|RE|Rev\.?|Elder)\s+", "", value.strip(), flags=re.I)
        value = re.sub(r"\s+et\.?\s+al\.\s*$", " et al.", value, flags=re.I)
        if re.search(r"\b(?:Session|Church|PCA|Presbytery)\b", value, flags=re.I):
            return value
        pieces = re.split(r"\s+(?:and|&)\s+", value, flags=re.I)
        compact = []
        for piece in pieces:
            suffix = " et al." if re.search(r"\bet\.?\s+al\.\s*$", piece, flags=re.I) else ""
            piece = re.sub(r"\s+et\.?\s+al\.\s*$", "", piece, flags=re.I).strip()
            words = piece.split()
            compact.append((words[-1] if len(words) > 1 else piece) + suffix)
        return " and ".join(compact)

    respondent = match[1].strip()
    respondent = re.sub(r"\bMetropolitan New York\b", "Metro NY", respondent, flags=re.I)
    respondent = re.sub(r"\bPresbytery\b", "", respondent, flags=re.I).strip()
    return f"{party(match[0])} v. {respondent}".strip()


def citation_key(value):
    match = re.fullmatch(r"(\d{4})-(\d+)([a-z]?)", str(value or "").strip(), flags=re.I)
    if not match:
        return str(value or "").strip().lower()
    return f"{match.group(1)}-{int(match.group(2)):02d}{match.group(3).lower()}"


def load_source_records(root):
    """Load printed-page metadata from the legacy case index."""
    path = os.path.join(root, "index", "cases.jsonl")
    records = {}
    if not os.path.exists(path):
        return records
    with open(path, encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            for key in (record.get("case_number"), record.get("case_id")):
                if key:
                    records.setdefault(citation_key(key), record)
    return records


def source_citation(row, source_records, root=None):
    source = source_records.get(citation_key(row.get("case_id")), {})
    page_volume = None
    page_start = page_end = None
    if root and row.get("case_page"):
        case_path = os.path.join(root, "cases", f"{row['case_page']}.md")
        if os.path.exists(case_path):
            with open(case_path, encoding="utf-8") as case_file:
                head = case_file.read(2500)
            volume = re.search(r"\bga(\d+)_", row["case_page"], flags=re.I)
            pages = re.search(r"\*Source:\s*\[[^\]]+\s+(pp?\.\s*\d+)(?:\s*[–-]\s*(\d+))?", head, flags=re.I)
            if volume:
                page_volume = int(volume.group(1))
            if pages:
                page_start = int(pages.group(1).split(".", 1)[1].strip())
                page_end = int(pages.group(2)) if pages.group(2) else None
    source_matches_page = (
        source.get("printed_page_start")
        and (not page_volume or source.get("ga_ordinal") == page_volume)
    )
    assembly = page_volume or row.get("assembly") or source.get("ga_ordinal")
    if source_matches_page:
        start = source.get("printed_page_start")
        end = source.get("printed_page_end")
    else:
        start = page_start
        end = page_end
    start = start or source.get("printed_page_start")
    end = end or source.get("printed_page_end")
    if not assembly:
        return ""
    result = f"M{assembly}GA"
    if start:
        pages = f"p. {start}" if not end or end == start else f"pp. {start}–{end}"
        result += f", {pages}"
    return result


def detail_pills(values, prefix=""):
    """Render compact, readable pills for repeated metadata values."""
    if not values:
        return '<span class="judicial-muted">None listed</span>'
    pills = "".join(
        f'<span class="judicial-detail-pill">{esc(prefix + str(value))}</span>'
        for value in values
    )
    return f'<span class="judicial-detail-pills">{pills}</span>'


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
    source_records = load_source_records(root)
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
            compact_title = citation_title(title)
            source_ref = source_citation(row, source_records, root)
            short_citation = f"{docket} {compact_title}".strip()
            full_citation = f"Case {docket}: {compact_title}"
            if source_ref:
                full_citation += f", {source_ref}"
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
            bco_text = ", ".join(f"BCO {x}" for x in bco_values) or "None listed"
            bco_markup = detail_pills(bco_values, prefix="BCO ")
            topic_details_markup = detail_pills(topic_values)
            source_markup = f'<a href="{esc(href)}">{"Read case" if row.get("case_page") else "Official PDF"} <span aria-hidden="true">→</span></a>' if href else '<span class="judicial-source-missing">Full text unavailable</span>'
            status_markup = '' if row.get("classification_status") == "classified" else '<p class="judicial-review-status">Classification needs review</p>'
            title_markup = f'<a href="{esc(href)}">{esc(title)}</a>' if href else esc(title)
            summary_id = "judicial-summary-" + "".join(ch if ch.isalnum() else "-" for ch in str(record_id))
            details_id = "judicial-details-" + "".join(ch if ch.isalnum() else "-" for ch in str(record_id))
            lines.extend([
                f'<article class="judicial-case" id="case-{esc(docket)}" data-judicial-record data-judicial-short-citation="{esc(short_citation)}" data-judicial-full-citation="{esc(full_citation)}" data-search-text="{esc(" ".join(map(str, [docket, title, row.get("summary", ""), row.get("matter_type", ""), disposition, review_basis(row), aliases_text, bco_text, " ".join(topic_values)])))}">',
                f'<header class="judicial-case__header"><p class="judicial-case__docket"><code>{esc(docket)}</code> <span>· {esc(MATTER_TYPE_LABELS.get(row.get("matter_type"), row.get("matter_type")) or "Matter")}</span><span class="judicial-saved-state" data-judicial-saved hidden> · Saved</span></p><h3>{title_markup}</h3></header>',
                f'<p class="judicial-case__outcome"><span>Outcome</span> {esc(disposition)}</p>',
                '<div class="judicial-case__layout">',
                '<div class="judicial-case__content">',
                f'<div class="judicial-case__summary-wrap"><p class="judicial-case__summary" id="{summary_id}">{esc(row.get("summary") or "Synopsis not available")}</p><button type="button" class="judicial-case__summary-toggle" aria-controls="{summary_id}" aria-expanded="false" hidden>Show full synopsis</button></div>',
                f'<div class="judicial-case__topics" aria-label="Topic tags"><span class="judicial-case__topics-label">Topics</span>{topic_markup or "<span class=\"judicial-muted\">None listed</span>"}</div>',
                '</div>',
                f'<aside class="judicial-case__rail" aria-label="Case actions">{source_markup}<button type="button" class="judicial-details__toggle" aria-controls="{details_id}" aria-expanded="false">Case details</button><div class="judicial-actions"><button type="button" class="judicial-actions__button" aria-haspopup="menu" aria-expanded="false" aria-label="Case actions" title="Case actions">Actions</button><div class="judicial-actions__menu" role="menu" hidden><button type="button" role="menuitem" data-judicial-action="save">Save to bookshelf</button><button type="button" role="menuitem" data-judicial-action="cite">Copy citation</button><button type="button" role="menuitem" data-judicial-action="link">Copy link</button></div></div></aside>',
                '</div>',
                f'<div class="judicial-details" id="{details_id}" hidden><dl><div><dt>Matter type</dt><dd>{esc(MATTER_TYPE_LABELS.get(row.get("matter_type"), row.get("matter_type")) or "Matter")}</dd></div><div><dt>Final disposition</dt><dd>{esc(final_disposition(row))}</dd></div><div><dt>Review basis</dt><dd>{esc(review_basis(row))}</dd></div><div><dt>BCO provisions</dt><dd>{bco_markup}</dd></div><div><dt>Aliases</dt><dd>{esc(aliases_text)}</dd></div><div><dt>All topic tags</dt><dd>{topic_details_markup}</dd></div></dl>{status_markup}</div>',
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
