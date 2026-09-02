#!/usr/bin/env python3
"""Replace one case body from explicit start/end text in corrected minutes.

Use for reviewed cases whose source boundaries are known by a human but do not
meet the automatic alignment threshold. The existing case-page preamble is
retained; one span updates its PDF-page source range, while multiple spans
retain the established min–max citation.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"<!--\s*PAGE\s+ga=(\d+)\s+pdf_page=(\d+)[^>]*-->")
SOURCE = re.compile(r"\*Source: \[([^ ]+) p{1,2}\. (\d+)(?:[–-](\d+))?\]\(\.\./markdown/[^)]*\)\*")


def page_at_or_before(source: str, offset: int) -> tuple[int, int]:
    marker = None
    for match in PAGE.finditer(source):
        if match.start() > offset:
            break
        marker = match
    if not marker:
        raise ValueError("no PDF page marker before selected text")
    return int(marker.group(1)), int(marker.group(2))


def replace_body(page: str, body: str) -> str:
    pieces = page.split("\n---\n")
    if len(pieces) < 3:
        raise ValueError("case page has no replaceable body delimiters")
    return "\n---\n".join([pieces[0], "\n" + body.strip() + "\n", *pieces[2:]]).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_file", type=Path, help="Case page relative to repository root")
    parser.add_argument(
        "--start",
        action="append",
        required=True,
        help="Literal opening text in corrected minutes; repeat with --end for a discontinuous record",
    )
    parser.add_argument(
        "--end",
        action="append",
        help="Literal closing text in corrected minutes; repeat with --start for a discontinuous record",
    )
    parser.add_argument(
        "--end-before",
        action="append",
        help="Literal heading immediately after a span; exclude it from the extracted body",
    )
    parser.add_argument(
        "--start-page",
        action="append",
        type=int,
        help="Restrict each opening-text search to this PDF page or later",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    target = ROOT / args.case_file
    page = target.read_text(encoding="utf-8")
    source_meta = SOURCE.search(page)
    if not source_meta:
        raise ValueError("case page has no recognizable source link")
    volume = source_meta.group(1)
    minutes = (ROOT / "markdown" / f"{volume}.md").read_text(encoding="utf-8")
    endings = [(text, False) for text in (args.end or [])] + [(text, True) for text in (args.end_before or [])]
    if len(args.start) != len(endings):
        raise ValueError("--start must occur once for every --end or --end-before")
    start_pages = args.start_page or []
    if start_pages and len(start_pages) != len(args.start):
        raise ValueError("repeat --start-page once per --start, or omit it")

    spans = []
    for index, (opening, (closing, excludes_closing)) in enumerate(zip(args.start, endings)):
        search_from = 0
        if start_pages:
            page_match = re.search(rf"<!--\s*PAGE\s+ga=\d+\s+pdf_page={start_pages[index]}\b[^>]*-->", minutes)
            if not page_match:
                raise ValueError(f"PDF page {start_pages[index]} not found in corrected minutes")
            search_from = page_match.end()
        begin = minutes.find(opening, search_from)
        if begin < 0:
            raise ValueError(f"opening text {index + 1} not found")
        finish_start = minutes.find(closing, begin)
        if finish_start < 0:
            raise ValueError(f"closing text {index + 1} not found after opening text")
        finish = finish_start if excludes_closing else finish_start + len(closing)
        spans.append((begin, finish))

    ordered = sorted(spans)
    if any(right[0] < left[1] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("selected spans overlap")
    ga, first = page_at_or_before(minutes, ordered[0][0])
    _, last = page_at_or_before(minutes, ordered[-1][1] - 1)
    body = "\n\n".join(minutes[begin:finish].strip() for begin, finish in ordered)
    # Case pages are prose views; do not carry the source-minute hard-break
    # markers that preserve physical OCR line wraps in the volume pages.
    body = re.sub(r"[ \t]+(?=\r?$)", "", body, flags=re.MULTILINE)
    if body.startswith("Case #"):
        body = "## " + body
    if len(ordered) == 1:
        pages = f"p. {first}" if first == last else f"pp. {first}–{last}"
        source_link = f"*Source: [{volume} {pages}](../markdown/{volume}.md#ga{ga}-p{first})*"
        updated = SOURCE.sub(source_link, page, count=1)
    else:
        pages = f"pp. {first}–{last} (noncontiguous)"
        updated = page
    updated = replace_body(updated, body)
    if args.apply:
        target.write_text(updated, encoding="utf-8")
    print(f"{args.case_file}: {'wrote' if args.apply else 'would write'} {volume} {pages}; {len(body)} body chars")


if __name__ == "__main__":
    main()
