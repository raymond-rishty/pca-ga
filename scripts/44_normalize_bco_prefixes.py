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
    """Split only a true sentence boundary, not a lowercase subsection marker."""
    if not match.group("next").isupper():
        return match.group(0)
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
        "Compare BCO 5-9.c, 8-4, 13-2. Therefore proceed."
    )
    rendered, count = SENTENCE_PERIOD.subn(protect_sentence_period, sample)
    assert count == 3
    assert "BCO 46-8&#46; Or continue" in rendered
    assert "BCO 5-9.c&#46; The paragraph" in rendered
    assert "BCO 5-9.c, 8-4, 13-2&#46; Therefore" in rendered
    assert "BCO 46-8. O" not in rendered


def main() -> int:
    self_test()
    site = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("_site")
    changed = 0
    emphasized = 0
    boundaries = 0

    for path in site.rglob("*.html"):
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

    print(
        "Normalized BCO citations in "
        f"{changed} HTML files: {emphasized} emphasized prefixes, "
        f"{boundaries} sentence boundaries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
