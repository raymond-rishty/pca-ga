#!/usr/bin/env python3
"""Audit main-branch indexed cases against the current re-OCR minutes.

The audit is intentionally non-mutating.  It reads the case roster from a git
ref (default ``main``), extracts each indexed PDF-page window from the current
Markdown, and reports whether distinctive case/title/party tokens are present.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("case_pages", ROOT / "scripts" / "24_case_pages.py")
case_pages = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(case_pages)

STOP = set(
    "the and for from against presbytery church session committee complaint appeal judicial"
    " case report general assembly of in on to vs versus et al no standing commission counsel"
    " matter question concerning regarding teaching elder ruling elder".split()
)


def words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9']{2,}", text or "")]


def distinctive(text: str) -> list[str]:
    seen = []
    for word in words(text):
        if word not in STOP and word not in seen:
            seen.append(word)
    return seen


def variants(*values: str) -> set[str]:
    result = set()
    for value in values:
        for match in re.findall(r"\b\d{2,4}-\d{1,3}[A-Za-z]?\b", value or ""):
            year, number, suffix = re.match(r"(\d{2,4})-(\d{1,3})([A-Za-z]?)", match).groups()
            result.update({f"{year}-{int(number)}{suffix}", f"{year}-{int(number):02d}{suffix}"})
            if len(year) == 4:
                result.update({f"{year[-2:]}-{int(number)}{suffix}", f"{year[-2:]}-{int(number):02d}{suffix}"})
    return result


def load_roster(ref: str, ga: int):
    raw = subprocess.check_output(
        ["git", "show", f"{ref}:index/cases.jsonl"], cwd=ROOT, text=True, encoding="utf-8"
    )
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("ga_ordinal") is not None and int(row["ga_ordinal"]) == ga:
            rows.append(row)
    return rows


def audit(row: dict) -> dict:
    vol = f"ga{int(row['ga_ordinal']):02d}_{row['year']}"
    start = row.get("pdf_page_start")
    end = row.get("pdf_page_end") or start
    if not start:
        return {"case_id": row.get("case_id"), "status": "no_page_range"}
    text = case_pages.page_text(vol, int(start), int(end))
    normalized = " ".join(words(text))
    title = row.get("canonical_title") or row.get("title") or ""
    parties = row.get("parties") or {}
    party_text = " ".join(parties.values()) if isinstance(parties, dict) else str(parties)
    terms = distinctive(f"{title} {party_text}")
    hits = [term for term in terms if re.search(rf"\b{re.escape(term)}\b", normalized)]
    nums = variants(row.get("case_id", ""), row.get("case_number", ""), row.get("canonical_number", ""))
    number_hits = [number for number in nums if number.lower() in normalized]
    hit_ratio = min(1.0, len(hits) / max(1, min(len(terms), 12)))
    pointer_only = bool(re.search(r"(?im)^\s*(?:[-*]\s*)?3\.\s+judicial cases\b", text)) and not bool(
        re.search(r"(?im)^\s*#{0,3}\s*case\s+\d+\s*[:.]?.{0,100}(complaint|adjudicat)", text)
    )
    scope = "exact_window" if int(end) - int(start) <= 3 else "broad_window"
    if pointer_only:
        status = "pointer"
    else:
        status = "located" if len(text) >= 200 and (hit_ratio >= 0.50 or number_hits) else "review"
    evidence = []
    for line in text.splitlines():
        clean = re.sub(r"\s+", " ", line).strip()
        if clean and any(term in clean.lower() for term in hits[:4]):
            evidence.append(clean[:180])
        if len(evidence) == 3:
            break
    return {
        "case_id": row.get("case_id"), "case_number": row.get("case_number"),
        "title": row.get("canonical_title") or row.get("title"), "vol": vol,
        "pdf_pages": f"{start}-{end}", "chars": len(text), "status": status,
        "scope": scope,
        "term_count": len(terms), "term_hits": hits, "number_hits": number_hits,
        "hit_ratio": round(hit_ratio, 3), "evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="main")
    parser.add_argument("--ga", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = [audit(row) for row in load_roster(args.ref, args.ga)]
    payload = {"ref": args.ref, "ga": args.ga, "results": results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
