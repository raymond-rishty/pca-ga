#!/usr/bin/env python3
"""Remove accidental Markdown hard-break markers from extracted pages.

Paddle's line-oriented Markdown can leave two spaces before a newline. In
CommonMark that means ``<br>``, which is not appropriate for prose case pages.
The source-minute files are intentionally not included by default because they
contain some genuine line-preserved blocks, such as addresses. Use ``--minutes``
to target source-minute Markdown and clean only blocks classified as ordinary
prose; that mode preserves addresses, blockquotes, lists, headings, HTML
tables, and short structured blocks.

By default this is a dry run. Use ``--apply`` to write changes or ``--check``
to return a failure status when cleanup is still needed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HARD_BREAK = re.compile(r" {2,}(?=\r?$)", re.MULTILINE)
ADDRESS_SIGNAL = re.compile(
    r"(?i)(^\s*(?:\d{1,6}\s+.*\b(?:road|street|lane|drive|avenue|boulevard|highway)|route\s+\d)\b"
    r"|\b(?:p\.?\s*o\.?\s+box|post office box|box)\s+\d"
    r"|\b(?:phone|fax|telephone)\b\s*:?(?=\s*[+(\d])"
    r"|\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)\s+\d{5}(?:-\d{4})?\b)"
)


def classify_block(block: list[str]) -> str:
    """Classify a non-empty Markdown block using the hard-break catalog rules."""
    content = [line.strip() for line in block if line.strip()]
    if not content:
        return "empty"

    lowered = "\n".join(content).lower()
    if "<table" in lowered or "<tr" in lowered:
        return "html-table"
    if all(line.startswith(">") for line in content):
        return "blockquote"
    if all(re.match(r"^(?:[-+*]\s+|\d+[.)]\s+)", line) for line in content):
        return "list"
    if (
        len(content) >= 2
        and max(map(len, content)) <= 80
        and any(ADDRESS_SIGNAL.search(line) for line in content)
    ):
        return "address"
    if all(re.match(r"^#{1,6}\s+", line) for line in content):
        return "heading"
    if len(content) >= 2 and max(map(len, content)) <= 80:
        return "short-structured"
    return "prose"


def markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        path = path if path.is_absolute() else ROOT / path
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
    return sorted(set(files))


def clean(text: str, *, minutes: bool = False) -> tuple[str, int]:
    """Strip accidental line-end spaces, optionally using minute classifications."""
    lines = text.splitlines(keepends=True)
    contents = [line.rstrip("\r\n") for line in lines]
    protected_lines: set[int] = set()
    fenced = False
    position = 0
    while position < len(contents):
        if not contents[position].strip():
            position += 1
            continue
        start = position
        contains_fence = False
        while position < len(contents) and contents[position].strip():
            if FENCE.match(contents[position]):
                contains_fence = True
                fenced = not fenced
            position += 1
        block = contents[start:position]
        category = classify_block(block)
        if (
            fenced
            or contains_fence
            or (minutes and category != "prose")
            or (not minutes and category == "address")
        ):
            protected_lines.update(range(start, position))

    output: list[str] = []
    changed = 0
    fenced = False
    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        ending = line[len(content) :]
        fence = FENCE.match(content)
        if not fenced and not fence and index not in protected_lines:
            updated = HARD_BREAK.sub("", content)
            changed += updated != content
            output.append(updated + ending)
        else:
            output.append(line)
        if fence:
            fenced = not fenced
    return "".join(output), changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Markdown files or directories, relative to the repository root (default: cases)",
    )
    parser.add_argument("--apply", action="store_true", help="Write the cleaned Markdown files")
    parser.add_argument("--check", action="store_true", help="Exit 1 if cleanup would change any file")
    parser.add_argument(
        "--minutes",
        action="store_true",
        help="Target source-minute Markdown and clean only cataloged prose blocks",
    )
    args = parser.parse_args()
    if args.apply and args.check:
        parser.error("--apply and --check are mutually exclusive")

    paths = args.paths or [Path("markdown" if args.minutes else "cases")]
    files = markdown_files(paths)
    affected_files = 0
    affected_lines = 0
    for path in files:
        original = path.read_text(encoding="utf-8")
        updated, changed = clean(original, minutes=args.minutes)
        if not changed:
            continue
        affected_files += 1
        affected_lines += changed
        print(f"{path.relative_to(ROOT)}: {changed} line(s)")
        if args.apply:
            path.write_text(updated, encoding="utf-8")

    mode = "applied" if args.apply else "would change"
    print(f"{mode}: {affected_lines} line(s) in {affected_files} file(s)")
    return int(args.check and affected_files > 0)


if __name__ == "__main__":
    sys.exit(main())
