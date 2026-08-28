#!/usr/bin/env python3
"""Group OCR-created continuation rows in the GA42 Hahn timeline tables."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "markdown" / "ga42_2014.md",
    ROOT / "cases" / "ga42_2014__2011-11_2011-12_2011-15_2011-16.md",
]
ROW = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
CELL = re.compile(r"<td(?:\s[^>]*)?>(.*?)</td>", re.DOTALL)
TABLE = re.compile(r"<table>.*?</table>", re.DOTALL)


def repair_table(match: re.Match[str]) -> str:
    rows = []
    for row_match in ROW.finditer(match.group(0)):
        cells = CELL.findall(row_match.group(1))
        if not cells:
            continue
        if len(cells) == 1 and rows:
            rows[-1][-1] += "<br>" + cells[0].strip()
        else:
            rows.append([cell.strip() for cell in cells])
    rendered = []
    for cells in rows:
        if len(cells) == 1:
            rendered.append(f"<tr><td colspan=\"2\">{cells[0]}</td></tr>")
        else:
            rendered.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return "<table><tbody>" + "".join(rendered) + "</tbody></table>"


def main() -> None:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        if path.name == "ga42_2014.md":
            marker = "### CASES 2011-11, 2011-12, 2011-15 and 2011-16"
            start = text.index(marker)
            end = text.index("### CASE 2011-14", start)
            before, section, after = text[:start], text[start:end], text[end:]
            section = TABLE.sub(repair_table, section)
            updated = before + section + after
        else:
            updated = TABLE.sub(repair_table, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
