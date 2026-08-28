#!/usr/bin/env python3
"""Apply adjudicated neighboring-case boundary repairs to case Markdown."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Each rule was reviewed against the corrected minutes.  A cut_heading rule
# keeps the indexed page and removes the following case from the same page;
# a cut_page rule drops pages that belong entirely to the following case.
RULES = [
    {"path": "cases/ga03_1975__case1.md", "cut_heading": "### 3-13 Report of the Constitutional Documents Committee"},
    {"path": "cases/ga11_1983__case1.md", "cut_heading": "### CASE 7"},
    {"path": "cases/ga11_1983__case4.md", "cut_page": "<!-- PAGE ga=11 pdf_page=152"},
    {"path": "cases/ga11_1983__case10.md", "cut_page": "<!-- PAGE ga=11 pdf_page=150"},
    {"path": "cases/ga26_1998__1997-11.md", "cut_heading": "### 9. COMPLAINT, CASE 97-13"},
    {"path": "cases/ga33_2005__2004-07.md", "cut_page": "<!-- PAGE ga=33 pdf_page=146"},
    {"path": "cases/ga44_2016__2015-03.md", "cut_heading": "### CASE 2015-04"},
    {"path": "cases/ga46_2018__2016-10.md", "cut_heading": "### CASE 2016-11"},
    {"path": "cases/ga17_1989__case3.md", "cut_page": "<!-- PAGE ga=17 pdf_page=229"},
]

SOURCE_UPDATES = {
    "cases/ga11_1983__case4.md": ("pp. 150–152", "pp. 150–151"),
    "cases/ga11_1983__case10.md": ("pp. 148–150", "pp. 148–149"),
    "cases/ga17_1989__case3.md": ("pp. 209–227", "pp. 209–228"),
}


def apply_rule(text: str, rule: dict[str, str]) -> str:
    separator = "\n---\n"
    body_end = text.rfind(separator)
    if body_end < 0:
        raise ValueError(f"missing wrapper separator: {rule['path']}")
    body = text[:body_end]
    if "cut_heading" in rule:
        marker = "\n" + rule["cut_heading"]
        if marker not in body:
            return text
        body = body.split(marker, 1)[0]
    else:
        marker = rule["cut_page"]
        position = body.find(marker)
        if position < 0:
            return text
        body = body[:position].rstrip()
    return body.rstrip() + text[body_end:]


def main() -> None:
    for rule in RULES:
        path = ROOT / rule["path"]
        original = path.read_text(encoding="utf-8")
        updated = apply_rule(original, rule)
        if rule["path"] in SOURCE_UPDATES:
            old, new = SOURCE_UPDATES[rule["path"]]
            if new in updated:
                continue
            if old not in updated:
                raise ValueError(f"source range not found: {rule['path']} / {old}")
            updated = updated.replace(old, new, 1)
        path.write_text(updated, encoding="utf-8")
        print(rule["path"])


if __name__ == "__main__":
    main()
