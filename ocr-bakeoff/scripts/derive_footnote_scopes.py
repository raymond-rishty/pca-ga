"""Derive reviewable, non-overlapping footnote scopes from indexed case ranges.

The case index is the best existing source for cross-page document boundaries,
but several records intentionally share pages (for example companion cases and
cases printed on the same page).  This tool preserves those raw ranges and
merges only overlapping ranges into deterministic connected components.  The
result can be supplied to the footnote detector, but the raw ranges and overlap
groups remain in the output so a human can review the resolution.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCOPE_SCHEMA = "pca-ga.footnote-scope-candidates.v1"


def volume_ordinal(volume: str) -> int:
    match = re.search(r"ga(\d+)(?:_|$)", volume.lower())
    if not match:
        raise ValueError(f"cannot determine GA ordinal from {volume!r}")
    return int(match.group(1))


def load_case_ranges(path: Path, ordinal: int) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("ga_ordinal") != ordinal:
            continue
        start = record.get("pdf_page_start")
        end = record.get("pdf_page_end", start)
        if not isinstance(start, int) or not isinstance(end, int) or end < start:
            continue
        records.append(
            {
                "case_id": str(record.get("case_id") or f"line-{line_number}"),
                "case_number": record.get("case_number"),
                "title": record.get("title"),
                "start_page": start,
                "end_page": end,
                "source_line": line_number,
            }
        )
    return sorted(records, key=lambda item: (item["start_page"], item["end_page"], item["case_id"]))


def overlap_groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge only overlapping ranges, preserving gaps between cases."""
    groups: list[dict[str, Any]] = []
    for record in records:
        if not groups or record["start_page"] > groups[-1]["end_page"]:
            groups.append(
                {
                    "start_page": record["start_page"],
                    "end_page": record["end_page"],
                    "records": [record],
                }
            )
            continue
        group = groups[-1]
        group["end_page"] = max(group["end_page"], record["end_page"])
        group["records"].append(record)
    return groups


def load_structure_anchors(path: Path) -> list[dict[str, Any]]:
    """Return direct section anchors, ordered by physical PDF page."""
    document = json.loads(path.read_text(encoding="utf-8"))
    anchors = []
    for part in document.get("parts", []):
        children = [child for child in part.get("children", []) if isinstance(child.get("pdf_page"), int)]
        if not children and isinstance(part.get("pdf_page"), int):
            children = [part]
        for child in children:
            anchors.append(
                {
                    "start_page": int(child["pdf_page"]),
                    "label": child.get("label"),
                    "title": child.get("title"),
                    "type": child.get("type"),
                    "parent": part.get("label"),
                }
            )
    # Several metadata nodes can begin on the same page (for example GA14's
    # Judicial Cases and Personal Resolutions).  They describe one physical
    # scope boundary and should not create overlapping ranges.
    grouped: dict[int, dict[str, Any]] = {}
    for anchor in sorted(anchors, key=lambda item: (item["start_page"], str(item.get("label")))):
        group = grouped.setdefault(
            anchor["start_page"],
            {"start_page": anchor["start_page"], "anchors": []},
        )
        group["anchors"].append(anchor)
    return list(grouped.values())


def structure_ranges(
    anchors: list[dict[str, Any]], page_count: int | None = None
) -> list[dict[str, Any]]:
    """Turn physical section starts into disjoint page ranges."""
    ranges = []
    for index, anchor in enumerate(anchors):
        next_start = anchors[index + 1]["start_page"] if index + 1 < len(anchors) else page_count
        if next_start is None:
            continue
        end_page = min(page_count, next_start - 1) if page_count else next_start - 1
        if end_page < anchor["start_page"]:
            continue
        ranges.append(
            {
                "start_page": anchor["start_page"],
                "end_page": end_page,
                "anchors": anchor["anchors"],
            }
        )
    return ranges


