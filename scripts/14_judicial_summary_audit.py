#!/usr/bin/env python3
"""Audit judicial-case synopsis coverage against the available source layer.

This is a conservative editorial gate, not a text generator. It marks an
existing synopsis audited only when it is long enough to identify the dispute
and disposition, and when the case has a local decision page, an official
decision PDF, or an official catalog record. Short, placeholder, and issue-
only synopses remain pending for human editing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IDX = ROOT / "index"
CASES = ROOT / "cases"
INPUT = IDX / "judicial_cases.jsonl"
OUTPUT = IDX / "judicial_case_summary_audits.json"

ISSUE_RE = re.compile(
    r"\b(challeng|complain|appeal|alleg|dispute|question|issue|regarding|concern|request|petition|charge|accus|err|violation|disciplin|ordination|licens|membership|jurisdiction|divest|excommun|censure|remand|withdraw)\w*\b",
    re.I,
)
DISPOSITION_RE = re.compile(
    r"\b(sustain|deny|denied|dismiss|out of order|abandon|withdraw|withdrew|remand|refer|revers|affirm|annul|judgment|moot|granted|not in order|found in order|no merits|no opinion|final disposition|source-recovery|order|instruct|direct|recommend|invalid|valid|constitutional|properly|error|err|violation|decision|excommun|censure|divest|accept|acceptable|resolve|response|forward|remit|satisfactor|compli)\w*\b",
    re.I,
)
PLACEHOLDER_RE = re.compile(
    r"(?i)(^\s*(see also|in re|alleged p\b)|\b(summary|issue):?\s*$|\bthe assembly found case\b|\bis$|\bcase \d+\b.*\bappointed a judicial commission\b)",
)


def read_rows():
    with INPUT.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def source_info(row):
    page = row.get("case_page")
    page_path = CASES / f"{page}.md" if page else None
    if page_path and page_path.exists() and "stub" not in page:
        return "case_page", page_path.read_text(encoding="utf-8")
    if row.get("official_pdf_url"):
        return "official_decision_pdf", ""
    return "official_catalog", ""


def audit(row):
    summary = " ".join((row.get("summary") or "").split())
    source, text = source_info(row)
    flags = []
    source_recovery = "source-recovery" in summary
    procedural = row.get("outcome") in {"abandoned", "out_of_order", "dismissed", "administrative", "in_order"} or "moot" in summary.lower()
    if len(summary) < (80 if procedural or source_recovery else 180):
        flags.append("short")
    administrative_record = row.get("outcome") in {"administrative", "referred"} or row.get("proceeding_type") == "review_and_control"
    if not procedural and not source_recovery and not administrative_record and not ISSUE_RE.search(summary):
        flags.append("no_issue_signal")
    if not DISPOSITION_RE.search(summary):
        flags.append("no_disposition_signal")
    if PLACEHOLDER_RE.search(summary):
        flags.append("placeholder_or_issue_only")
    if source == "case_page" and text and not re.search(r"(?i)(judgment|disposition|sustain|deny|dismiss|out of order|abandon|withdraw|remand|refer|annul|affirm|accept|acceptable|resolve|response|forward|remit|satisfactor|compli)", text):
        flags.append("source_has_no_decision_signal")
    status = "audited" if not flags else "pending_audit"
    return {
        "summary_review_status": status,
        "summary_source": source,
        "summary_audit_basis": "source-presence-and-summary-quality-v1",
        "flags": flags,
    }


def main():
    audits = {row["case_id"]: audit(row) for row in read_rows() if row.get("case_id")}
    OUTPUT.write_text(json.dumps(audits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {}
    flagged = []
    for cid, result in audits.items():
        counts[result["summary_review_status"]] = counts.get(result["summary_review_status"], 0) + 1
        if result["flags"]:
            flagged.append((cid, result["flags"]))
    print(f"[summary-audit] wrote {len(audits)} rows -> {OUTPUT}")
    print(f"[summary-audit] status={counts}")
    print(f"[summary-audit] flagged={len(flagged)}")
    for cid, flags in flagged[:40]:
        print(f"  {cid}: {', '.join(flags)}")


if __name__ == "__main__":
    main()
