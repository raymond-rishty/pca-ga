#!/usr/bin/env python3
"""Reconcile CASES.md fallback rows against the structure-first case pages.

The cases table contains some duplicate/mis-paged rows.  After the structure-first case pages and
CASES.md have been regenerated, a fallback row labelled ``no separate decision located`` is noise
when its reported PDF page is already physically present inside one of the case pages mapped by
index/case_pages_map.json.  Suppress those rows rather than presenting an apparent missing case.

This intentionally does *not* suppress ``no separate decision`` rows (withdrawn/out-of-order/etc.)
or genuinely unresolved rows whose page is not contained in an extracted decision.
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.environ.get("PCA_GA_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(ROOT, "index", "CASES.md")
PMAP = os.path.join(ROOT, "index", "case_pages_map.json")

PAGE_MARKER = re.compile(r"<!--\s*PAGE\b[^>]*\bpdf_page=(\d+)\b", re.I)
FALLBACK = re.compile(
    r"_no separate decision located_\s*·\s*\[(ga\d+_\d+)\s+p\.(\d+)\]",
    re.I,
)


def main() -> None:
    if not os.path.exists(INDEX) or not os.path.exists(PMAP):
        raise SystemExit("CASES.md and case_pages_map.json must be generated first")

    page_map = json.load(open(PMAP, encoding="utf-8"))
    occupied: set[tuple[str, int]] = set()
    seen_files: set[str] = set()

    for entry in page_map.values():
        case_file = entry.get("file")
        vol = entry.get("vol")
        if not case_file or not vol or case_file in seen_files:
            continue
        seen_files.add(case_file)
        path = os.path.join(ROOT, "cases", case_file + ".md")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        for raw in PAGE_MARKER.findall(text):
            occupied.add((vol, int(raw)))

    lines = open(INDEX, encoding="utf-8").read().splitlines()
    kept: list[str] = []
    removed: list[tuple[str, int]] = []
    for line in lines:
        m = FALLBACK.search(line)
        if m and (m.group(1), int(m.group(2))) in occupied:
            removed.append((m.group(1), int(m.group(2))))
            continue
        kept.append(line)

    with open(INDEX, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")

    unique = sorted(set(removed))
    print(f"suppressed {len(removed)} duplicate/mis-paged fallback rows "
          f"({len(unique)} unique source pages) already contained in extracted case pages")
    if unique:
        print("resolved:", " ".join(f"{v}:p{p}" for v, p in unique))


if __name__ == "__main__":
    main()
