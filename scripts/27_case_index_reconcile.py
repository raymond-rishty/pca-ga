#!/usr/bin/env python3
"""Reconcile checked-in judicial-case artefacts without rebuilding the SQLite corpus.

The structure-first publisher normally owns case pages and the case-page map, but a clean GitHub
Pages checkout intentionally does not contain the analysis database/caches needed to rerun that
publisher.  This small reconciliation pass therefore treats the checked-in ``cases/*.md`` pages as
the evidence it can safely inspect during deployment.

It repairs two recurring extraction artefacts:

1. A consolidated SJC decision may be printed under only one docket-number heading while its
   holding expressly disposes of sibling dockets.  Add those sibling numbers to the existing
   case-page map and index row, and make the case-page heading reflect the consolidated decision.
2. The cases table contains duplicate/mis-paged fallback rows.  A row labelled
   ``no separate decision located`` is noise when its reported PDF page is already physically
   present inside an extracted case page.  Suppress it.

Discovery deliberately scans every checked-in case page instead of relying on case_pages_map.json.
That is important because an omitted docket can coincide with an incomplete map: the very defect
this script is meant to repair must not prevent the page from being inspected.
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
# We do not require the whole holding to fit one fragile regex.  First identify sentence-ish text
# that contains a disposition verb, then collect case numbers only when the same sentence expressly
# speaks of a Complaint/Appeal/Petition and Case No(s).  That excludes ordinary precedent cites.
DISPOSITION = re.compile(
    r"(?i)\b(?:is|are|be|was|were)\s+(?:partially\s+|in\s+part\s+)?"
    r"(?:sustained|denied|dismissed|granted|affirmed|reversed|annulled|"
    r"out\s+of\s+order|not\s+sustained)\b"
)
HOLDING_CASE = re.compile(
    r"(?i)\b(?:complaints?|appeals?|petitions?)\b[^.!?]{0,260}?\bcase\s+nos?\.?(?:\s|$)"
)
FALLBACK = re.compile(
    r"_no separate decision located_\s*·\s*\[(ga\d+_\d+)\s+p\.(\d+)\]",
    re.I,
)
FILE_VOL = re.compile(r"^(ga\d+_\d+)__(.+)$")


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
    # Page comments and hard line wrapping can interrupt a holding.  Strip comments and collapse
    # whitespace before splitting into sentence-ish chunks.
    flat = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    flat = re.sub(r"\s+", " ", flat)
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", flat):
        if not DISPOSITION.search(sentence) or not HOLDING_CASE.search(sentence):
            continue
        for raw in (m.group(0) for m in CASE_NUM.finditer(sentence)):
            n = norm_num(raw)
            # Consolidated dockets are contemporaneous.  This guards against an older precedent
            # mentioned in the same paragraph without needing the unavailable database roster.
            if years and all(abs(int(n[:4]) - y) > 2 for y in years):
                continue
            if n not in out:
                out.append(n)
    return out


def page_identity(path: str, page_map: dict[str, dict]) -> tuple[str, list[str], str] | None:
    """Return (volume, known docket numbers, title) for a checked-in case page.

    Prefer page-map metadata when present, but recover identity from the stable filename/heading
    when the map itself is incomplete.
    """
    case_file = os.path.splitext(os.path.basename(path))[0]
    mapped = next((v for v in page_map.values() if v.get("file") == case_file), None)
    if mapped:
        return mapped.get("vol", ""), [norm_num(x) for x in mapped.get("numbers", [])], mapped.get("title", "")

    fm = FILE_VOL.match(case_file)
    if not fm:
        return None
    vol, tail = fm.groups()
    nums = [norm_num(x) for x in CASE_NUM.findall(tail.replace("_", " "))]
    # CASE_NUM.findall returns groups when used this way; recover from the filename explicitly.
    nums = [norm_num(m.group(0)) for m in CASE_NUM.finditer(tail.replace("_", " "))]
    if not nums:
        return None
    first = open(path, encoding="utf-8").readline().strip()
    title = re.sub(r"^#\s*", "", first)
    title = re.sub(r"^.*?\s+—\s+", "", title)
    return vol, nums, title


def main() -> None:
    if not os.path.exists(INDEX) or not os.path.exists(PMAP):
        raise SystemExit("CASES.md and case_pages_map.json must exist")

    page_map = json.load(open(PMAP, encoding="utf-8"))
    index_text = open(INDEX, encoding="utf-8").read()
    occupied: set[tuple[str, int]] = set()
    expanded: list[tuple[str, list[str]]] = []

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

        # Ensure even an incompletely mapped existing page has a canonical map entry.
        canonical = {"vol": vol, "file": case_file, "numbers": merged, "title": title}
        if merged != nums:
            joined = "/".join(merged)
            text = re.sub(r"^#\s+[^\n]+?(\s+—\s+)", lambda m: f"# {joined}{m.group(1)}", text, count=1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

            # Change the docket label wherever the index already links to this stable case URL.
            pat = re.compile(r"(\|\s*\[)[^\]]+(\]\(\.\./cases/" + re.escape(case_file) + r"\.md\))")
            index_text = pat.sub(lambda m: m.group(1) + joined + m.group(2), index_text)
            expanded.append((case_file, merged))

        for n in merged:
            page_map[n] = dict(canonical)

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

    # Regression guard for the defect that prompted this reconciliation.  If the known GA49
    # consolidated decision is present, all three docket numbers must map to the same page.
    ga49 = [page_map.get(n) for n in ("2020-07", "2020-08", "2020-09")]
    if any(ga49) and not all(x and x.get("file") == "ga49_2022__2020-09" for x in ga49):
        raise SystemExit("GA49 consolidated decision reconciliation failed for 2020-07/08/09")


if __name__ == "__main__":
    main()
