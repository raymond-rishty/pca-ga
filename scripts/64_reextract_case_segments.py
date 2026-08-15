#!/usr/bin/env python3
"""Re-extract reviewed cases from explicitly selected, non-contiguous pages.

The plan is JSON so every selected page and boundary is auditable.  Each
segment is copied from corrected minutes, with a page marker inserted at every
selected page break.  The case title, source/provenance line, and footer are
left untouched.

Plan shape::

  {
    "cases/example.md": [
      {"page": 52, "start": "### Case heading"},
      {"page": 53, "start": "continuation", "end": "case closing", "include_end": true},
      {"page": 72, "start": "### Adjudication", "end": "### Next matter"}
    ]
  }
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(value)
    return value


extractor = module("structural_case_extractor", "55_reextract_cases_from_formatted_minutes.py")


def replace_body(page: str, body: str) -> str:
    pieces = page.split("\n---\n")
    if len(pieces) < 3:
        raise ValueError("case page has no replaceable body delimiters")
    return "\n---\n".join([pieces[0], "\n" + body.strip() + "\n", *pieces[2:]]).rstrip() + "\n"


def build_body(case_file: Path, plan: list[dict]) -> tuple[str, list[int]]:
    page_text = case_file.read_text(encoding="utf-8")
    source = extractor.SOURCE.search(page_text)
    if not source:
        raise ValueError(f"{case_file}: no recognizable source link")
    volume = source.group(1)
    pages = extractor.source_pages(volume)
    pieces: list[str] = []
    selected_pages: list[int] = []
    for segment in plan:
        first_number = int(segment["page"])
        final_number = int(segment.get("through", first_number))
        if final_number < first_number:
            raise ValueError(f"{case_file}: invalid page range {first_number}–{final_number}")
        numbers = list(range(first_number, final_number + 1))
        for offset, number in enumerate(numbers):
            current = dict(segment)
            current["page"] = number
            # A boundary attached to a range belongs only to its outer page.
            if offset:
                current.pop("start", None)
            if offset < len(numbers) - 1:
                current.pop("end", None)
            start = current.get("start")
            end = current.get("end")
            if number not in pages:
                raise ValueError(f"{case_file}: corrected minutes has no PDF page {number}")
            text = pages[number]["text"]
            if start:
                position = text.find(start)
                if position < 0:
                    raise ValueError(f"{case_file}: page {number} has no start boundary {start!r}")
                text = text[position:]
            if end:
                position = text.find(end)
                if position < 0:
                    raise ValueError(f"{case_file}: page {number} has no end boundary {end!r}")
                text = text[:position + len(end)] if current.get("include_end") else text[:position]
            text = text.strip()
            if not text:
                raise ValueError(f"{case_file}: empty selected segment on page {number}")
            pieces.append(pages[number]["marker"])
            pieces.append(text)
            selected_pages.append(number)
    return "\n\n".join(pieces), selected_pages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    results = []
    for relative, segments in plan.items():
        target = ROOT / relative
        original = target.read_text(encoding="utf-8")
        body, pages = build_body(target, segments)
        updated = replace_body(original, body)
        changed = updated != original
        if args.apply and changed:
            target.write_text(updated, encoding="utf-8")
        results.append({
            "case_file": relative,
            "pages": pages,
            "changed": changed,
            "written": bool(args.apply and changed),
            "body_chars": len(body),
        })
    print(json.dumps({"cases": len(results), "apply": args.apply, "results": results}, indent=2))


if __name__ == "__main__":
    main()
