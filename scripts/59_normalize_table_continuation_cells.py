"""Restore empty leading cells for one-cell continuation rows in HTML tables.

PP-Structure sometimes emits a right-column continuation line as
``<tr><td>text</td></tr>``.  On reviewed two-column tables, this represents an
empty left cell, not a one-column row.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"(?s)(<!-- PAGE ga=\d+ pdf_page=(\d+)\b[^>]*-->)(.*?)(?=<!-- PAGE ga=|\Z)")
TABLE = re.compile(r"(?s)<table\b.*?</table>")
ONE_CELL_ROW = re.compile(r"<tr><td>([^<]*)</td></tr>")
TWO_CELL_ROW = re.compile(r"(?s)<tr><td>(.*?)</td><td>(.*?)</td></tr>")
# Limited recovery for the pre-commit run of this helper, whose permissive row
# pattern added an empty first cell to full two-column rows.
ACCIDENTAL_THREE_CELL_ROW = re.compile(r"<tr><td></td><td>([^<]*)</td><td>")


def normalize_table(match: re.Match[str]) -> tuple[str, int]:
    changed = 0

    def replace(row: re.Match[str]) -> str:
        nonlocal changed
        content = row.group(1)
        if not content.strip():
            return row.group(0)
        changed += 1
        return f"<tr><td></td><td>{content}</td></tr>"

    return ONE_CELL_ROW.sub(replace, match.group(0)), changed


def merge_continuations(table: str) -> tuple[str, int]:
    """Fold empty-left rows into the preceding right-hand cell."""
    rows = list(TWO_CELL_ROW.finditer(table))
    if not rows:
        return table, 0
    output = [table[: rows[0].start()]]
    merged = 0
    pending_left: str | None = None
    pending_right: str | None = None

    def flush() -> None:
        nonlocal pending_left, pending_right
        if pending_left is not None:
            output.append(f"<tr><td>{pending_left}</td><td>{pending_right}</td></tr>")
        pending_left = pending_right = None

    for row in rows:
        left, right = row.group(1), row.group(2)
        if not left.strip() and pending_left is not None:
            pending_right = f"{pending_right}<br>{right}"
            merged += 1
        else:
            flush()
            pending_left, pending_right = left, right
    flush()
    output.append(table[rows[-1].end() :])
    return "".join(output), merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("minutes_file", type=Path, help="Minutes Markdown relative to repository root")
    parser.add_argument("--pages", required=True, help="Comma-separated PDF pages")
    parser.add_argument("--repair-accidental-three-cells", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--merge-continuations", action="store_true", help="Merge empty-left continuation rows into multiline right cells")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    targets = {int(value) for value in args.pages.split(",") if value.strip()}
    path = ROOT / args.minutes_file
    source = path.read_text(encoding="utf-8")
    output = []
    offset = 0
    changed = 0
    for page in PAGE.finditer(source):
        output.append(source[offset : page.start()])
        marker, number, body = page.groups()
        if int(number) in targets:
            if args.repair_accidental_three_cells:
                body = ACCIDENTAL_THREE_CELL_ROW.sub(r"<tr><td>\1</td><td>", body)
            def table_replace(table: re.Match[str]) -> str:
                nonlocal changed
                rewritten, count = normalize_table(table)
                changed += count
                if args.merge_continuations:
                    rewritten, count = merge_continuations(rewritten)
                    changed += count
                return rewritten

            body = TABLE.sub(table_replace, body)
        output.append(marker + body)
        offset = page.end()
    output.append(source[offset:])
    updated = "".join(output)
    if args.apply and updated != source:
        path.write_text(updated, encoding="utf-8")
    print(f"{args.minutes_file}: {'wrote' if args.apply and updated != source else 'unchanged'}; normalized_rows={changed}")


if __name__ == "__main__":
    main()
