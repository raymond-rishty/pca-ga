"""Re-extract reviewed cases as one or more matching Markdown block spans.

Unlike the contiguous-span selector, this compares each corrected-minutes
block to the complete main-branch case body. It can therefore retain a later
adjudication while excluding unrelated docket material between the two spans.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from rapidfuzz import fuzz


ROOT = Path(__file__).resolve().parents[1]


def module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(value)
    return value


matcher = module("case_matcher", "50_match_case_text_in_reocr.py")
extractor = module("structural_case_extractor", "55_reextract_cases_from_formatted_minutes.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main")
    parser.add_argument("--case-id", action="append", required=True)
    parser.add_argument("--block-threshold", type=float, default=0.76)
    parser.add_argument("--whole-threshold", type=float, default=0.80)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "matching_block_case_reextract.json")
    return parser.parse_args()


def score(reference: str, candidate: str) -> float:
    source = matcher.normalize(reference)
    target = matcher.normalize(candidate)
    if len(source) < 20 or len(target) < 20:
        return 0.0
    return fuzz.partial_ratio(target, source) / 100


def matching_body(row: dict, pages_cache: dict[str, dict[int, dict]], threshold: float) -> tuple[dict, str | None]:
    if row["vol"] not in pages_cache:
        pages_cache[row["vol"]] = extractor.source_pages(row["vol"])
    pages = pages_cache[row["vol"]]
    selected: list[dict] = []
    for page_number in range(row["start"], row["end"] + 1):
        page = pages.get(page_number)
        if not page:
            continue
        for block in page["text"].split("\n\n"):
            block = block.strip()
            block_score = score(row["old_body"], block)
            if block_score >= threshold:
                selected.append({"page": page_number, "marker": page["marker"], "text": block, "score": block_score})
    if not selected:
        return {"case_id": row["case_id"], "case_file": row["path"], "status": "no_matching_blocks"}, None

    output = []
    previous_page = None
    for block in selected:
        if previous_page is not None and block["page"] != previous_page:
            output.append(block["marker"])
        output.append(block["text"])
        previous_page = block["page"]
    body = "\n\n".join(output)
    whole_score = matcher.whole_score(row["old_body"], body)
    return {
        "case_id": row["case_id"],
        "case_file": row["path"],
        "title": row["title"],
        "status": "candidate",
        "matched_pdf_pages": sorted({block["page"] for block in selected}),
        "matched_blocks": len(selected),
        "whole_body_similarity": round(whole_score, 4),
        "min_block_similarity": round(min(block["score"] for block in selected), 4),
        "candidate_chars": len(body),
    }, body


def main() -> None:
    args = parse_args()
    rows_by_ga = extractor.fingerprint_rows(args.ref)
    rows = {row["case_id"]: row for group in rows_by_ga.values() for row in group}
    pages_cache: dict[str, dict[int, dict]] = {}
    results = []
    for case_id in args.case_id:
        row = rows.get(case_id)
        if not row:
            results.append({"case_id": case_id, "status": "not_found_in_ref"})
            continue
        result, body = matching_body(row, pages_cache, args.block_threshold)
        result["selected"] = bool(body) and result.get("whole_body_similarity", 0.0) >= args.whole_threshold
        result["written"] = False
        if args.apply and result["selected"]:
            target = ROOT / row["path"]
            template = target.read_text(encoding="utf-8")
            updated = extractor.replace_body(template, body)
            if updated != template:
                target.write_text(updated, encoding="utf-8")
                result["written"] = True
        results.append(result)
    payload = {"ref": args.ref, "block_threshold": args.block_threshold, "whole_threshold": args.whole_threshold, "apply": args.apply, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(results), "selected": sum(item["selected"] for item in results), "written": sum(item["written"] for item in results)}, indent=2))


if __name__ == "__main__":
    main()
