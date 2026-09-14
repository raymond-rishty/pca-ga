#!/usr/bin/env python3
"""Audit case-content and Markdown regressions against a prior case revision.

The prior revision is a structural reference only.  This script does not copy
its words or modify case files.  It reports content similarity, body shrinkage,
Markdown block changes, provenance/page-marker changes, and likely severity.

Example::

    python scripts/67_audit_case_regressions.py \
      --ref c2a2cb85 --output build/case_regression_audit.json
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"<!--\s*PAGE\s+ga=(\d+)\s+pdf_page=(\d+)[^>]*-->")
SOURCE = re.compile(r"^\*Source:.*$", re.MULTILINE)
SEPARATOR = "\n---\n"
PIPE_TABLE = re.compile(r"(?:^\s*>?\s*\|.*(?:\n|$))+", re.MULTILINE)
HTML_TABLE = re.compile(r"<table\b", re.IGNORECASE)


def git_show(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    return result.stdout.replace("\r\n", "\n")


def normalize(text: str) -> str:
    text = PAGE.sub(" ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(char for char in text if char.isalnum())


def body(text: str) -> str:
    if SEPARATOR in text:
        return text.split(SEPARATOR, 1)[1].rsplit(SEPARATOR, 1)[0]
    return text


def count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def metrics(text: str) -> dict:
    value = body(text)
    headings = re.findall(r"^(#{1,6})\s+.+$", value, re.MULTILINE)
    return {
        "raw_chars": len(value),
        "normalized_chars": len(normalize(value)),
        "page_markers": len(PAGE.findall(value)),
        "headings": len(headings),
        "heading_levels": {str(level): sum(len(item) == level for item in headings) for level in range(1, 7)},
        "lists": count(value, r"^\s*(?:[-*+]\s+|\d+[.)]\s+)"),
        # PP-Structure emits both pipe tables and HTML tables; blockquoted
        # pipe rows are also valid Markdown tables in the main reference.
        "tables": len(PIPE_TABLE.findall(value)) + len(HTML_TABLE.findall(value)),
        "blockquotes": count(value, r"^\s*>\s?"),
        "double_quotes": value.count('"') + value.count("“") + value.count("”"),
        "single_quotes": value.count("'") + value.count("‘") + value.count("’"),
        "blank_paragraphs": count(value, r"\n\s*\n"),
    }


def page_numbers(text: str) -> list[int]:
    return [int(page) for _ga, page in PAGE.findall(body(text))]


def source_line(text: str) -> str | None:
    match = SOURCE.search(text)
    return match.group(0).strip() if match else None


def flags(old: dict, new: dict, similarity: float, old_source: str | None, new_source: str | None) -> list[str]:
    result: list[str] = []
    if not new_source:
        result.append("missing_provenance")
    if old_source != new_source:
        result.append("provenance_changed")
    if new["page_markers"] < old["page_markers"]:
        result.append("page_marker_loss")
    if new["headings"] < old["headings"]:
        result.append("heading_loss")
    if new["lists"] < old["lists"]:
        result.append("list_loss")
    if new["tables"] < old["tables"]:
        result.append("table_loss")
    if new["normalized_chars"] < old["normalized_chars"] * 0.90:
        result.append("body_shrink")
    if similarity < 0.90:
        result.append("low_normalized_similarity")
    if abs(new["double_quotes"] - old["double_quotes"]) >= 4 or abs(new["single_quotes"] - old["single_quotes"]) >= 8:
        result.append("quote_style_change")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="c2a2cb85")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-similarity", type=float, default=0.90)
    args = parser.parse_args()

    names = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", args.ref, "--", "cases"],
        cwd=ROOT,
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=True,
    ).stdout.splitlines()
    rows: list[dict] = []
    for path in names:
        current_path = ROOT / path
        if not current_path.exists():
            continue
        old_text = git_show(args.ref, path)
        new_text = current_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        old_body = body(old_text)
        new_body = body(new_text)
        old_normalized = normalize(old_body)
        new_normalized = normalize(new_body)
        similarity = difflib.SequenceMatcher(None, old_normalized, new_normalized).ratio()
        old_metrics = metrics(old_text)
        new_metrics = metrics(new_text)
        old_pages = page_numbers(old_text)
        new_pages = page_numbers(new_text)
        row = {
            "case_file": path,
            "similarity": round(similarity, 4),
            "old_pages": old_pages,
            "new_pages": new_pages,
            "old": old_metrics,
            "new": new_metrics,
            "deltas": {key: new_metrics[key] - old_metrics[key] for key in (
                "raw_chars", "normalized_chars", "page_markers", "headings", "lists",
                "tables", "blockquotes", "double_quotes", "single_quotes", "blank_paragraphs",
            )},
            "flags": flags(old_metrics, new_metrics, similarity, source_line(old_text), source_line(new_text)),
        }
        rows.append(row)

    flagged = [row for row in rows if row["flags"]]
    summary = {
        "ref": args.ref,
        "cases": len(rows),
        "flagged": len(flagged),
        "similarity_below_threshold": sum(row["similarity"] < args.min_similarity for row in rows),
        "flag_counts": {
            flag: sum(flag in row["flags"] for row in rows)
            for flag in sorted({flag for row in rows for flag in row["flags"]})
        },
    }
    payload = {"summary": summary, "cases": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
