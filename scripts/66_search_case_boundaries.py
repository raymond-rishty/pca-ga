#!/usr/bin/env python3
"""Find case start/end pages by searching the corrected minutes window.

The older structural locator assumed that the first and last retained page
markers were already correct.  This version treats those markers as hints and
searches the full source-link window (with a small pagination allowance) for
the best matching boundary anchors.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("structural", ROOT / "scripts" / "55_reextract_cases_from_formatted_minutes.py")
structural = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(structural)
matcher = structural.matcher


def case_tokens(row: dict) -> set[str]:
    """Return normalized case-number tokens associated with this case."""
    text = f"{row['case_id']} {row.get('title', '')}".lower()
    tokens = set()
    for full_year, number in re.findall(r"((?:19|20)\d{2})[-–](\d{1,2})", text):
        tokens.add(f"{int(full_year)}-{int(number)}")
        tokens.add(f"{int(full_year) % 100:02d}-{int(number)}")
    for year, number in re.findall(r"\b(\d{2})[-–](\d{1,2})\b", text):
        tokens.add(f"{int(year):02d}-{int(number)}")
    for number in re.findall(r"\bcase\s*#?\s*(\d+)\b", text):
        tokens.add(f"case-{int(number)}")
    # Early case files use identifiers such as ga11_1983__case2 rather than
    # spelling the case number in the title.
    for number in re.findall(r"__case(\d+)\b", text):
        tokens.add(f"case-{int(number)}")
    return tokens


def next_matter_heading(line: str, tokens: set[str]) -> bool:
    """Recognize headings that cannot belong to the current case matter."""
    heading = line.lower()
    docket = re.search(r"\b((?:19|20)\d{2}|\d{1,3})[-–](\d{1,3})\b", heading)
    if docket:
        # BCO/section references such as “BCO 31-2” are not new matters.
        # Only treat a docket as a boundary when the heading itself is a
        # case/matter heading or begins with the Assembly docket number.
        if not re.search(r"^###\s+(?:\d{1,3}[-–]\d+|case\b|judicial\b|complaint\b|appeal\b|findings\b)", heading) \
                and not re.search(r"\b(?:case|complaint|appeal|judicial)\b", heading):
            return False
        year = int(docket.group(1))
        number = int(docket.group(2))
        return f"{year}-{number}" not in tokens and f"{year % 100:02d}-{number}" not in tokens
    case_number = re.search(r"\bcase\s*(?:no\.?\s*)?#?\s*(\d+)", heading)
    if case_number:
        token = f"case-{int(case_number.group(1))}"
        return token not in tokens
    if re.search(r"\b(?:judicial\s+case|case\s+no\.?|findings\s+on\s+case|complaint)\b", heading):
        # A numbered heading with no parseable number is ambiguous; leave it
        # alone rather than risking removal of a brief/addendum belonging to
        # the current case.
        return False
    if re.search(r"^###\s+(?:minutes,|recess\b|committee\s+of\s+commissioners\b)", heading):
        return True
    if re.search(r"\b(?:vs\.?|versus)\b", heading):
        return True
    return False


def trim_next_matter(body: str, row: dict) -> tuple[str, str | None]:
    tokens = case_tokens(row)
    for match in re.finditer(r"(?m)^#{2,3}\s+[^\r\n]+", body):
        if match.start() < 200:
            continue
        line = match.group(0)
        if next_matter_heading(line, tokens):
            body = body[:match.start()].rstrip()
            # If the next matter began the page, the page marker is now an
            # orphan and must not claim provenance for an empty page.
            return re.sub(r"\n+<!-- PAGE ga=\d+ pdf_page=\d+[^>]*-->\s*$", "", body).rstrip(), line
    return body, None


def best_boundary(reference: str, pages: dict[int, dict], leading: bool) -> tuple[float, int, int] | None:
    candidates = []
    for page, entry in pages.items():
        located = structural.anchor_location(reference, entry["text"], leading=leading)
        if located:
            score, offset = located
            candidates.append((score, page, offset))
    if not candidates:
        return None
    # For a start, an equally good earlier hit is preferable; for an end,
    # an equally good later hit is preferable.  Score remains primary.
    return max(candidates, key=lambda item: (item[0], -item[1] if leading else item[1]))


def build_candidate(row: dict, pages_cache: dict[str, dict[int, dict]], allowance: int,
                    threshold: float) -> tuple[dict, str | None]:
    segments = matcher.old_segments(row["old_body"], row["start"])
    if not segments:
        return {"case_file": row["path"], "status": "missing_source_segments"}, None
    if row["vol"] not in pages_cache:
        pages_cache[row["vol"]] = structural.source_pages(row["vol"])
    all_pages = pages_cache[row["vol"]]
    low = max(1, min(row["start"], segments[0][0]) - allowance)
    high = max(row["end"], segments[-1][0]) + allowance
    pages = {number: entry for number, entry in all_pages.items() if low <= number <= high}
    if not pages:
        return {"case_file": row["path"], "status": "missing_minutes_page", "span": [low, high]}, None

    start_hit = best_boundary(segments[0][1], pages, leading=True)
    end_hit = best_boundary(segments[-1][1], pages, leading=False)
    search_scope = [low, high]
    # Corrected OCR can move a case well beyond the old marker window (and
    # some volumes contain duplicated or non-monotonic page markers).  When
    # the local search cannot produce an ordered pair, search the complete
    # volume.  The whole-body score below remains the acceptance gate.
    if not start_hit or not end_hit or start_hit[1] > end_hit[1]:
        pages = all_pages
        search_scope = [min(all_pages), max(all_pages)]
        start_hit = best_boundary(segments[0][1], pages, leading=True)
        end_hit = best_boundary(segments[-1][1], pages, leading=False)
    if not start_hit or not end_hit:
        return {"case_file": row["path"], "status": "unlocated_boundary", "search": search_scope}, None
    start_score, first_page, start_offset = start_hit
    end_score, last_page, end_offset = end_hit
    if first_page > last_page:
        return {"case_file": row["path"], "status": "reversed_boundary",
                "start": [first_page, start_score], "end": [last_page, end_score],
                "search": search_scope}, None
    first = all_pages[first_page]["text"]
    last = all_pages[last_page]["text"]
    start_offset = structural.block_start(first, start_offset)
    # The alignment endpoint is the authoritative end of the old case text.
    # Do not expand to the next blank-line block: OCR/layout cleanup can place
    # the next matter's heading in the same paragraph as the case closing.
    if first_page == last_page and start_offset >= end_offset:
        return {"case_file": row["path"], "status": "reversed_boundary",
                "span": [first_page, last_page]}, None
    output = [f"{all_pages[first_page]['marker']}\n\n{first[start_offset:]}".strip()]
    for page in range(first_page + 1, last_page + 1):
        if page not in all_pages:
            return {"case_file": row["path"], "status": "missing_minutes_page",
                    "span": [first_page, last_page]}, None
        text = all_pages[page]["text"]
        if page == last_page:
            text = text[:end_offset]
        output.append(f"{all_pages[page]['marker']}\n\n{text}".strip())
    body = "\n\n".join(part.strip() for part in output if part.strip())
    raw_score = matcher.whole_score(row["old_body"], body)
    trimmed_body, trim_heading = trim_next_matter(body, row)
    trimmed = trimmed_body != body
    body = trimmed_body
    result = {
        "case_file": row["path"], "case_id": row["case_id"], "title": row["title"],
        "status": "candidate", "span": [first_page, last_page],
        "start_anchor_similarity": round(start_score, 4),
        "end_anchor_similarity": round(end_score, 4),
        "whole_body_similarity": round(raw_score, 4), "candidate_chars": len(body),
        "trimmed_next_matter": trimmed,
        "trim_heading": trim_heading,
        "selected": bool(start_score >= threshold and end_score >= threshold and raw_score >= threshold),
    }
    return result, body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="main")
    parser.add_argument("--ga-from", type=int, default=1)
    parser.add_argument("--ga-to", type=int, default=52)
    parser.add_argument("--case-id", action="append", help="Restrict the run to one or more case IDs.")
    parser.add_argument("--allowance", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.80)
    parser.add_argument("--anchor-threshold", type=float)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    anchor_threshold = args.anchor_threshold if args.anchor_threshold is not None else args.threshold
    rows_by_ga = structural.fingerprint_rows(args.ref)
    pages_cache: dict[str, dict[int, dict]] = {}
    results = []
    for ga in range(args.ga_from, args.ga_to + 1):
        for row in rows_by_ga.get(ga, []):
            if args.case_id and row["case_id"] not in args.case_id:
                continue
            result, body = build_candidate(row, pages_cache, args.allowance, anchor_threshold)
            result["written"] = False
            if args.apply and result.get("selected") and body:
                target = ROOT / row["path"]
                template = target.read_text(encoding="utf-8") if target.exists() else matcher.git_text(args.ref, row["path"])
                updated = structural.replace_body(template, body)
                if updated != template:
                    try:
                        target.write_text(updated, encoding="utf-8")
                        result["written"] = True
                    except OSError as error:
                        result["write_error"] = str(error)
            results.append(result)
    payload = {"ref": args.ref, "threshold": args.threshold, "anchor_threshold": anchor_threshold, "allowance": args.allowance,
               "apply": args.apply,
               "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(results), "selected": sum(item.get("selected", False) for item in results),
                      "written": sum(item.get("written", False) for item in results)}, indent=2))


if __name__ == "__main__":
    main()
