#!/usr/bin/env python3
"""Ensure every sourced case body begins with its first minutes page marker.

Case extractions commonly retained continuation-page markers but omitted the
first page because it is also represented in the displayed source link.  The
marker itself is still needed for page-level provenance within the body.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = re.compile(r"\*Source: \[([^ ]+) p{1,2}\. (\d+)(?:[–-](\d+))?")
PAGE = re.compile(r"<!-- PAGE ga=(\d+) pdf_page=(\d+)\b[^>]*-->")


def source_marker(volume: str, page: int) -> str:
    minutes = (ROOT / "markdown" / f"{volume}.md").read_text(encoding="utf-8")
    found = re.search(rf"<!-- PAGE ga=\d+ pdf_page={page}\b[^>]*-->", minutes)
    if not found:
        raise ValueError(f"{volume}: page {page} marker not found")
    return found.group(0)


def update(path: Path, text: str) -> str | None:
    source = SOURCE.search(text)
    if not source:
        return None
    volume, first, _last = source.groups()
    first_page = int(first)
    pieces = text.split("\n---\n")
    if len(pieces) < 3:
        raise ValueError(f"{path}: no replaceable case body")
    body = pieces[1]
    existing = {int(page) for _ga, page in PAGE.findall(body)}
    if first_page in existing:
        return None
    marker = source_marker(volume, first_page)
    leading = re.match(r"\n*", body).group(0)
    pieces[1] = leading + marker + "\n\n" + body[len(leading):]
    return "\n---\n".join(pieces)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--from-git-ref", help="Regenerate case bodies from a Git revision")
    args = parser.parse_args()
    changed = 0
    skipped = 0
    for path in sorted((ROOT / "cases").glob("*.md")):
        if args.from_git_ref:
            relative = path.relative_to(ROOT).as_posix()
            text = subprocess.check_output(
                ["git", "show", f"{args.from_git_ref}:{relative}"], cwd=ROOT, text=True, encoding="utf-8"
            )
        else:
            text = path.read_text(encoding="utf-8")
        result = update(path, text)
        if result is None:
            skipped += 1
            continue
        if args.apply:
            path.write_text(result, encoding="utf-8")
        changed += 1
    print(f"{'Updated' if args.apply else 'Would update'} {changed} case start marker(s); skipped {skipped}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
