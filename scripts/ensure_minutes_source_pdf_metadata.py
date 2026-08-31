#!/usr/bin/env python3
"""Ensure full-minutes Markdown carries canonical PCA Historical Center PDF metadata.

Bulk OCR/regeneration jobs may replace the document front matter along with page
content. This normalizer is deliberately narrow: it derives the canonical source
PDF filename from each ``markdown/gaNN_YEAR.md`` path, inserts ``source_pdf.file``
when it is absent, preserves any existing ``source_pdf`` fields (for example a
SHA-256), and refuses to overwrite a conflicting filename.

Run after any minutes regeneration/import and before site validation/build.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINUTES = ROOT / "markdown"
VOLUME_RE = re.compile(r"^ga(?P<ga>\d{2})_(?P<year>\d{4})\.md$")
SOURCE_BLOCK_RE = re.compile(r"(?m)^source_pdf:\s*$")
SOURCE_FILE_RE = re.compile(r"(?m)^  file:\s*[\"']?(?P<file>[^\"'\n]+)[\"']?\s*$")


def ordinal_suffix(value: int) -> str:
    if 10 <= value % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")


def expected_pdf(path: Path) -> str:
    match = VOLUME_RE.match(path.name)
    if not match:
        raise ValueError(f"Not a full-minutes filename: {path.name}")
    ga = int(match.group("ga"))
    year = int(match.group("year"))
    return f"{ga}{ordinal_suffix(ga)}_pcaga_{year}.pdf"


def split_front_matter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("Minutes file has no YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("Minutes file has unterminated YAML front matter")
    return text[4:end], text[end:]


def normalize_text(text: str, filename: str) -> tuple[str, bool]:
    front, rest = split_front_matter(text)
    expected = expected_pdf(Path(filename))
    source_match = SOURCE_BLOCK_RE.search(front)

    if source_match:
        block_start = source_match.end()
        next_top_level = re.search(r"(?m)^[A-Za-z0-9_-]+:\s*", front[block_start:])
        block_end = block_start + (next_top_level.start() if next_top_level else len(front[block_start:]))
        block = front[block_start:block_end]
        file_match = SOURCE_FILE_RE.search(block)
        if file_match:
            actual = file_match.group("file").strip()
            if actual != expected:
                raise ValueError(f"{filename}: source_pdf.file is {actual!r}, expected {expected!r}")
            return text, False
        insertion = f"\n  file: {expected}"
        front = front[:block_start] + insertion + front[block_start:]
    else:
        block = f"source_pdf:\n  file: {expected}\n"
        extraction = re.search(r"(?m)^extraction:\s*$", front)
        schema = re.search(r"(?m)^schema_version:\s*", front)
        anchor = extraction.start() if extraction else (schema.start() if schema else len(front))
        if anchor and not front[:anchor].endswith("\n"):
            block = "\n" + block
        front = front[:anchor] + block + front[anchor:]

    return "---\n" + front + rest, True


def volume_paths(root: Path = MINUTES) -> list[Path]:
    return sorted(path for path in root.glob("ga??_????.md") if VOLUME_RE.match(path.name))


def run(root: Path, check: bool) -> int:
    paths = volume_paths(root)
    if len(paths) != 52:
        raise SystemExit(f"expected 52 full-minutes volumes, found {len(paths)}")

    changed: list[Path] = []
    for path in paths:
        original = path.read_text(encoding="utf-8")
        normalized, did_change = normalize_text(original, path.name)
        if did_change:
            changed.append(path)
            if not check:
                path.write_text(normalized, encoding="utf-8")

    if changed:
        verb = "need" if check else "received"
        print(f"{len(changed)} minutes volumes {verb} source_pdf.file metadata")
        for path in changed:
            print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
        return 1 if check else 0

    print("All 52 minutes volumes already carry canonical source_pdf.file metadata")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report missing metadata without modifying files")
    parser.add_argument("--root", type=Path, default=MINUTES, help="Minutes directory (for tests or alternate worktrees)")
    args = parser.parse_args()
    return run(args.root, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
