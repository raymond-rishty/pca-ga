#!/usr/bin/env python3
"""Validate explicit source roles in constitutional-inquiry locators.

The legacy locator fields describe a single journal passage.  Where an appendix
contains the substantive question-and-answer and the journal has a separate
adopting action, `substantive` is the primary research source and
`assembly_action` is secondary.  This check prevents a future rebuild from
quietly treating the action page as the inquiry itself.
"""
from __future__ import annotations

import json
import os
import re
import sys


ANCHOR_RE = re.compile(r"^ga\d+-p\d+$")
ANCHOR_TAG_RE = re.compile(r'<a id="(ga\d+-p\d+)"')


def fail(errors: list[str], where: str, message: str) -> None:
    errors.append(f"{where}: {message}")


def check_source(errors: list[str], where: str, stem: str, source: object,
                 role: str, markdown: str) -> None:
    if not isinstance(source, dict):
        fail(errors, where, f"{role} must be an object")
        return
    start, end = source.get("start"), source.get("end")
    stable_locator = source.get("text_locator")
    has_lines = (isinstance(start, int) and isinstance(end, int)
                 and start >= 1 and end >= start)
    if not has_lines and not isinstance(stable_locator, dict):
        fail(errors, where, f"{role} requires either positive inclusive lines or a text_locator")
    anchor = source.get("page_anchor")
    if not isinstance(anchor, str) or not ANCHOR_RE.fullmatch(anchor):
        fail(errors, where, f"{role} requires a gaNN-pNNN page_anchor")
    elif f'id="{anchor}"' not in markdown:
        fail(errors, where, f"{role} page_anchor {anchor!r} is absent from {stem}.md")
    page = source.get("printed_page")
    if not isinstance(page, int) or page < 1:
        fail(errors, where, f"{role} requires a positive printed_page")


def anchor_at(markdown: str, line_number: int) -> str | None:
    """Return the markdown page anchor in force at a one-based line number."""
    current = None
    for n, line in enumerate(markdown.splitlines(), 1):
        match = ANCHOR_TAG_RE.search(line)
        if match:
            current = match.group(1)
        if n >= line_number:
            return current
    return current


def marker_line(lines: list[str], marker: str, after: int = 0) -> int | None:
    """Find a durable text marker and return its zero-based line, ignoring punctuation."""
    wanted = re.findall(r"[a-z0-9]+", marker.casefold())
    if not wanted:
        return None
    tokens = [(match.group(0), index)
              for index, line in enumerate(lines)
              for match in re.finditer(r"[a-z0-9]+", line.casefold())]
    for offset in range(len(tokens) - len(wanted) + 1):
        window = tokens[offset:offset + len(wanted)]
        if window[0][1] >= after and [token for token, _ in window] == wanted:
            return window[0][1]
    return None


def resolve_text_locator(markdown: str, locator: object) -> tuple[int, int] | None:
    if not isinstance(locator, dict):
        return None
    lines = markdown.splitlines()
    start = marker_line(lines, str(locator.get("start_text") or ""))
    end_before = marker_line(lines, str(locator.get("end_before") or ""),
                             start + 1 if start is not None else 0)
    if start is None or end_before is None or end_before <= start:
        return None
    return start + 1, end_before


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
    path = os.path.join(root, "index", "inquiries.jsonl")
    records = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    errors: list[str] = []
    checked = 0

    for record in records:
        stem = record.get("minutes_volume", "")
        md_path = os.path.join(root, "markdown", f"{stem}.md")
        markdown = open(md_path, encoding="utf-8").read() if os.path.exists(md_path) else ""
        where = f"{record.get('inquiry_id', '?')} {record.get('minute_para', '?')} {record.get('digest_topic', '?')}"
        if any(k.startswith("verbatim_") for k in record):
            fail(errors, where, "deprecated verbatim_* page overrides are not allowed; use substantive")
        substantive = record.get("substantive")
        action = record.get("assembly_action")
        if action is not None and substantive is None:
            fail(errors, where, "assembly_action requires a substantive Q&A source")
        if substantive is None:
            continue
        checked += 1
        check_source(errors, where, stem, substantive, "substantive", markdown)
        if substantive.get("kind") != "question_and_answer":
            fail(errors, where, "substantive.kind must be question_and_answer")
        stable_locator = substantive.get("text_locator")
        if isinstance(stable_locator, dict):
            span = resolve_text_locator(markdown, stable_locator)
            if span is None:
                fail(errors, where, "substantive text_locator markers were not found in order")
            else:
                start, end = span
                text = "\n".join(markdown.splitlines()[start - 1:end])
                if "Constitutional Inquiry" not in text or "ANSWER" not in text:
                    fail(errors, where, "substantive locator span must contain the inquiry and its ANSWER")
                expected_anchor = anchor_at(markdown, start)
                if expected_anchor and substantive.get("page_anchor") != expected_anchor:
                    fail(errors, where,
                         f"substantive page_anchor must be {expected_anchor}, the page containing its Q&A")
        else:
            start, end = substantive.get("start"), substantive.get("end")
            if isinstance(start, int) and isinstance(end, int):
                text = "\n".join(markdown.splitlines()[start - 1:end])
                if "Constitutional Inquiry" not in text or "ANSWER" not in text:
                    fail(errors, where, "substantive span must contain the inquiry and its ANSWER")
                expected_anchor = anchor_at(markdown, start)
                if expected_anchor and substantive.get("page_anchor") != expected_anchor:
                    fail(errors, where,
                         f"substantive page_anchor must be {expected_anchor}, the page containing its Q&A")
        if action is not None:
            check_source(errors, where, stem, action, "assembly_action", markdown)
            action_locator = action.get("text_locator")
            action_span = None
            if isinstance(action_locator, dict):
                action_span = resolve_text_locator(markdown, action_locator)
                if action_span is None:
                    fail(errors, where, "assembly_action text_locator markers were not found in order")
                else:
                    expected_anchor = anchor_at(markdown, action_span[0])
                    if expected_anchor and action.get("page_anchor") != expected_anchor:
                        fail(errors, where,
                             f"assembly_action page_anchor must be {expected_anchor}, the page containing the action")
            substantive_span = resolve_text_locator(markdown, stable_locator) if isinstance(stable_locator, dict) else None
            a0, a1 = substantive_span or (substantive.get("start"), substantive.get("end"))
            b0, b1 = action_span or (action.get("start"), action.get("end"))
            if all(isinstance(v, int) for v in (a0, a1, b0, b1)) and max(a0, b0) <= min(a1, b1):
                fail(errors, where, "substantive and assembly_action must be distinct spans")

    if errors:
        print("Inquiry source validation failed:", file=sys.stderr)
        print("\n".join(f"- {e}" for e in errors), file=sys.stderr)
        return 1
    print(f"[{root}] inquiry source validation passed ({checked} explicit Q&A source record(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
