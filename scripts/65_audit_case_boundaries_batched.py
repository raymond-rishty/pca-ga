#!/usr/bin/env python3
"""Batch the whole-body case audit without rereading minutes for every case.

This is the corpus-scale companion to ``51_reextract_matched_case_pages.py``.
It keeps the existing matcher and its scoring rules, but caches each corrected
minutes volume and loads the reference case pages in one git archive.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("case_matcher", ROOT / "scripts" / "50_match_case_text_in_reocr.py")
matcher = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(matcher)


def archived_case_pages(ref: str, gas: set[int]) -> list[dict]:
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", ref, "cases"], cwd=ROOT
    )
    source_re = re.compile(r"\*Source: \[([^ ]+) p{1,2}\. (\d+)(?:[–-](\d+))?")
    rows = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        for item in bundle:
            if not item.isfile() or not item.name.endswith(".md"):
                continue
            raw_path = item.name.removeprefix("cases/")
            text = bundle.extractfile(item).read().decode("utf-8").replace("\r\n", "\n")
            source = source_re.search(text)
            if not source:
                continue
            volume = source.group(1)
            match = re.match(r"ga(\d+)_", volume)
            if not match or int(match.group(1)) not in gas:
                continue
            rows.append({
                "case_id": Path(raw_path).stem,
                "title": next((line.lstrip("# ").strip() for line in text.splitlines()
                                if line.startswith("# ")), Path(raw_path).stem),
                "path": f"cases/{raw_path}",
                "old_body": matcher.case_body(text),
                "vol": volume,
                "start": int(source.group(2)),
                "end": int(source.group(3) or source.group(2)),
            })
    return rows


def cached_page_chunks():
    cache: dict[str, dict[int, dict]] = {}
    for path in (ROOT / "markdown").glob("ga*.md"):
        volume = path.stem
        source = path.read_text(encoding="utf-8")
        parts = re.split(r"<!--\s*PAGE\s+ga=\d+\s+pdf_page=(\w+)[^>]*-->", source)
        pages = {}
        for i in range(1, len(parts), 2):
            if parts[i].isdigit():
                number = int(parts[i])
                text = re.sub(r'<a id="[^"]*"></a>\s*', "", parts[i + 1]).strip()
                pages[number] = {"pdf_page": number, "text": text}
        cache[volume] = pages

    def page_chunks(volume: str, start: int, end: int) -> list[dict]:
        return [page for number, page in cache.get(volume, {}).items() if start <= number <= end]

    return page_chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="main")
    parser.add_argument("--ga-from", type=int, default=1)
    parser.add_argument("--ga-to", type=int, default=52)
    parser.add_argument("--segment-similarity", type=float, default=0.85)
    parser.add_argument("--bridge-similarity", type=float, default=0.80)
    parser.add_argument("--min-similarity", type=float, default=0.80)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gas = set(range(args.ga_from, args.ga_to + 1))
    matcher.page_chunks = cached_page_chunks()
    rows = archived_case_pages(args.ref, gas)
    results = []
    for row in rows:
        results.append(matcher.match(row, args.segment_similarity, args.bridge_similarity,
                                     args.min_similarity))
    payload = {"ref": args.ref, "gas": sorted(gas), "cases": len(rows),
               "segment_similarity": args.segment_similarity,
               "bridge_similarity": args.bridge_similarity,
               "min_similarity": args.min_similarity, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cases": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
