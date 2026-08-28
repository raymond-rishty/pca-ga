"""Select corrected case spans by whole-body similarity over Markdown blocks.

The old main-branch case body is a noisy fingerprint.  Candidate boundaries are
drawn from complete, PP-Structure-formatted Markdown blocks within the recorded
page window; formatting characters never participate in the score.
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
    parser.add_argument("--ga-from", type=int, default=3)
    parser.add_argument("--ga-to", type=int, default=52)
    parser.add_argument("--context-pages", type=int, default=1)
    parser.add_argument("--boundary-candidates", type=int, default=12)
    parser.add_argument("--threshold", type=float, default=0.80)
    parser.add_argument(
        "--min-boundary-similarity",
        type=float,
        default=0.70,
        help="Require both selected boundary blocks to agree with the old body.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "block_span_case_reextract.json")
    return parser.parse_args()


def blocks_for_window(pages: dict[int, dict], first: int, last: int) -> list[dict]:
    result = []
    for page in range(first, last + 1):
        current = pages.get(page)
        if not current:
            continue
        for text in current["text"].split("\n\n"):
            text = text.strip()
            if matcher.normalize(text):
                result.append({"page": page, "marker": current["marker"], "text": text})
    return result


def boundary_score(reference: str, block: str, leading: bool) -> float:
    source = matcher.normalize(reference)
    target = matcher.normalize(block)
    if not source or not target:
        return 0.0
    widths = (80, 180)
    snippets = [source[:width] if leading else source[-width:] for width in widths if len(source) >= 20]
    return max((fuzz.partial_ratio(snippet, target) / 100 for snippet in snippets), default=0.0)


def render_span(blocks: list[dict], start: int, end: int) -> str:
    output = []
    prior_page = None
    for block in blocks[start : end + 1]:
        if prior_page is not None and block["page"] != prior_page:
            output.append(block["marker"])
        output.append(block["text"])
        prior_page = block["page"]
    return "\n\n".join(output).strip()


def best_span(row: dict, pages_cache: dict[str, dict[int, dict]], args: argparse.Namespace) -> tuple[dict, str | None]:
    segments = matcher.old_segments(row["old_body"], row["start"])
    if not segments:
        return {"case_file": row["path"], "status": "missing_source_segments"}, None
    first_page, first_reference = segments[0]
    last_page, last_reference = segments[-1]
    if row["vol"] not in pages_cache:
        pages_cache[row["vol"]] = extractor.source_pages(row["vol"])
    pages = pages_cache[row["vol"]]
    window_start = max(1, first_page - args.context_pages)
    window_end = last_page + args.context_pages
    blocks = blocks_for_window(pages, window_start, window_end)
    if not blocks:
        return {"case_file": row["path"], "status": "missing_minutes_blocks"}, None
    start_ranked = sorted(
        ((boundary_score(first_reference, block["text"], True), index) for index, block in enumerate(blocks)), reverse=True
    )[: args.boundary_candidates]
    end_ranked = sorted(
        ((boundary_score(last_reference, block["text"], False), index) for index, block in enumerate(blocks)), reverse=True
    )[: args.boundary_candidates]
    best: tuple[float, float, float, int, int, str] | None = None
    for start_score, start in start_ranked:
        for end_score, end in end_ranked:
            if end < start:
                continue
            body = render_span(blocks, start, end)
            score = matcher.whole_score(row["old_body"], body)
            candidate = (score, start_score, end_score, start, end, body)
            if best is None or candidate[:3] > best[:3]:
                best = candidate
    if best is None:
        return {"case_file": row["path"], "status": "no_ordered_boundaries"}, None
    score, start_score, end_score, start, end, body = best
    return {
        "case_file": row["path"], "case_id": row["case_id"], "title": row["title"], "status": "candidate",
        "indexed_pdf_pages": [row["start"], row["end"]],
        "candidate_pdf_pages": [blocks[start]["page"], blocks[end]["page"]],
        "start_block_similarity": round(start_score, 4), "end_block_similarity": round(end_score, 4),
        "whole_body_similarity": round(score, 4), "candidate_chars": len(body),
    }, body


def main() -> None:
    args = parse_args()
    rows = extractor.fingerprint_rows(args.ref)
    pages_cache: dict[str, dict[int, dict]] = {}
    results = []
    for ga in range(args.ga_from, args.ga_to + 1):
        for row in rows.get(ga, []):
            result, body = best_span(row, pages_cache, args)
            result["selected"] = (
                bool(body)
                and result.get("whole_body_similarity", 0.0) >= args.threshold
                and result.get("start_block_similarity", 0.0) >= args.min_boundary_similarity
                and result.get("end_block_similarity", 0.0) >= args.min_boundary_similarity
            )
            result["written"] = False
            if args.apply and result["selected"]:
                target = ROOT / row["path"]
                template = target.read_text(encoding="utf-8") if target.exists() else matcher.git_text(args.ref, row["path"])
                updated = extractor.replace_body(template, body)
                if updated != template:
                    target.write_text(updated, encoding="utf-8")
                    result["written"] = True
            results.append(result)
    payload = {
        "ref": args.ref, "threshold": args.threshold, "context_pages": args.context_pages,
        "boundary_candidates": args.boundary_candidates,
        "min_boundary_similarity": args.min_boundary_similarity,
        "apply": args.apply,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(results), "selected": sum(item["selected"] for item in results), "written": sum(item["written"] for item in results)}, indent=2))


if __name__ == "__main__":
    main()
