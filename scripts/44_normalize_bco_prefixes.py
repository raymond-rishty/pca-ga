#!/usr/bin/env python3
"""Normalize rendered BCO citations before the constitutional-reference linker.

Two HTML-boundary cases need a small preprocessing pass:

1. Markdown may wrap the ``BCO`` prefix in inline emphasis, splitting the text
   across HTML nodes before the citation parser sees it.
2. A sentence such as ``BCO 46-8. Or ...`` must not be parsed as subsection
   ``46-8.O``. The sentence period is encoded as an HTML character reference so
   it remains visible but forms a node boundary before the next word.
"""

from __future__ import annotations

import re
import sys
import hashlib
import json
import argparse
from pathlib import Path

DASH = r"[-\u2010\u2011\u2012\u2013\u2014\u2212]"
PREFIX = r"(?:B\.?\s*C\.?\s*O\.?|Book\s+of\s+Church\s+Order)"
REF = rf"\d{{1,2}}\s*{DASH}\s*\d{{1,2}}(?:\.[A-Za-z]|\s*\(\s*[A-Za-z]\s*\))?"
SEP = r"(?:\s*,\s*|\s*;\s*|\s+(?:and|or)\s+)"

INLINE_PREFIX = re.compile(
    rf"<(?P<tag>em|i|strong|b)\b[^>]*>\s*(?P<prefix>{PREFIX})\s*</(?P=tag)>",
    re.IGNORECASE,
)
SENTENCE_PERIOD = re.compile(
    rf"(?P<citation>\b{PREFIX}\s+{REF}(?:{SEP}{REF})*)"
    rf"\.(?P<space>\s+)(?P<next>[A-Za-z])",
    re.IGNORECASE,
)


def protect_sentence_period(match: re.Match[str]) -> str:
    """Split a sentence period from the following word.

    A subsection marker is attached to the section number (``5-9.c``) or is
    parenthesized. Once whitespace follows a period, it is punctuation rather
    than part of the constitutional reference.
    """
    return (
        match.group("citation")
        + "&#46;"
        + match.group("space")
        + match.group("next")
    )


def self_test() -> None:
    sample = (
        "carry out BCO 46-8. Or continue. "
        "See BCO 5-9.c. The paragraph applies. "
        "Compare BCO 5-9.c, 8-4, 13-2. Therefore proceed. "
        "An OCR line may say BCO 31-2. process continues."
    )
    rendered, count = SENTENCE_PERIOD.subn(protect_sentence_period, sample)
    assert count == 4
    assert "BCO 46-8&#46; Or continue" in rendered
    assert "BCO 5-9.c&#46; The paragraph" in rendered
    assert "BCO 5-9.c, 8-4, 13-2&#46; Therefore" in rendered
    assert "BCO 31-2&#46; process continues" in rendered
    assert "BCO 46-8. O" not in rendered


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    self_test()
    parser = argparse.ArgumentParser()
    parser.add_argument("site_dir", type=Path, nargs="?", default=Path("_site"))
    parser.add_argument("--incremental-state", type=Path,
                        help="Use prior per-page link hashes to select stale HTML")
    parser.add_argument("--files-manifest", type=Path,
                        help="Write changed HTML paths for the citation linker")
    parser.add_argument("--changed-files", type=Path,
                        help="Restrict processing to a JSON list or mapping of changed HTML paths")
    args = parser.parse_args()
    site = args.site_dir
    cached_pages: dict[str, dict[str, str]] = {}
    if args.incremental_state and args.incremental_state.is_file():
        try:
            cached_pages = json.loads(
                args.incremental_state.read_text(encoding="utf-8")
            ).get("pages", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            cached_pages = {}

    candidates: dict[str, str | None] | None = None
    if args.changed_files:
        try:
            raw_candidates = json.loads(args.changed_files.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            parser.error(f"Cannot read changed-file manifest: {error}")
        candidates = ({str(item): None for item in raw_candidates}
                      if isinstance(raw_candidates, list)
                      else {str(key): value for key, value in raw_candidates.items()})

    changed = 0
    emphasized = 0
    boundaries = 0
    changed_paths: list[str] = []

    all_paths = sorted(site.rglob("*.html"))
    if candidates is None:
        paths = all_paths
    else:
        paths = [site / relative for relative in sorted(candidates)
                 if candidates[relative] is not None and (site / relative).is_file()]
    for path in paths:
        relative = path.relative_to(site).as_posix()
        cached = cached_pages.get(relative)
        if cached and cached.get("sha256") == file_sha256(path):
            continue
        source = path.read_text(encoding="utf-8")
        rendered, prefix_count = INLINE_PREFIX.subn(
            lambda match: match.group("prefix"), source
        )
        rendered, boundary_count = SENTENCE_PERIOD.subn(
            protect_sentence_period, rendered
        )
        if prefix_count or boundary_count:
            path.write_text(rendered, encoding="utf-8")
            changed += 1
            emphasized += prefix_count
            boundaries += boundary_count
        changed_paths.append(relative)

    if args.files_manifest:
        args.files_manifest.parent.mkdir(parents=True, exist_ok=True)
        if candidates is None:
            result_manifest: object = {
                relative: file_sha256(site / relative) if (site / relative).is_file() else None
                for relative in changed_paths
            }
        else:
            result_manifest = {
                relative: file_sha256(site / relative) if (site / relative).is_file() else None
                for relative in candidates
            }
        args.files_manifest.write_text(json.dumps(result_manifest, separators=(",", ":")),
                                       encoding="utf-8")

    print(
        "Normalized BCO citations in "
        f"{changed} HTML files: {emphasized} emphasized prefixes, "
        f"{boundaries} sentence boundaries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
