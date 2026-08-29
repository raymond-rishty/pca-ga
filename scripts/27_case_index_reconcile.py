#!/usr/bin/env python3
"""Reconcile checked-in judicial-case artefacts without rebuilding the SQLite corpus.

The structure-first publisher normally owns case pages and the case-page map, but a clean GitHub
Pages checkout intentionally does not contain the analysis database/caches needed to rerun that
publisher. This pass therefore treats the checked-in ``cases/*.md`` pages as evidence it can safely
inspect during deployment.

It repairs two recurring extraction artefacts:

1. A consolidated SJC decision may be printed under only one docket-number heading while its
   holding expressly disposes of sibling dockets. Add those sibling numbers to the existing
   case-page map and index row, and make the case-page heading reflect the consolidated decision.
2. The cases table contains duplicate/mis-paged fallback rows. Suppress only rows we can safely
   identify as duplicates; a valid docket that is not mapped to a decision is preserved for review.

Discovery scans every checked-in case page instead of relying on case_pages_map.json. An omitted
docket can coincide with an incomplete map, so the defect itself must not prevent discovery.
"""
from __future__ import annotations

import glob
import json
import os
import re

ROOT = os.environ.get("PCA_GA_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(ROOT, "index", "CASES.md")
PMAP = os.path.join(ROOT, "index", "case_pages_map.json")
CASES = os.path.join(ROOT, "cases")

PAGE_MARKER = re.compile(r"<!--\s*PAGE\b[^>]*\bpdf_page=(\d+)\b", re.I)
CASE_NUM = re.compile(r"\b(\d{4})-(\d{1,3}[A-Za-z]?)\b")
DISPOSITION = re.compile(
    r"(?i)\b(?:is|are|be|was|were)\s+(?:partially\s+|in\s+part\s+)?"
    r"(?:sustained|denied|dismissed|granted|affirmed|reversed|annulled|"
    r"out\s+of\s+order|not\s+sustained)\b"
)
HOLDING_CASE = re.compile(
    r"(?i)\b(?:complaints?|appeals?|petitions?)\b[^.!?]{0,260}?\bcase\s+nos?(?:\s|$)"
)
FALLBACK = re.compile(
    r"_no separate decision located_\s*·\s*\[(ga\d+_\d+)\s+p\.(\d+)\]",
    re.I,
)
FILE_VOL = re.compile(r"^(ga\d+_\d+)__(.+)$")

AUDITED_DUPLICATE_PAGES = {
    ("ga20_1992", 195),
    ("ga26_1998", 120),
    ("ga29_2001", 108),
    ("ga30_2002", 177),
    ("ga37_2009", 154),
    ("ga37_2009", 187),
    ("ga46_2018", 533),
    ("ga48_2021", 693),
    ("ga48_2021", 697),
}
PRESERVE_FALLBACK_PAGES = {
    ("ga49_2022", 842),  # 2020-2, BCO 34-1 original-jurisdiction requests
    ("ga49_2022", 886),  # 2021-7, Acree complaint administratively out of order
}


def norm_num(raw: str) -> str:
    m = CASE_NUM.fullmatch(raw.strip())
    if not m:
        return raw.strip()
    suffix = re.sub(r"^\d+", "", m.group(2)).lower()
    number = int(re.match(r"\d+", m.group(2)).group())
    return f"{m.group(1)}-{number:02d}{suffix}"


def expressly_decided_siblings(text: str, existing: list[str]) -> list[str]:
    """Find dockets expressly disposed of in actual holding sentences."""
    if not existing:
        return []
    years = {int(n[:4]) for n in existing if re.match(r"\d{4}-", n)}
    flat = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    flat = re.sub(r"\s+", " ", flat)
    flat = re.sub(r"(?i)\bCase\s+Nos?\.\s*", lambda m: m.group(0).replace(".", ""), flat)
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", flat):
        if not DISPOSITION.search(sentence) or not HOLDING_CASE.search(sentence):
            continue
        for raw in (m.group(0) for m in CASE_NUM.finditer(sentence)):
            n = norm_num(raw)
            if years and all(abs(int(n[:4]) - y) > 2 for y in years):
                continue
            if n not in out:
                out.append(n)
    return out


def page_identity(path: str, page_map: dict[str, dict]) -> tuple[str, list[str], str] | None:
    """Return (volume, known docket numbers, title) for a checked-in case page."""
    case_file = os.path.splitext(os.path.basename(path))[0]
    mapped = next((v for v in page_map.values() if v.get("file") == case_file), None)
    if mapped:
        return mapped.get("vol", ""), [norm_num(x) for x in mapped.get("numbers", [])], mapped.get("title", "")

    fm = FILE_VOL.match(case_file)
    if not fm:
        return None
    vol, tail = fm.groups()
    nums = [norm_num(m.group(0)) for m in CASE_NUM.finditer(tail.replace("_", " "))]
    if not nums:
        return None
    first = open(path, encoding="utf-8").readline().strip()
    title = re.sub(r"^#\s*", "", first)
    title = re.sub(r"^.*?\s+—\s+", "", title)
    return vol, nums, title


def row_docket(line: str) -> str | None:
    cells = line.split("|")
    if len(cells) < 3:
        return None
    m = CASE_NUM.search(cells[1])
    return norm_num(m.group(0)) if m else None


def normalize_consolidated_row(index_text: str, case_file: str, numbers: list[str]) -> str:
    """Normalize the two links in a consolidated CASES.md row without touching other columns."""
    target = f"../cases/{case_file}.md"
    joined = "/".join(numbers)
    out = []
    for line in index_text.splitlines():
        if target not in line or not line.startswith("|"):
            out.append(line)
            continue
        cells = line.split("|")
        # Leading/trailing pipes make cells 1 and 5 the Case and Page cells respectively.
        if len(cells) >= 7 and target in cells[1]:
            cells[1] = re.sub(
                r"\[[^\]]+\](\(" + re.escape(target) + r"\))",
                lambda m: f"[{joined}]{m.group(1)}",
                cells[1],
                count=1,
            )
            if target in cells[5]:
                cells[5] = re.sub(
                    r"\[[^\]]+\](\(" + re.escape(target) + r"\))",
                    lambda m: f"[full text]{m.group(1)}",
                    cells[5],
                    count=1,
                )
            line = "|".join(cells)
        out.append(line)
    return "\n".join(out) + ("\n" if index_text.endswith("\n") else "")


def main() -> None:
    if not os.path.exists(INDEX) or not os.path.exists(PMAP):
        raise SystemExit("CASES.md and case_pages_map.json must exist")

    page_map = json.load(open(PMAP, encoding="utf-8"))
    index_text = open(INDEX, encoding="utf-8").read()
    occupied: set[tuple[str, int]] = set()
    expanded: list[tuple[str, list[str]]] = []
    consolidated: dict[str, dict] = {}

    for path in sorted(glob.glob(os.path.join(CASES, "*.md"))):
        case_file = os.path.splitext(os.path.basename(path))[0]
        identity = page_identity(path, page_map)
        if not identity:
            continue
        vol, nums, title = identity
        if not vol or not nums:
            continue
        text = open(path, encoding="utf-8").read()
        for raw in PAGE_MARKER.findall(text):
            occupied.add((vol, int(raw)))

        nums = sorted(dict.fromkeys(nums))
        siblings = expressly_decided_siblings(text, nums)
        merged = sorted(dict.fromkeys(nums + siblings))
        canonical = {"vol": vol, "file": case_file, "numbers": merged, "title": title}

        if merged != nums:
            joined = "/".join(merged)
            text = re.sub(r"^#\s+[^\n]+?(\s+—\s+)", lambda m: f"# {joined}{m.group(1)}", text, count=1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            expanded.append((case_file, merged))
            for n in merged:
                consolidated[n] = dict(canonical)

        # Existing consolidated pages also pass through here on later runs, so normalize the index
        # links every time rather than only on the first discovery run.
        if len(merged) > 1:
            index_text = normalize_consolidated_row(index_text, case_file, merged)

        for n in merged:
            if n not in consolidated:
                page_map[n] = dict(canonical)

    page_map.update(consolidated)

    with open(PMAP, "w", encoding="utf-8") as f:
        json.dump(page_map, f, indent=1)
        f.write("\n")

    lines = index_text.splitlines()
    kept: list[str] = []
    removed: list[tuple[str, int]] = []
    for line in lines:
        m = FALLBACK.search(line)
        if not m:
            kept.append(line)
            continue
        source = (m.group(1), int(m.group(2)))
        if source in PRESERVE_FALLBACK_PAGES:
            kept.append(line)
            continue
        docket = row_docket(line)
        safe_duplicate = source in AUDITED_DUPLICATE_PAGES or (docket is not None and docket in page_map)
        if source in occupied and safe_duplicate:
            removed.append(source)
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

    ga49 = [page_map.get(n) for n in ("2020-07", "2020-08", "2020-09")]
    if not all(x and x.get("file") == "ga49_2022__2020-09" for x in ga49):
        raise SystemExit("GA49 consolidated decision reconciliation failed for 2020-07/08/09")


if __name__ == "__main__":
    main()
