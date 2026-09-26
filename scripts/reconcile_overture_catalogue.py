#!/usr/bin/env python3
"""Apply reviewed overture catalogue inclusions and exclusions.

Corrections are page-occurrence keyed in index/overture_catalogue_corrections.jsonl.
The generated catalogue keeps reused overture numbers separate and filters only
rows explicitly identified as back-of-volume index locators.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
IDX = ROOT / "index"
CORRECTIONS = IDX / "overture_catalogue_corrections.jsonl"
CATALOGUE = IDX / "OVERTURES.md"

_HEADING = re.compile(r"^## (\d+)(?:st|nd|rd|th) General Assembly \((\d{4})\).*`(ga\d+_\d{4})`$")
_PAGE = re.compile(r"\]\(\.\./markdown/([^)#]+)#ga\d+-p(\d+)\)")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _source_rows() -> tuple[dict[tuple[str, int, int], dict], dict[tuple[str, int, int], dict]]:
    titles = _jsonl(IDX / "overture_titles.jsonl")
    bodies = _jsonl(IDX / "overture_bodies.jsonl")
    dispositions = _jsonl(IDX / "overture_dispositions.jsonl")

    def key(row: dict) -> tuple[str, int, int]:
        return (str(row.get("vol") or ""), int(row.get("number") or 0), int(row.get("pdf_page") or 0))

    title_by_key = {key(row): (row.get("title") or "").strip() for row in titles}
    body_by_key = {key(row): row for row in bodies}
    disposition_by_key = {key(row): row for row in dispositions}
    return title_by_key, {
        k: {**body_by_key.get(k, {}), **disposition_by_key.get(k, {})}
        for k in title_by_key
    }


def main() -> None:
    corrections = _jsonl(CORRECTIONS)
    includes = [row for row in corrections if row.get("action") == "include"]
    excludes = {
        (row.get("vol"), int(row.get("number") or 0), int(row.get("pdf_page") or 0))
        for row in corrections if row.get("action") == "exclude" and row.get("pdf_page")
    }
    structural_rows = set()
    for path in (IDX / "structure").glob("ga*.json"):
        structure = json.loads(path.read_text(encoding="utf-8"))
        for row in structure.get("overtures", []):
            structural_rows.add((structure["volume"], int(row.get("number") or 0),
                                 int(row.get("pdf_page") or 0)))
    if not excludes.issubset(structural_rows):
        raise ValueError(f"exclusions do not match structural source rows: {sorted(excludes - structural_rows)[:12]}")
    titles, evidence = _source_rows()

    # The corrections are an auditable, page-keyed subset of the existing
    # curated source rows. Fail the build if an upstream title or locator drifts.
    seen_ids: set[str] = set()
    for row in includes:
        identity = (row["vol"], int(row["number"]), int(row["pdf_page"]))
        if identity in seen_ids:
            raise ValueError(f"duplicate correction identity: {identity}")
        seen_ids.add(identity)
        if row.get("record_id") != f"overture:{identity[0]}:{identity[1]}:p{identity[2]}":
            raise ValueError(f"unstable record_id for {identity}")
        if titles.get(identity) != row.get("title"):
            raise ValueError(f"title mismatch for {identity}: {row.get('title')!r}")
        source = evidence.get(identity) or {}
        if not source.get("body") or not source.get("source"):
            raise ValueError(f"missing source text or sponsor for {identity}")

    original = CATALOGUE.read_text(encoding="utf-8").splitlines()
    intro: list[str] = []
    sections: dict[int, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    for line in original:
        heading = _HEADING.match(line)
        if heading:
            ordinal = int(heading.group(1))
            current = sections.setdefault(ordinal, {
                "year": int(heading.group(2)), "vol": heading.group(3),
                "head": [], "rows": [], "tail": [], "has_rows": False,
            })
            current["head"].append(line)
            continue
        if current is None:
            intro.append(line)
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")] if line.startswith("| ") else []
        if len(cells) == 5 and not line.startswith(("|---", "| Overture")):
            number_match = re.search(r"\d+", cells[0])
            if number_match:
                number = int(number_match.group())
                page_matches = list(_PAGE.finditer(cells[4]))
                retained_links = []
                pages = []
                for match in page_matches:
                    linked_volume = match.group(1).removesuffix(".md")
                    page = int(match.group(2))
                    identity = (current["vol"], number, page)
                    if linked_volume == current["vol"] and identity in excludes:
                        continue
                    retained_links.append(match.group(0))
                    if linked_volume == current["vol"]:
                        pages.append(page)
                if page_matches:
                    if not retained_links:
                        current["has_rows"] = True
                        continue
                    if len(retained_links) != len(page_matches):
                        cells[4] = ", ".join(retained_links)
                        line = "| " + " | ".join(cells) + " |"
                row = {"number": number, "pages": pages, "subject": cells[1], "line": line}
                current["rows"].append(row)
                current["has_rows"] = True
                continue
        if current["has_rows"]:
            current["tail"].append(line)
        else:
            current["head"].append(line)

    for correction in includes:
        ordinal = int(correction["ga_ordinal"])
        group = sections.get(ordinal)
        if group is None:
            raise ValueError(f"missing Assembly section for correction {correction['record_id']}")
        number = int(correction["number"])
        page = int(correction["pdf_page"])
        if any(row["number"] == number and row["subject"] == correction["title"] for row in group["rows"]):
            continue
        vol = correction["vol"]
        page_link = f"[p.{page}](../markdown/{vol}.md#ga{ordinal:02}-p{page})"
        number_link = f"[{number}](../overtures/{vol}__o{number}.md)"
        line = (f"| {number_link} | {_md(correction['title'])} | {_md(correction.get('disposition'))} "
                f"| {_md(correction['source'])} | {page_link} |")
        new_row = {"number": number, "pages": [page], "subject": correction["title"], "line": line}
        order = (number, page)
        position = next((i for i, row in enumerate(group["rows"])
                         if (row["number"], min(row["pages"] or [0])) > order), len(group["rows"]))
        group["rows"].insert(position, new_row)

    output = list(intro)
    for group in sections.values():
        output.extend(group["head"])
        output.extend(row["line"] for row in group["rows"])
        output.extend(group["tail"])
    CATALOGUE.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {len(includes)} reviewed restorations; removed {len(excludes)} index-only locators -> {CATALOGUE}")

if __name__ == "__main__":
    main()
