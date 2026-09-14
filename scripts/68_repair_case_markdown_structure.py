#!/usr/bin/env python3
"""Restore high-confidence Markdown structure without replacing current text.

The current case body remains authoritative for OCR words, page ranges, and
page markers.  A prior case revision supplies only structural prefixes when a
normalized line aligns uniquely: heading levels, list markers, and headings
that became plain text.  Tables and ambiguous/low-similarity cases are left
for separate review.
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
SEPARATOR = "\n---\n"
PAGE = re.compile(r"^<!--\s*PAGE\s+ga=\d+\s+pdf_page=\d+[^>]*-->\s*$")
HEADING = re.compile(r"^(#{1,6})(\s+)(.*)$")
LIST = re.compile(r"^(\s*)((?:(?:[-*+]\s+)|(?:\d+[.)]\s+)|(?:[A-Za-z][.)]\s+)|(?:[-*+]\s+\*\*[A-Za-z][.)]\*\*\s+)))(.*)$")


def git_show(ref: str, path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, check=True,
        text=True, encoding="utf-8", capture_output=True,
    ).stdout.replace("\r\n", "\n")


def body(text: str) -> str:
    if SEPARATOR in text:
        return text.split(SEPARATOR, 1)[1].rsplit(SEPARATOR, 1)[0]
    return text


def replace_body(page: str, new_body: str) -> str:
    parts = page.split(SEPARATOR)
    if len(parts) < 3:
        raise ValueError("case page has no replaceable body delimiters")
    return SEPARATOR.join([parts[0], "\n" + new_body.strip() + "\n", *parts[2:]]).rstrip() + "\n"


def normalized(line: str) -> str:
    line = re.sub(r"<!--.*?-->", " ", line)
    line = re.sub(r"<[^>]+>", " ", line)
    line = re.sub(r"^[#>*+\-|\s]+", " ", line)
    line = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|[A-Za-z][.)]\s+)", " ", line)
    line = re.sub(r"\*\*|__|[*_`]", "", line)
    line = unicodedata.normalize("NFKC", line).casefold()
    return "".join(char for char in line if char.isalnum())


def kind_and_prefix(line: str) -> tuple[str, str, str] | None:
    match = HEADING.match(line)
    if match:
        return "heading", match.group(1), match.group(3)
    match = LIST.match(line)
    if match:
        return "list", match.group(1) + match.group(2), match.group(3)
    if line.lstrip().startswith("|"):
        return "table", "", line
    if normalized(line) and not line.strip().startswith("<!--"):
        return "plain", "", line
    return None


def similarity(old: str, new: str) -> float:
    return difflib.SequenceMatcher(None, normalized(old), normalized(new)).ratio()


def structural_overlay(current: str, reference: str, min_similarity: float) -> tuple[str, dict]:
    current_body = body(current)
    reference_body = body(reference)
    whole = difflib.SequenceMatcher(None, normalized(reference_body), normalized(current_body)).ratio()
    report = {"whole_similarity": round(whole, 4), "changes": [], "skipped": None}
    old_normalized = normalized(reference_body)
    new_normalized = normalized(current_body)
    if whole < min_similarity or len(new_normalized) < len(old_normalized) * 0.95:
        report["skipped"] = "low_similarity"
        return current, report

    old_lines = reference_body.splitlines()
    new_lines = current_body.splitlines()
    old_by_norm: dict[str, list[int]] = {}
    for index, line in enumerate(old_lines):
        key = normalized(line)
        if len(key) >= 8 and kind_and_prefix(line):
            old_by_norm.setdefault(key, []).append(index)

    cursor = 0
    output = list(new_lines)
    for new_index, line in enumerate(new_lines):
        key = normalized(line)
        candidates = [index for index in old_by_norm.get(key, []) if index >= cursor]
        if not candidates or len(candidates) > 1:
            continue
        old_index = candidates[0]
        cursor = old_index + 1
        old_shape = kind_and_prefix(old_lines[old_index])
        new_shape = kind_and_prefix(line)
        if not old_shape or not new_shape:
            continue
        old_kind, old_prefix, old_content = old_shape
        new_kind, _new_prefix, new_content = new_shape
        if old_kind == "table" or new_kind == "table":
            continue
        if old_kind == "heading" and new_kind in {"heading", "plain"}:
            desired = f"{old_prefix} {new_content}"
            if desired != line:
                output[new_index] = desired
                report["changes"].append({"line": new_index + 1, "from": line, "to": desired, "kind": "heading"})
        # Keep current list markers.  Marker style is often a deliberate
        # rendering choice and is not enough evidence of OCR/layout damage.

    if report["changes"]:
        return replace_body(current, "\n".join(output)), report
    report["skipped"] = "no_structural_changes"
    return current, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="main")
    parser.add_argument("--min-similarity", type=float, default=0.90)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / "build" / "case_structure_repair_report.json")
    args = parser.parse_args()

    paths = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", args.ref, "--", "cases"],
        cwd=ROOT, check=True, text=True, encoding="utf-8", capture_output=True,
    ).stdout.splitlines()
    rows = []
    for path in paths:
        target = ROOT / path
        if not target.exists():
            continue
        current = target.read_text(encoding="utf-8").replace("\r\n", "\n")
        reference = git_show(args.ref, path)
        updated, report = structural_overlay(current, reference, args.min_similarity)
        report["case_file"] = path
        report["applied"] = bool(args.apply and updated != current)
        if args.apply and updated != current:
            target.write_text(updated, encoding="utf-8")
        rows.append(report)

    payload = {
        "ref": args.ref,
        "min_similarity": args.min_similarity,
        "apply": args.apply,
        "cases": len(rows),
        "changed": sum(bool(row["changes"]) for row in rows),
        "applied": sum(row["applied"] for row in rows),
        "structural_changes": sum(len(row["changes"]) for row in rows),
        "rows": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("cases", "changed", "applied", "structural_changes")}, indent=2))


if __name__ == "__main__":
    main()
