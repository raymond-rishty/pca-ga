"""Replace one reviewed case from explicitly ordered corrected-minute pages.

Use when a scanned PDF's physical page order differs from its printed-page
order. PP-Structure supplies the order decision; the re-OCR Markdown supplies
the text to retain.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = re.compile(r"\*Source: \[([^ ]+) p{1,2}\. (\d+)(?:[–-](\d+))?\]\(\.\./markdown/[^)]*\)\*")


def module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(value)
    return value


extractor = module("structural_case_extractor", "55_reextract_cases_from_formatted_minutes.py")


def parse_pages(value: str) -> list[int]:
    pages = [int(part) for part in value.split(",") if part.strip()]
    if not pages:
        raise argparse.ArgumentTypeError("provide at least one page")
    if len(set(pages)) != len(pages):
        raise argparse.ArgumentTypeError("pages must not repeat")
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_file", type=Path)
    parser.add_argument("--pages", required=True, type=parse_pages, help="Ordered PDF pages, e.g. 103,102,101")
    parser.add_argument("--start", required=True, help="Literal first case heading on the first selected page")
    parser.add_argument("--end", help="Optional literal closing text on the final selected page")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    target = ROOT / args.case_file
    page = target.read_text(encoding="utf-8")
    source = SOURCE.search(page)
    if not source:
        raise ValueError("case page has no recognizable source link")
    volume = source.group(1)
    pages = extractor.source_pages(volume)
    selected = []
    for index, number in enumerate(args.pages):
        if number not in pages:
            raise ValueError(f"PDF page {number} not found in corrected minutes")
        text = pages[number]["text"]
        if index == 0:
            offset = text.find(args.start)
            if offset < 0:
                raise ValueError("opening text not found on first selected page")
            text = text[offset:]
        if index == len(args.pages) - 1 and args.end:
            offset = text.find(args.end)
            if offset < 0:
                raise ValueError("closing text not found on final selected page")
            text = text[: offset + len(args.end)]
        if index:
            selected.append(pages[number]["marker"])
        selected.append(text.strip())
    body = "\n\n".join(part for part in selected if part)
    first, last = args.pages[0], args.pages[-1]
    low, high = sorted((first, last))
    display_pages = f"p. {first}" if first == last else f"pp. {low}–{high}"
    ga_match = re.search(r"ga(\d+)_", volume)
    assert ga_match
    source_link = f"*Source: [{volume} {display_pages}](../markdown/{volume}.md#ga{ga_match.group(1)}-p{first})*"
    updated = SOURCE.sub(source_link, page, count=1)
    updated = extractor.replace_body(updated, body)
    if args.apply:
        target.write_text(updated, encoding="utf-8")
    print(f"{args.case_file}: {'wrote' if args.apply else 'would write'} {volume} {display_pages}; {len(body)} body chars")


if __name__ == "__main__":
    main()
