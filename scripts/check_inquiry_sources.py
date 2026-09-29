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
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inquiry_records import load_inquiry_records


ANCHOR_RE = re.compile(r"^ga\d+-p\d+$")
ANCHOR_TAG_RE = re.compile(r'<a id="(ga\d+-p\d+)"')


def fail(errors: list[str], where: str, message: str) -> None:
    errors.append(f"{where}: {message}")


def phrase_hits(text: str, phrase: str) -> list[tuple[int, int]]:
    wanted = [m.group(0).casefold() for m in re.finditer(r"[\w]+", phrase, re.UNICODE)]
    source = [(m.group(0).casefold(), m.start(), m.end())
              for m in re.finditer(r"[\w]+", text, re.UNICODE)]
    if not wanted:
        return []
    return [(source[i][1], source[i + len(wanted) - 1][2])
            for i in range(max(0, len(source) - len(wanted) + 1))
            if [word for word, _, _ in source[i:i + len(wanted)]] == wanted]


def page_bounds(markdown: str) -> dict[str, tuple[int, int]]:
    anchors = list(re.finditer(r'<a\s+id="(ga\d+-p\d+)"\s*></a>', markdown))
    bounds: dict[str, tuple[int, int]] = {}
    for i, match in enumerate(anchors):
        if match.group(1) in bounds:
            bounds[match.group(1)] = (-1, -1)
            continue
        bounds[match.group(1)] = (
            match.end(), anchors[i + 1].start() if i + 1 < len(anchors) else len(markdown)
        )
    return bounds


def check_phrase_locator(errors: list[str], where: str, label: str, locator: object,
                         markdown: str, bounds: dict[str, tuple[int, int]]) -> None:
    if not isinstance(locator, dict):
        fail(errors, where, f"{label} must be an object")
        return
    start, end = locator.get("start"), locator.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        # Accept the original single-page representation during migration.
        anchor = locator.get("page_anchor")
        end_text = locator.get("end_after") or locator.get("end_before")
        if not anchor or not end_text or bool(locator.get("end_after")) == bool(locator.get("end_before")):
            fail(errors, where, f"{label} requires start/end page-and-phrase boundaries")
            return
        start = {"page_anchor": anchor, "text": locator.get("start_text", "")}
        end = {"page_anchor": anchor, "text": end_text,
               "inclusive": bool(locator.get("end_after"))}

    found: list[int] = []
    for side, boundary in (("start", start), ("end", end)):
        anchor = boundary.get("page_anchor")
        phrase = boundary.get("text")
        if not isinstance(anchor, str) or anchor not in bounds:
            fail(errors, where, f"{label}.{side} page anchor {anchor!r} is absent from the source")
            return
        left, right = bounds[anchor]
        if left < 0:
            fail(errors, where, f"{label}.{side} page anchor {anchor!r} is duplicated")
            return
        pdf_page = boundary.get("pdf_page")
        anchor_pdf_page = re.search(r"-p(\d+)$", anchor)
        if pdf_page is not None and (not isinstance(pdf_page, int) or not anchor_pdf_page
                                     or pdf_page != int(anchor_pdf_page.group(1))):
            fail(errors, where,
                 f"{label}.{side} pdf_page must match the physical PDF page in {anchor}")
            return
        if not isinstance(phrase, str) or not phrase.strip():
            fail(errors, where, f"{label}.{side} requires a non-empty text phrase")
            return
        hits = phrase_hits(markdown[left:right], phrase)
        if len(hits) != 1:
            fail(errors, where, f"{label}.{side} phrase must occur exactly once within {anchor}")
            return
        found.append(left + hits[0][0])
    if len(found) == 2 and found[0] > found[1]:
        fail(errors, where, f"{label} start must precede end")


