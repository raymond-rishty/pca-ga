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
from collections import defaultdict
from typing import Any

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
IDX = ROOT / "index"
CORRECTIONS = IDX / "overture_catalogue_corrections.jsonl"
CATALOGUE = IDX / "OVERTURES.md"

_HEADING = re.compile(r"^## (\d+)(?:st|nd|rd|th) General Assembly \((\d{4})\).*`(ga\d+_\d{4})`$")
_PAGE = re.compile(r"\[p\.(\d+)\]\(\.\./markdown/([^)#]+)#ga\d+-p\d+\)")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _source_rows() -> tuple[
    dict[tuple[str, int, int], str],
    dict[tuple[str, int, int], dict],
    dict[tuple[str, int], set[str]],
]:
    titles = _jsonl(IDX / "overture_titles.jsonl")
    bodies = _jsonl(IDX / "overture_bodies.jsonl")
    dispositions = _jsonl(IDX / "overture_dispositions.jsonl")

    def key(row: dict) -> tuple[str, int, int]:
        return (str(row.get("vol") or ""), int(row.get("number") or 0), int(row.get("pdf_page") or 0))

    title_by_key = {key(row): (row.get("title") or "").strip() for row in titles}
    titles_by_record: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in titles:
        titles_by_record[(str(row.get("vol") or ""), int(row.get("number") or 0))].add(
            (row.get("title") or "").strip()
        )
    body_by_key: dict[tuple[str, int, int], dict] = {}
    for row in bodies:
        identity = key(row)
        current = body_by_key.get(identity)
        if current is None or len(str(row.get("body") or "")) > len(str(current.get("body") or "")):
            body_by_key[identity] = row
    disposition_by_key = {key(row): row for row in dispositions}
    evidence = {
        k: {**body_by_key.get(k, {}), **disposition_by_key.get(k, {})}
        for k in body_by_key.keys() | disposition_by_key.keys()
    }
    return title_by_key, evidence, titles_by_record


def _source_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _render_row(row: dict[str, Any]) -> str:
    cells = row["cells"]
    cells[0] = row["number_link"]
    cells[1] = row["subject"]
    cells[2] = row["disposition"]
    cells[3] = row["source"]
    cells[4] = ", ".join(link for _, _, link in sorted(row["pages"]))
    return "| " + " | ".join(cells) + " |"


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
            number = int(row.get("number") or 0)
            pages = row.get("pages") or [row.get("pdf_page")]
            structural_rows.update((structure["volume"], number, int(page or 0)) for page in pages)
    if not excludes.issubset(structural_rows):
        raise ValueError(f"exclusions do not match structural source rows: {sorted(excludes - structural_rows)[:12]}")
    titles, evidence, titles_by_record = _source_rows()

    structural_by_key: dict[tuple[str, int, int], dict[str, Any]] = {}
    for path in (IDX / "structure").glob("ga*.json"):
        structure = json.loads(path.read_text(encoding="utf-8"))
        for source_row in structure.get("overtures", []):
            number = int(source_row.get("number") or 0)
            pages = source_row.get("pages") or [source_row.get("pdf_page")]
            for page in pages:
                identity = (structure["volume"], number, int(page or 0))
                structural_by_key.setdefault(identity, source_row)

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
        known_titles = titles_by_record.get((identity[0], identity[1]), set())
        if titles.get(identity) != row.get("title") and row.get("title") not in known_titles:
            raise ValueError(f"title mismatch for {identity}: {row.get('title')!r}")
        source = evidence.get(identity) or {}
        structural_source = structural_by_key.get(identity) or {}
        if not source.get("source") and not structural_source.get("source"):
            raise ValueError(f"missing source or sponsor for {identity}")
        if not source.get("body") and not structural_source.get("source"):
            raise ValueError(f"missing body text or structural source for {identity}")

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
                    page = int(match.group(1))
                    linked_volume = match.group(2).removesuffix(".md")
                    identity = (current["vol"], number, page)
                    if linked_volume == current["vol"] and identity in excludes:
                        continue
                    retained_links.append((linked_volume, page, match.group(0)))
                    pages.append((linked_volume, page, match.group(0)))
                if page_matches:
                    if not retained_links:
                        current["has_rows"] = True
                        continue
                    if len(retained_links) != len(page_matches):
                        cells[4] = ", ".join(link for _, _, link in retained_links)
                    row = {
                        "number": number,
                        "number_link": cells[0],
                        "pages": pages,
                        "subject": cells[1],
                        "disposition": cells[2],
                        "source": cells[3],
                        "cells": cells,
                    }
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
        vol = correction["vol"]
        page_link = f"[p.{page}](../markdown/{vol}.md#ga{ordinal:02}-p{page})"
        number_link = f"[{number}](../overtures/{vol}__o{number}.md)"
        subject = _md(correction["title"])
        source = _md(correction["source"])
        disposition = _md(correction.get("disposition"))

        # When a reviewed correction points to a page already linked in the
        # catalogue, use it to repair the metadata on that row. Otherwise add
        # the source page to an exact same-title/sponsor row when possible.
        identity_row = next((row for row in group["rows"]
                             if row["number"] == number
                             and any(linked_volume == vol and linked_page == page
                                     for linked_volume, linked_page, _ in row["pages"])), None)
        if identity_row is not None:
            identity_row["number_link"] = number_link
            identity_row["subject"] = subject
            identity_row["source"] = source
            if disposition:
                identity_row["disposition"] = disposition
            identity_row["line"] = _render_row(identity_row)
            continue

        matching_row = next((row for row in group["rows"]
                             if row["number"] == number
                             and _source_key(row["subject"]) == _source_key(subject)
                             and _source_key(row["source"]) == _source_key(source)), None)
        if matching_row is not None:
            if not any(linked_volume == vol and linked_page == page
                       for linked_volume, linked_page, _ in matching_row["pages"]):
                matching_row["pages"].append((vol, page, page_link))
            matching_row["number_link"] = number_link
            matching_row["subject"] = subject
            matching_row["source"] = source
            if disposition:
                matching_row["disposition"] = disposition
            matching_row["line"] = _render_row(matching_row)
            continue

        new_row = {
            "number": number,
            "number_link": number_link,
            "pages": [(vol, page, page_link)],
            "subject": subject,
            "disposition": disposition,
            "source": source,
            "cells": [number_link, subject, disposition, source, page_link],
        }
        order = (number, page)
        position = next((i for i, row in enumerate(group["rows"])
                         if (row["number"], min((p for v, p, _ in row["pages"] if v == vol), default=0)) > order),
                         len(group["rows"]))
        group["rows"].insert(position, new_row)

    output = list(intro)
    for group in sections.values():
        output.extend(group["head"])
        output.extend(_render_row(row) for row in group["rows"])
        output.extend(group["tail"])
    CATALOGUE.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {len(includes)} reviewed restorations; removed {len(excludes)} index-only locators -> {CATALOGUE}")

if __name__ == "__main__":
    main()
