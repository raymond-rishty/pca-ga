#!/usr/bin/env python3
"""Catalog Markdown hard-break blocks before source-minute softening.

This is read-only. It reports every non-empty block containing trailing
two-space hard-break markers and classifies likely intentional structures so a
later cleanup can preserve them explicitly.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARD_BREAK = re.compile(r" {2,}(?=\r?$)")
PAGE_MARKER = re.compile(r"<!--\s*PAGE\s+ga=(\d+)\s+pdf_page=(\d+)[^>]*-->")
ADDRESS_SIGNAL = re.compile(
    r"(?i)(^\s*(?:\d{1,6}\s+.*\b(?:road|street|lane|drive|avenue|boulevard|highway)|route\s+\d)\b"
    r"|\b(?:p\.?\s*o\.?\s+box|post office box|box)\s+\d"
    r"|\b(?:phone|fax|telephone)\b\s*:?(?=\s*[+(\d])"
    r"|\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)\s+\d{5}(?:-\d{4})?\b)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Markdown files or directories, relative to the repository root (default: markdown)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "markdown-hard-break-catalog.json",
        help="JSON report destination",
    )
    parser.add_argument("--sample-limit", type=int, default=12, help="Examples to retain per category")
    return parser.parse_args()


def markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths or [Path("markdown")]:
        path = path if path.is_absolute() else ROOT / path
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.md"))
    return sorted(set(files))


def classify(lines: list[str]) -> str:
    content = [line.strip() for line in lines if line.strip()]
    if not content:
        return "empty"
    if any("<table" in line.lower() or "<tr" in line.lower() for line in content):
        return "html-table"
    if all(line.startswith(">") for line in content):
        return "blockquote"
    if all(re.match(r"^(?:[-+*]\s+|\d+[.)]\s+)", line) for line in content):
        return "list"
    if any(ADDRESS_SIGNAL.search(line) for line in content) and len(content) >= 2 and max(map(len, content)) <= 80:
        return "address"
    if all(re.match(r"^#{1,6}\s", line) for line in content):
        return "heading"
    if len(content) >= 2 and max(map(len, content)) <= 80:
        return "short-structured"
    return "prose"


def catalog(path: Path, sample_limit: int) -> tuple[Counter, list[dict], list[dict]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    counts: Counter = Counter()
    samples: list[dict] = []
    blocks: list[dict] = []
    position = 0
    page = None
    while position < len(lines):
        marker = PAGE_MARKER.search(lines[position])
        if marker:
            page = int(marker.group(2))
        if not lines[position].strip():
            position += 1
            continue
        start = position
        while position < len(lines) and lines[position].strip():
            position += 1
        block = lines[start:position]
        hard_breaks = [index for index, line in enumerate(block) if HARD_BREAK.search(line)]
        if not hard_breaks:
            continue
        category = classify(block)
        counts[category] += len(hard_breaks)
        record = {
            "path": str(path.relative_to(ROOT)),
            "page": page,
            "start_line": start + 1,
            "end_line": position,
            "category": category,
            "block_lines": len(block),
            "hard_break_lines": len(hard_breaks),
            "text_preview": " ".join(line.strip() for line in block)[:240],
        }
        blocks.append(record)
        if sum(1 for sample in samples if sample["category"] == category) >= sample_limit:
            continue
        samples.append(
            {
                "path": str(path.relative_to(ROOT)),
                "page": page,
                "start_line": start + 1,
                "end_line": position,
                "category": category,
                "hard_break_lines": len(hard_breaks),
                "text": "\n".join(line.rstrip() for line in block),
            }
        )
    return counts, samples, blocks


def main() -> None:
    args = parse_args()
    total = Counter()
    samples: list[dict] = []
    blocks: list[dict] = []
    files = markdown_files(args.paths)
    files_with_hard_breaks = 0
    for path in files:
        counts, path_samples, path_blocks = catalog(path, args.sample_limit)
        if counts:
            files_with_hard_breaks += 1
        total.update(counts)
        samples.extend(path_samples)
        blocks.extend(path_blocks)

    by_category: dict[str, list[dict]] = {}
    for sample in samples:
        by_category.setdefault(sample["category"], []).append(sample)
    report = {
        "paths": [str(path.relative_to(ROOT)) for path in files],
        "files_scanned": len(files),
        "files_with_hard_breaks": files_with_hard_breaks,
        "hard_break_lines": sum(total.values()),
        "counts_by_category": dict(sorted(total.items())),
        "blocks": blocks,
        "samples_by_category": by_category,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("files_scanned", "files_with_hard_breaks", "hard_break_lines", "counts_by_category")}, indent=2))
    print(args.output)


if __name__ == "__main__":
    main()
