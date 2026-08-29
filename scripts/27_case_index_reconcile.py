#!/usr/bin/env python3
"""Reconcile the checked-in judicial-case artefacts without rebuilding the SQLite corpus.

Two recurring extraction artefacts are repaired here:

1. A consolidated SJC decision may be printed under only one docket-number heading while its
   holding expressly disposes of sibling dockets.  Add those sibling numbers to the existing
   case-page map and index row, and make the case-page heading reflect the consolidated decision.
2. The cases table contains duplicate/mis-paged fallback rows.  A row labelled
   ``no separate decision located`` is noise when its reported PDF page is already physically
   present inside an extracted case page.  Suppress it.

The script deliberately works only from checked-in case pages, case_pages_map.json, and CASES.md,
so it is safe to run in the GitHub Pages build where pca_minutes.db is not present.
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.environ.get("PCA_GA_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(ROOT, "index", "CASES.md")
PMAP = os.path.join(ROOT, "index", "case_pages_map.json")

PAGE_MARKER = re.compile(r"<!--\s*PAGE\b[^>]*\bpdf_page=(\d+)\b", re.I)
CASE_NUM = re.compile(r"\b(\d{4})-(\d{1,3}[A-Za-z]?)\b")
DECIDED = re.compile(
    r"(?i)\b(?:complaints?|appeals?|petitions?)\b[^.!?]{0,180}?\bcase\s+nos?\.?\s*"
    r"[^.!?]{0,120}?\b(?:is|are|be|was|were)\s+"
    r"(?:partially\s+|in\s+part\s+)?(?:sustained|denied|dismissed|granted|affirmed|reversed|"
    r"annulled|out\s+of\s+order|not\s+sustained)\b",
)
FALLBACK = re.compile(
    r"_no separate decision located_\s*·\s*\[(ga\d+_\d+)\s+p\.(\d+)\]",
    re.I,
)


def norm_num(raw: str) -> str:
    m = CASE_NUM.fullmatch(raw.strip())
    if not m:
        return raw.strip()
    return f"{m.group(1)}-{int(re.match(r'\d+', m.group(2)).group()):02d}{re.sub(r'^\d+', '', m.group(2)).lower()}"


def expressly_decided_siblings(text: str, existing: list[str]) -> list[str]:
    """Find sibling dockets in actual holding sentences, not ordinary precedent citations."""
    if not existing:
        return []
    years = {int(n[:4]) for n in existing if re.match(r"\d{4}-", n)}
    flat = re.sub(r"\s+", " ", text)
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", flat):
        if not DECIDED.search(sentence):
            continue
        for raw in (m.group(0) for m in CASE_NUM.finditer(sentence)):
            n = norm_num(raw)
            # Consolidated dockets are contemporaneous.  This excludes older cases quoted as
            # precedent in a holding paragraph without needing the unavailable database roster.
            if years and all(abs(int(n[:4]) - y) > 2 for y in years):
                continue
            if n not in out:
                out.append(n)
    return out


def main() -> None:
    if not os.path.exists(INDEX) or not os.path.exists(PMAP):
        raise SystemExit("CASES.md and case_pages_map.json must exist")

    page_map = json.load(open(PMAP, encoding="utf-8"))
    index_text = open(INDEX, encoding="utf-8").read()
    occupied: set[tuple[str, int]] = set()
    seen_files: set[str] = set()
    expanded: list[tuple[str, list[str]]] = []

    # Work once per extracted decision page.  Multiple map keys may already point at the same file.
    by_file: dict[str, dict] = {}
    for entry in page_map.values():
        if entry.get("file"):
            by_file.setdefault(entry["file"], entry)

    for case_file, entry in by_file.items():
        vol = entry.get("vol")
        if not vol:
            continue
        path = os.path.join(ROOT, "cases", case_file + ".md")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        for raw in PAGE_MARKER.findall(text):
            occupied.add((vol, int(raw)))

        nums = sorted(dict.fromkeys(norm_num(x) for x in entry.get("numbers", []) if x))
        siblings = expressly_decided_siblings(text, nums)
        merged = sorted(dict.fromkeys(nums + siblings))
        if merged == nums:
            continue

        canonical = dict(entry)
        canonical["numbers"] = merged
        for n in merged:
            page_map[n] = dict(canonical)

        # Keep the existing filename stable; only the human-facing heading/index label needs the
        # complete docket set.  This avoids breaking old inbound URLs.
        joined = "/".join(merged)
        text = re.sub(r"^#\s+[^\n]+?(\s+—\s+)", lambda m: f"# {joined}{m.group(1)}", text, count=1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

        pat = re.compile(r"(\|\s*\[)[^\]]+(\]\(\.\./cases/" + re.escape(case_file) + r"\.md\))")
        index_text = pat.sub(lambda m: m.group(1) + joined + m.group(2), index_text)
        expanded.append((case_file, merged))

    with open(PMAP, "w", encoding="utf-8") as f:
        json.dump(page_map, f, indent=1)
        f.write("\n")

    lines = index_text.splitlines()
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

    if expanded:
        print("expanded consolidated decisions:", " ".join(f"{f}={'/'.join(ns)}" for f, ns in expanded))
    unique = sorted(set(removed))
    print(f"suppressed {len(removed)} duplicate/mis-paged fallback rows "
          f"({len(unique)} unique source pages) already contained in extracted case pages")
    if unique:
        print("resolved:", " ".join(f"{v}:p{p}" for v, p in unique))


if __name__ == "__main__":
    main()