def subtract_ranges(
    ranges: list[dict[str, Any]], exclusions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Subtract case components from structural ranges without overlap."""
    result = []
    for source in ranges:
        cursor = source["start_page"]
        for exclusion in exclusions:
            if exclusion["end_page"] < cursor or exclusion["start_page"] > source["end_page"]:
                continue
            if exclusion["start_page"] > cursor:
                result.append(
                    {
                        "start_page": cursor,
                        "end_page": min(source["end_page"], exclusion["start_page"] - 1),
                        "anchors": source.get("anchors", []),
                    }
                )
            cursor = max(cursor, exclusion["end_page"] + 1)
            if cursor > source["end_page"]:
                break
        if cursor <= source["end_page"]:
            result.append(
                {
                    "start_page": cursor,
                    "end_page": source["end_page"],
                    "anchors": source.get("anchors", []),
                }
            )
    return result


def derive(
    volume: str,
    cases_path: Path,
    structure_path: Path | None = None,
    page_count: int | None = None,
) -> dict[str, Any]:
    ordinal = volume_ordinal(volume)
    records = load_case_ranges(cases_path, ordinal)
    groups = overlap_groups(records)
    case_scopes = []
    overlaps = []
    for index, group in enumerate(groups, start=1):
        members = group["records"]
        scope_id = f"{volume}-case-component-{index:03d}"
        case_scopes.append(
            {
                "id": scope_id,
                "start_page": group["start_page"],
                "end_page": group["end_page"],
                "basis": "index/cases.jsonl overlapping-case component",
                "case_ids": [item["case_id"] for item in members],
                "titles": [item["title"] for item in members if item.get("title")],
            }
        )
        if len(members) > 1:
            overlaps.append(
                {
                    "scope_id": scope_id,
                    "page_range": [group["start_page"], group["end_page"]],
                    "case_ids": [item["case_id"] for item in members],
                    "resolution": "merged overlapping ranges; review before production use",
                }
            )
    anchors = load_structure_anchors(structure_path) if structure_path else []
    structural = structure_ranges(anchors, page_count)
    structural_uncovered = subtract_ranges(structural, case_scopes)
    structure_scopes = []
    for index, item in enumerate(structural_uncovered, start=1):
        structure_scopes.append(
            {
                "id": f"{volume}-structure-segment-{index:03d}",
                "start_page": item["start_page"],
                "end_page": item["end_page"],
                "basis": "index/structure physical section anchors",
                "anchors": item.get("anchors", []),
            }
        )
    scopes = sorted(case_scopes + structure_scopes, key=lambda item: (item["start_page"], item["end_page"], item["id"]))
    return {
        "schema": SCOPE_SCHEMA,
        "volume": volume,
        "source": str(cases_path),
        "structure_source": str(structure_path) if structure_path else None,
        "page_count": page_count,
        "review_status": "derived_pending_review",
        "resolution": "overlapping case ranges are merged; structural ranges fill uncovered pages; adjacent ranges remain separate",
        "raw_case_ranges": records,
        "overlap_groups": overlaps,
        "raw_structure_anchors": anchors,
        "case_scopes": case_scopes,
        "structure_scopes": structure_scopes,
        "scopes": scopes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Derive reviewable footnote pairing scopes from indexed cases.")
    parser.add_argument("--volume", required=True, help="Volume such as ga40_2012 or ga40")
    parser.add_argument("--cases", type=Path, default=ROOT / "index" / "cases.jsonl")
    parser.add_argument("--structure", type=Path, help="Structure metadata JSON; defaults to index/structure/<volume>.json")
    parser.add_argument("--pdf", type=Path, help="Optional PDF used to determine total page count")
    parser.add_argument("--page-count", type=int, help="Total PDF pages when --pdf is not supplied")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    structure_path = args.structure or ROOT / "index" / "structure" / f"{args.volume}.json"
    if not structure_path.exists():
        structure_path = None
    page_count = args.page_count
    if args.pdf:
        import pymupdf

        with pymupdf.open(args.pdf) as document:
            page_count = len(document)
    report = derive(args.volume, args.cases, structure_path, page_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "volume": report["volume"],
                "raw_case_ranges": len(report["raw_case_ranges"]),
                "scopes": len(report["scopes"]),
                "overlap_groups": len(report["overlap_groups"]),
                "review_status": report["review_status"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
