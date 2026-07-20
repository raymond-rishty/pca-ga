#!/usr/bin/env python3
"""Expose BCO prefixes wrapped in inline emphasis to the citation linker."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PREFIX = r"(?:B\.?\s*C\.?\s*O\.?|Book\s+of\s+Church\s+Order)"
INLINE_PREFIX = re.compile(
    rf"<(?P<tag>em|i|strong|b)\b[^>]*>\s*(?P<prefix>{PREFIX})\s*</(?P=tag)>",
    re.IGNORECASE,
)


def main() -> int:
    site = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("_site")
    changed = 0
    for path in site.rglob("*.html"):
        source = path.read_text(encoding="utf-8")
        rendered, count = INLINE_PREFIX.subn(lambda match: match.group("prefix"), source)
        if count:
            path.write_text(rendered, encoding="utf-8")
            changed += 1
    print(f"Normalized emphasized BCO prefixes in {changed} HTML files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
