#!/usr/bin/env python3
"""Put the complete GA42 Hahn chronology into page-aware two-column tables."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "markdown" / "ga42_2014.md",
    ROOT / "cases" / "ga42_2014__2011-11_2011-12_2011-15_2011-16.md",
]
PAGE = re.compile(r"^<!-- PAGE ga=42 pdf_page=\d+[^>]*-->\s*$", re.MULTILINE)
TABLE = re.compile(r"<table>.*?</table>", re.DOTALL)
ROW = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
CELL = re.compile(r"<td(?:\s[^>]*)?>(.*?)</td>", re.DOTALL)
DATE = re.compile(r"^\s*(\d{1,2}/\d{1,2}(?:-\d{1,2})?/\d{1,2}|\d{1,2}/\d{1,2}/\d{2}|December 2010)\b")


def table_rows(raw: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for match in ROW.finditer(raw):
        cells = [cell.strip() for cell in CELL.findall(match.group(1))]
        if not cells:
            continue
        if len(cells) >= 2:
            cells[1] = re.sub(r"^(?:<br>)+", "", cells[1])
        rows.append(cells)
    return rows


def render_rows(rows: list[list[str]]) -> str:
    paragraphs = []
    rendered = []
    for cells in rows:
        if len(cells) == 1:
            if cells[0].startswith("instruction by the CBPD"):
                paragraphs.append(cells[0])
            else:
                rendered.append(f"<tr><td></td><td>{cells[0]}</td></tr>")
        else:
            rendered.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    prefix = "\n\n".join(paragraphs)
    table = "<table><tbody>" + "".join(rendered) + "</tbody></table>"
    return (prefix + "\n\n" if prefix else "") + table


def dated_row(paragraph: str) -> list[str] | None:
    match = DATE.match(paragraph)
    if not match:
        return None
    event = paragraph[match.end():].strip().replace("\n", "<br>")
    event = re.sub(r"^(?:<br>)+", "", event)
    return [match.group(1), event]


def repair_section(section: str) -> str:
    matches = list(PAGE.finditer(section))
    if not matches:
        raise ValueError("Hahn timeline has no page markers")
    pieces = []
    for index, marker in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        chunk = section[marker.end():end]
        rows: list[list[str]] = []
        cursor = 0
        for table_match in TABLE.finditer(chunk):
            prose = chunk[cursor:table_match.start()]
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
            for paragraph in paragraphs:
                dated = dated_row(paragraph)
                if dated:
                    rows.append(dated)
                elif rows and len(rows[-1]) >= 2 and not rows[-1][1]:
                    rows[-1][1] = paragraph.replace("\n", "<br>")
                else:
                    rows.append([paragraph])
            rows.extend(table_rows(table_match.group(0)))
            cursor = table_match.end()
        prose = chunk[cursor:]
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
        for paragraph in paragraphs:
            dated = dated_row(paragraph)
            if dated:
                rows.append(dated)
            elif rows and len(rows[-1]) >= 2 and not rows[-1][1]:
                rows[-1][1] = paragraph.replace("\n", "<br>")
            else:
                rows.append([paragraph])
        pieces.append(section[marker.start():marker.end()] + "\n\n" + render_rows(rows))
    return "\n\n".join(pieces) + "\n\n"


def main() -> None:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        start = text.index("<!-- PAGE ga=42 pdf_page=505")
        end = text.index("### II. STATEMENT OF THE ISSUE FOR CASE 2011-11", start)
        updated = text[:start] + repair_section(text[start:end]) + text[end:]
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