def check_source(errors: list[str], where: str, stem: str, source: object,
                 role: str, markdown: str) -> None:
    if not isinstance(source, dict):
        fail(errors, where, f"{role} must be an object")
        return
    start, end = source.get("start"), source.get("end")
    locator = source.get("locator")
    if (not isinstance(locator, dict)
            and (not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start)):
        fail(errors, where, f"{role} requires positive inclusive start/end lines")
    anchor = source.get("page_anchor")
    if not isinstance(anchor, str) or not ANCHOR_RE.fullmatch(anchor):
        fail(errors, where, f"{role} requires a gaNN-pNNN page_anchor")
    elif f'id="{anchor}"' not in markdown:
        fail(errors, where, f"{role} page_anchor {anchor!r} is absent from {stem}.md")
    if isinstance(locator, dict):
        check_phrase_locator(errors, where, role + ".locator", locator, markdown,
                             page_bounds(markdown))
    page = source.get("printed_page")
    if not isinstance(locator, dict) and (not isinstance(page, int) or page < 1):
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


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
    records = load_inquiry_records(Path(root))
    errors: list[str] = []
    checked = 0
    phrase_located = 0
    review_needed = 0
    posed_only = 0

    for record in records:
        stem = record.get("stem", "")
        md_path = os.path.join(root, "markdown", f"{stem}.md")
        markdown = open(md_path, encoding="utf-8").read() if os.path.exists(md_path) else ""
        result = record["locator"]
        where = f"{stem} {record.get('minute_para', '?')} {record.get('topic', '?')}"
        bounds = page_bounds(markdown)
        migration = result.get("phrase_migration")
        if not isinstance(migration, dict) or migration.get("status") not in {
                "phrase_located", "posed_only", "needs_review"}:
            fail(errors, where, "phrase_migration must state phrase_located, posed_only, or needs_review")
        else:
            has_primary = bool(result.get("advice_locator")
                               or (result.get("substantive") or {}).get("locator"))
            status = migration["status"]
            if status == "phrase_located":
                phrase_located += 1
                if not has_primary:
                    fail(errors, where, "phrase_located requires an advice or substantive phrase locator")
            elif status == "needs_review":
                review_needed += 1
                if has_primary:
                    fail(errors, where, "needs_review record already has a primary phrase locator")
                if not migration.get("reason"):
                    fail(errors, where, "needs_review requires a reason")
            else:
                posed_only += 1
                if not result.get("posed_locator") or has_primary:
                    fail(errors, where, "posed_only requires a posed locator and no primary answer locator")
        for role in ("advice_locator", "posed_locator"):
            if result.get(role):
                check_phrase_locator(errors, where, role, result[role], markdown, bounds)
        if any(k.startswith("verbatim_") for k in result):
            fail(errors, where, "deprecated verbatim_* page overrides are not allowed; use substantive")
        substantive = result.get("substantive")
        action = result.get("assembly_action")
        if isinstance(substantive, dict) and substantive.get("locator"):
            check_phrase_locator(errors, where, "substantive.locator", substantive["locator"],
                                 markdown, bounds)
        if isinstance(action, dict) and action.get("locator"):
            check_phrase_locator(errors, where, "assembly_action.locator", action["locator"],
                                 markdown, bounds)
        if action is not None and substantive is None:
            fail(errors, where, "assembly_action requires a substantive Q&A source")
        if substantive is None:
            continue
        checked += 1
        check_source(errors, where, stem, substantive, "substantive", markdown)
        if substantive.get("kind") != "question_and_answer":
            fail(errors, where, "substantive.kind must be question_and_answer")
        start, end = substantive.get("start"), substantive.get("end")
        if (not substantive.get("locator") and isinstance(start, int) and isinstance(end, int)):
            text = "\n".join(markdown.splitlines()[start - 1:end])
            if "Constitutional Inquiry" not in text or "ANSWER" not in text:
                fail(errors, where, "substantive span must contain the inquiry and its ANSWER")
            expected_anchor = anchor_at(markdown, start)
            if expected_anchor and substantive.get("page_anchor") != expected_anchor:
                fail(errors, where,
                     f"substantive page_anchor must be {expected_anchor}, the page containing its Q&A")
        if action is not None:
            check_source(errors, where, stem, action, "assembly_action", markdown)
            a0, a1 = substantive.get("start"), substantive.get("end")
            b0, b1 = action.get("start"), action.get("end")
            if (not substantive.get("locator") and not action.get("locator")
                    and all(isinstance(v, int) for v in (a0, a1, b0, b1))
                    and max(a0, b0) <= min(a1, b1)):
                fail(errors, where, "substantive and assembly_action must be distinct spans")

    if errors:
        print("Inquiry source validation failed:", file=sys.stderr)
        print("\n".join(f"- {e}" for e in errors), file=sys.stderr)
        return 1
    print(f"[{root}] inquiry source validation passed: {phrase_located}/{len(records)} primary phrase locators, "
          f"{review_needed} need source review, {posed_only} posed-only; "
          f"{checked} explicit Q&A source record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
