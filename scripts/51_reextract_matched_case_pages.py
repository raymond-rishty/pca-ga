#!/usr/bin/env python3
"""Write high-confidence corrected case bodies found by script 50.

The old body always comes from ``--ref`` (normally ``main``); the replacement
comes from the corrected Markdown checked out in this branch.  Page preambles,
titles, source links, and page-range provenance are retained from the current
case page.  Nothing is written unless ``--apply`` is supplied.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("case_matcher", ROOT / "scripts" / "50_match_case_text_in_reocr.py")
matcher = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(matcher)


def replace_body(page: str, body: str) -> str:
    """Replace only the content between the case page's two rule separators."""
    pieces = page.split("\n---\n")
    if len(pieces) < 3:
        raise ValueError("case page has no replaceable body delimiters")
    return "\n---\n".join([pieces[0], "\n" + body.strip() + "\n", *pieces[2:]]).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="main", help="Git ref holding the older case-page fingerprints")
    parser.add_argument("--ga", type=int, action="append", help="Assembly ordinal; repeatable")
    parser.add_argument("--ga-from", type=int, default=1)
    parser.add_argument("--ga-to", type=int, default=18)
    parser.add_argument("--segment-similarity", type=float, default=0.85)
    parser.add_argument("--bridge-similarity", type=float, default=0.80)
    parser.add_argument("--min-similarity", type=float, default=0.80)
    parser.add_argument("--whole-body-threshold", type=float,
                        help="Extract complete candidates at this whole-body score, even if a boundary segment is weak")
    parser.add_argument("--apply", action="store_true", help="Write matched case pages; otherwise report only")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    gas = args.ga or list(range(args.ga_from, args.ga_to + 1))
    results = []
    for ga in gas:
        for row in matcher.load_case_pages(ga, args.ref):
            result = matcher.match(row, args.segment_similarity, args.bridge_similarity, args.min_similarity, include_text=True)
            body = result.pop("_reconstructed_text")
            target = ROOT / row["path"]
            result["written"] = False
            selected = result["status"] == "matched"
            if args.whole_body_threshold is not None:
                selected = (result["candidate_complete"]
                            and result["whole_body_similarity"] >= args.whole_body_threshold)
            result["selected"] = selected
            if args.apply and selected:
                template = target.read_text(encoding="utf-8") if target.exists() else matcher.git_text(args.ref, row["path"])
                updated = replace_body(template, body)
                if updated != template:
                    target.write_text(updated, encoding="utf-8")
                    result["written"] = True
            results.append(result)

    payload = {"ref": args.ref, "gas": gas, "apply": args.apply, "results": results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
