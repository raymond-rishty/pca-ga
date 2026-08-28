#!/usr/bin/env python3
"""Audit report-only candidate case files against the current case files."""
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = re.compile(r"<!--\s*PAGE\s+ga=(\d+)\s+pdf_page=(\d+)[^>]*-->")
SOURCE = re.compile(r"^\*Source:.*$", re.M)
WORD = re.compile(r"[a-z][a-z0-9']{2,}")
SEP = "\n---\n"


def normalize(value: str) -> str:
    return " ".join(WORD.findall((value or "").lower()))


def body(value: str) -> str:
    return value.split(SEP, 1)[1].rsplit(SEP, 1)[0] if SEP in value else value


def pages(value: str) -> list[int]:
    return [int(page) for _ga, page in PAGE.findall(body(value))]


def source(value: str) -> str | None:
    match = SOURCE.search(value)
    return match.group(0) if match else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=ROOT / "cases")
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for candidate in sorted(args.candidate_dir.glob("cases/**/*.md")):
        relative = candidate.relative_to(args.candidate_dir)
        base = args.base / relative.relative_to("cases")
        if not base.exists():
            rows.append({"case_file": str(relative).replace("\\", "/"), "status": "missing_base"})
            continue
        old = base.read_text(encoding="utf-8")
        new = candidate.read_text(encoding="utf-8")
        old_body, new_body = body(old), body(new)
        old_pages, new_pages = pages(old), pages(new)
        rows.append({
            "case_file": str(relative).replace("\\", "/"),
            "normalized_similarity": round(difflib.SequenceMatcher(None, normalize(old_body), normalize(new_body)).ratio(), 4),
            "old_pages": old_pages,
            "new_pages": new_pages,
            "page_invariant": old_pages == new_pages,
            "source_invariant": source(old) == source(new),
            "title_invariant": old.splitlines()[:1] == new.splitlines()[:1],
            "old_normalized_chars": len(normalize(old_body)),
            "new_normalized_chars": len(normalize(new_body)),
            "body_shrink": len(normalize(new_body)) < len(normalize(old_body)) * 0.95,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"cases": len(rows), "rows": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "cases": len(rows),
        "page_failures": sum(not row.get("page_invariant", False) for row in rows),
        "source_failures": sum(not row.get("source_invariant", False) for row in rows),
        "title_failures": sum(not row.get("title_invariant", False) for row in rows),
        "body_shrink": sum(row.get("body_shrink", False) for row in rows),
        "similarity_below_0.90": sum(row.get("normalized_similarity", 0) < 0.90 for row in rows),
    }, indent=2))


if __name__ == "__main__":
    main()
