#!/usr/bin/env python3
"""Locate corrected case text by whole-body alignment.

Existing case pages are the noisy fingerprint. Corrected minutes are searched
only inside each page's recorded PDF window. Page shingles nominate plausible
source blocks; the decision is then a normalized Levenshtein similarity over
the entire old body and a proposed reconstructed body. This is non-mutating.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parents[1]
WORD_RE = re.compile(r"[a-z][a-z0-9']{2,}")


def normalize(text: str) -> str:
    """Remove formatting and line-wrap artefacts while retaining word order."""
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text or "")
    return " ".join(WORD_RE.findall(text.lower()))


def normalized_with_offsets(text: str) -> tuple[str, list[int]]:
    """Normalize while retaining a raw-source offset for every output character."""
    cleaned, origins = [], []
    i = 0
    while i < len(text):
        # Join an OCR line-wrap hyphen without losing the source mapping.
        joined = re.match(r"-\s*\n\s*(?=\w)", text[i:])
        if joined:
            i += len(joined.group(0))
            continue
        cleaned.append(text[i].lower())
        origins.append(i)
        i += 1
    compact = "".join(cleaned)
    result, offsets = [], []
    for match in WORD_RE.finditer(compact):
        if result:
            result.append(" ")
            offsets.append(origins[match.start()])
        result.extend(compact[match.start():match.end()])
        offsets.extend(origins[match.start():match.end()])
    return "".join(result), offsets


def case_body(text: str) -> str:
    chunks = text.split("\n---\n")
    return chunks[1] if len(chunks) >= 2 else ""


def git_text(ref: str, path: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True, encoding="utf-8")


def load_case_pages(ga: int, ref: str) -> list[dict]:
    """Load the older case bodies from a git ref, not the working tree."""
    vol_prefix = f"ga{ga:02d}_"
    source_re = re.compile(r"\*Source: \[([^ ]+) p{1,2}\. (\d+)(?:[–-](\d+))?")
    rows = []
    paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", "cases"], cwd=ROOT, text=True, encoding="utf-8"
    ).splitlines()
    for raw_path in paths:
        if not raw_path.endswith(".md"):
            continue
        text = git_text(ref, raw_path)
        source = source_re.search(text)
        if not source or not source.group(1).startswith(vol_prefix):
            continue
        rows.append({
            "case_id": Path(raw_path).stem,
            "title": next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")), Path(raw_path).stem),
            "path": raw_path,
            "old_body": case_body(text),
            "vol": source.group(1),
            "start": int(source.group(2)),
            "end": int(source.group(3) or source.group(2)),
        })
    return rows


def page_chunks(vol: str, start: int, end: int) -> list[dict]:
    path = ROOT / "markdown" / f"{vol}.md"
    source = path.read_text(encoding="utf-8") if path.exists() else ""
    parts = re.split(r"<!--\s*PAGE\s+ga=\d+\s+pdf_page=(\w+)[^>]*-->", source)
    return [
        {"pdf_page": int(parts[i]), "text": re.sub(r'<a id="[^"]*"></a>\s*', "", parts[i + 1]).strip()}
        for i in range(1, len(parts), 2)
        if parts[i].isdigit() and start <= int(parts[i]) <= end
    ]


def whole_score(old: str, candidate: str) -> float:
    """Global normalized Levenshtein similarity of the reconstructed body."""
    left, right = normalize(old), normalize(candidate)
    return Levenshtein.normalized_similarity(left, right) if left and right else 0.0


def old_segments(old: str, first_page: int) -> list[tuple[int, str]]:
    """Split an existing case body at its retained PDF-page markers."""
    marker = r"<!--\s*PAGE\s+ga=\d+\s+pdf_page=(\d+)[^>]*-->"
    parts = re.split(marker, old)
    result = [(first_page, parts[0])]
    for i in range(1, len(parts), 2):
        result.append((int(parts[i]), parts[i + 1]))
    return [(page, text) for page, text in result if normalize(text)]


def match(row: dict, segment_similarity: float, bridge_similarity: float, min_similarity: float,
          include_text: bool = False) -> dict:
    old = row["old_body"]
    segments = old_segments(old, row["start"])
    # Source links can be stale or too narrow even when the existing case body
    # retains authoritative PDF-page markers.  Search the full evidenced span;
    # keep the source-link range separately as the page's displayed provenance.
    segment_pages = [page for page, _ in segments]
    search_start = min([row["start"], *segment_pages])
    search_end = max([row["end"], *segment_pages])
    pages = page_chunks(row["vol"], search_start, search_end)
    corrected_by_page = {page["pdf_page"]: page["text"] for page in pages}
    diagnostics = []
    for page, old_part in segments:
        source = normalize(old_part)
        raw_target = corrected_by_page.get(page, "")
        target, target_offsets = normalized_with_offsets(raw_target)
        if not target:
            diagnostics.append({"pdf_page": page, "status": "missing_page", "segment_similarity": 0.0, "source_coverage": 0.0})
            continue
        alignment = fuzz.partial_ratio_alignment(source, target)
        source_coverage = (alignment.src_end - alignment.src_start) / max(1, len(source))
        similarity = alignment.score / 100
        accepted = similarity >= segment_similarity and source_coverage >= 0.90
        diagnostic = {
            "pdf_page": page, "status": "matched" if accepted else "review",
            "segment_similarity": round(similarity, 4), "source_coverage": round(source_coverage, 4),
            "target_coverage": round((alignment.dest_end - alignment.dest_start) / max(1, len(target)), 4),
        }
        raw_start = target_offsets[alignment.dest_start]
        raw_end = target_offsets[alignment.dest_end - 1] + 1
        diagnostic["_excerpt"] = raw_target[raw_start:raw_end].strip()
        diagnostics.append(diagnostic)

    # A page between two directly verified, consecutive case pages is safe to
    # include at a slightly lower threshold: it is inside an established span,
    # not an isolated fuzzy hit.
    for i in range(1, len(diagnostics) - 1):
        previous, current, following = diagnostics[i - 1:i + 2]
        bounded = (previous["status"] == "matched" and following["status"] == "matched"
                   and previous["pdf_page"] == current["pdf_page"] - 1
                   and following["pdf_page"] == current["pdf_page"] + 1)
        if (current["status"] == "review" and bounded
                and current["segment_similarity"] >= bridge_similarity
                and current["source_coverage"] >= bridge_similarity):
            current["status"] = "bridged"
            current["bridge_evidence"] = [previous["pdf_page"], following["pdf_page"]]

    # For a whole-body decision, retain every aligned source segment.  A weak
    # boundary segment should not be silently dropped when the complete body
    # still clears the requested global-similarity threshold.
    reconstructed = [item["_excerpt"] for item in diagnostics if item["status"] != "missing_page"]
    reconstructed_text = "\n\n".join(reconstructed)
    best_similarity = whole_score(old, reconstructed_text)
    matched_pages = [item["pdf_page"] for item in diagnostics if item["status"] in ("matched", "bridged")]
    bridged_pages = [item["pdf_page"] for item in diagnostics if item["status"] == "bridged"]
    complete = len(matched_pages) == len(diagnostics) and bool(diagnostics)
    candidate_complete = all(item["status"] != "missing_page" for item in diagnostics) and bool(diagnostics)
    for item in diagnostics:
        item.pop("_excerpt", None)
    result = {
        "case_id": row["case_id"], "title": row["title"],
        "case_file": row["path"],
        "indexed_pdf_pages": str(row["start"]) if row["start"] == row["end"] else f"{row['start']}-{row['end']}",
        "search_pdf_pages": str(search_start) if search_start == search_end else f"{search_start}-{search_end}",
        "candidate_spans": [str(page) for page in matched_pages],
        "whole_body_similarity": round(best_similarity, 4),
        "status": "matched" if complete and best_similarity >= min_similarity else "review",
        "candidate_complete": candidate_complete,
        "source_chars": len(old), "candidate_chars": len(reconstructed_text),
        "bridged_pages": bridged_pages,
        "segments": diagnostics,
    }
    if include_text:
        result["_reconstructed_text"] = reconstructed_text
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="main", help="Git ref containing the old case-page fingerprints")
    parser.add_argument("--ga", type=int, default=8)
    parser.add_argument("--segment-similarity", type=float, default=0.85)
    parser.add_argument("--bridge-similarity", type=float, default=0.80)
    parser.add_argument("--min-similarity", type=float, default=0.80)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = [match(row, args.segment_similarity, args.bridge_similarity, args.min_similarity) for row in load_case_pages(args.ga, args.ref)]
    payload = {"ref": args.ref, "ga": args.ga, "segment_similarity": args.segment_similarity, "bridge_similarity": args.bridge_similarity, "min_similarity": args.min_similarity, "results": results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
