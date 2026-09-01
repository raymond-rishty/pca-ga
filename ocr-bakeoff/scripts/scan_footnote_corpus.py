"""Scan PP-Structure footnote-region pages across selected PCA volumes.

This is a discovery/reporting pass, not a renderer.  It uses the same
footnote_evidence module as the page-level detector and emits compact page
summaries so a review tranche can be chosen without loading all ambiguous
digits into a report.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("footnote_evidence.py")
SPEC = importlib.util.spec_from_file_location("footnote_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
footnote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(footnote)


def pdf_by_volume() -> dict[str, Path]:
    result = {}
    for path in (ROOT / "minutes").glob("*.pdf"):
        match = re.match(r"(\d+)(?:st|nd|rd|th)_pcaga_(\d{4})\.pdf$", path.name, re.IGNORECASE)
        if match:
            result[f"ga{int(match.group(1)):02d}"] = path
    return result


def pages_for_volume(corpus: Path, use_all_ocr: bool) -> list[int]:
    directory = corpus / ("paddle_ocr_json" if use_all_ocr else "paddle_layout_json")
    pages = []
    for path in directory.glob("page_*.json"):
        match = re.match(r"page_(\d+)\.json$", path.name)
        if match:
            pages.append(int(match.group(1)))
    return sorted(pages)


def compact_note_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Keep note evidence useful for review without copying full OCR prose."""
    result = {
        "page": entry.get("page"),
        "value": entry.get("value"),
        "source": entry.get("source"),
        "block_source": entry.get("block_source"),
        "block_index": entry.get("block_index"),
        "line_index": entry.get("line_index"),
        "bbox": entry.get("bbox"),
        "content_recovered": bool(entry.get("content_recovered")),
        "sequence_anomaly": bool(entry.get("sequence_anomaly")),
    }
    text = str(entry.get("text") or "").strip()
    if text:
        result["text"] = text[:300]
    return result


def cluster_needs_review(cluster: dict[str, Any]) -> bool:
    """Identify unresolved marker decisions worth human adjudication."""
    if cluster.get("classification") == "candidate":
        return True
    if cluster.get("classification") != "ambiguous":
        return False
    if cluster.get("paired_note_entries"):
        return True
    reasons = set(cluster.get("reasons", []))
    return bool(
        reasons.intersection(
            {
                "near_footnote_block",
                "matching_note_number",
                "sequence_support",
                "scope_boundary_blocked",
                "scope_required_for_cross_page",
            }
        )
    )


def compact_page(page: dict[str, Any]) -> dict[str, Any]:
    confirmed = [
        {
            "cluster_id": cluster.get("cluster_id"),
            "value": cluster.get("value"),
            "score": cluster.get("score"),
            "sources": cluster.get("sources", []),
            "reasons": cluster.get("reasons", []),
        }
        for cluster in page.get("marker_clusters", [])
        if cluster.get("classification") == "confirmed"
    ]
    candidates = [
        {
            "cluster_id": cluster.get("cluster_id"),
            "value": cluster.get("value"),
            "score": cluster.get("score"),
            "sources": cluster.get("sources", []),
            "reasons": cluster.get("reasons", []),
        }
        for cluster in page.get("marker_clusters", [])
        if cluster.get("classification") == "candidate"
    ]
    ambiguous = [
        {
            "cluster_id": cluster.get("cluster_id"),
            "value": cluster.get("value"),
            "score": cluster.get("score"),
            "sources": cluster.get("sources", []),
            "reasons": cluster.get("reasons", []),
        }
        for cluster in page.get("marker_clusters", [])
        if cluster.get("classification") == "ambiguous"
        and cluster_needs_review(cluster)
    ]
    review_items = [
        {
            "page": page["page"],
            "cluster_id": cluster.get("cluster_id"),
            "value": cluster.get("value"),
            "classification": cluster.get("classification"),
            "score": cluster.get("score"),
            "sources": cluster.get("sources", []),
            "reasons": cluster.get("reasons", []),
            "witness_count": cluster.get("witness_count", 0),
            "paired_note_entries": [
                compact_note_entry(entry)
                for entry in cluster.get("paired_note_entries", [])
            ],
        }
        for cluster in page.get("marker_clusters", [])
        if cluster_needs_review(cluster)
    ]
    return {
        "page": page["page"],
        "has_layout": page.get("has_layout"),
        "scope_ids": page.get("scope_ids", []),
        "scope_id": page.get("scope_id"),
        "scope_resolved": page.get("scope_resolved"),
        "note_block_count": len(page.get("blocks", [])),
        "note_entries": [
            compact_note_entry({**entry, "page": page["page"]})
            for entry in page.get("note_entries", [])
        ],
        "review_link_count": len(page.get("review_links", [])),
        "note_entry_values": sorted(
            {str(entry.get("value")) for entry in page.get("note_entries", []) if not entry.get("sequence_anomaly")},
            key=lambda value: (len(value), value),
        ),
        "legacy_marker_values": page.get("legacy_marker_values", []),
        "legacy_only_marker_values": page.get("legacy_only_marker_values", []),
        "confirmed": confirmed,
        "candidates": candidates,
        "ambiguous": ambiguous,
        "review_items": review_items,
        "links": page.get("links", []),
    }


def scan_volume(
    volume: str,
    pdf: Path,
    corpus: Path,
    use_all_ocr: bool = False,
    scope_path: Path | None = None,
    legacy_markers: dict[int, set[str]] | None = None,
    legacy_source: str | None = None,
) -> dict[str, Any]:
    pages = []
    document = footnote.pymupdf.open(pdf)
    for number in pages_for_volume(corpus, use_all_ocr):
        ocr_path = corpus / "paddle_ocr_json" / f"page_{number:04d}.json"
        layout_path = corpus / "paddle_layout_json" / f"page_{number:04d}.json"
        page_json = footnote.load_json(ocr_path)
        layout_json = footnote.load_json(layout_path)
        if not use_all_ocr and not layout_json:
            continue
        evidence = footnote.analyze_page(document[number - 1], page_json, layout_json)
        pages.append({
            "page": number,
            "has_ocr": bool(page_json),
            "has_layout": bool(layout_json),
            **evidence,
        })
    scope_value = None
    scopes = None
    if scope_path is not None:
        try:
            scope_value = json.loads(scope_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read scope file {scope_path}: {exc}") from exc
        scopes = footnote.load_scope_records(scope_value)
    footnote.resolve_document(pages, scopes=scopes)
    if legacy_markers is not None:
        footnote.apply_legacy_witness(pages, legacy_markers)
        footnote.rebuild_links(pages)
    compact = [compact_page(page) for page in pages]
    all_links = [
        link
        for page in compact
        for link in [*page.get("links", []), *page.get("review_links", [])]
    ]
    note_review_queue = []
    for page in compact:
        for entry in page.get("note_entries", []):
            if entry.get("sequence_anomaly"):
                continue
            linked = False
            for link in all_links:
                if (
                    int(link.get("note_page", -1)) != int(page["page"])
                    or str(link.get("marker_value")) != str(entry.get("value"))
                ):
                    continue
                note_bbox = link.get("note_bbox")
                entry_bbox = entry.get("bbox")
                if not note_bbox or not entry_bbox:
                    linked = True
                    break
                vertical = min(float(note_bbox[3]), float(entry_bbox[3])) - max(
                    float(note_bbox[1]), float(entry_bbox[1])
                )
                horizontal_gap = max(
                    0.0,
                    max(float(note_bbox[0]), float(entry_bbox[0]))
                    - min(float(note_bbox[2]), float(entry_bbox[2])),
                )
                if vertical > -3.0 and horizontal_gap <= 12.0:
                    linked = True
                    break
            if not linked:
                note_review_queue.append(
                    {
                        "volume": volume,
                        "type": "note_entry_without_marker_pair",
                        "page": page["page"],
                        "scope_id": page.get("scope_id"),
                        "reason": "note_block_has_no_marker_pair_in_selected_pages",
                        "value": entry.get("value"),
                        "source": entry.get("source"),
                        "block_index": entry.get("block_index"),
                        "line_index": entry.get("line_index"),
                        "bbox": entry.get("bbox"),
                        "sequence_anomaly": entry.get("sequence_anomaly"),
                        "text": entry.get("text"),
                    }
                )
    legacy_review_queue = []
    for page in compact:
        note_values = set(page.get("note_entry_values", []))
        for value in page.get("legacy_only_marker_values", []):
            if str(value) not in note_values:
                continue
            matching_entries = [
                entry
                for entry in page.get("note_entries", [])
                if str(entry.get("value")) == str(value)
            ]
            legacy_review_queue.append(
                {
                    "volume": volume,
                    "type": "legacy_only_marker_value",
                    "page": page["page"],
                    "scope_id": page.get("scope_id"),
                    "reason": "legacy_checkpoint_marker_without_current_geometry",
                    "value": str(value),
                    "source": "legacy_checkpoint",
                    "legacy_source": legacy_source,
                    "bbox": None,
                    "note_entries": matching_entries,
                }
            )
    note_review_pages = {item["page"] for item in note_review_queue}
    note_pages = [page for page in compact if page["note_block_count"] > 0]
    positive = [
        page
        for page in compact
        if page["confirmed"]
        or page["candidates"]
        or page["ambiguous"]
        or page["links"]
        or page.get("review_items")
        or any(
            item["page"] == page["page"]
            for item in legacy_review_queue
        )
        or page["page"] in note_review_pages
    ]
    marker_review_queue = [
        {
            "volume": volume,
            "scope_id": page.get("scope_id"),
            **item,
        }
        for page in compact
        for item in page.get("review_items", [])
    ]
    review_queue = marker_review_queue + legacy_review_queue + note_review_queue
    scope_status = scope_value.get("review_status") if isinstance(scope_value, dict) else None
    return {
        "volume": volume,
        "pdf": str(pdf),
        "selection": "all OCR pages" if use_all_ocr else "all pages with paddle_layout_json",
        "scope_source": str(scope_path) if scope_path else None,
        "scope_review_status": scope_status,
        "scope_policy": "unique_equal_scope_required" if scopes is not None else "same_page_only",
        "legacy_witness": legacy_source,
        "summary": {
            "pages": len(pages),
            "pages_with_note_blocks": sum(page["note_block_count"] > 0 for page in compact),
            "pages_with_positive_or_candidate": len(positive),
            "confirmed": sum(
                sum(cluster.get("classification") == "confirmed" for cluster in page.get("marker_clusters", []))
                for page in pages
            ),
            "candidates": sum(
                sum(cluster.get("classification") == "candidate" for cluster in page.get("marker_clusters", []))
                for page in pages
            ),
            "ambiguous": sum(
                sum(cluster.get("classification") == "ambiguous" for cluster in page.get("marker_clusters", []))
                for page in pages
            ),
            "links": sum(len(page["links"]) for page in compact),
            "review_links": sum(page["review_link_count"] for page in compact),
            "review_items": len(review_queue),
            "marker_review_items": len(marker_review_queue),
            "legacy_review_items": len(legacy_review_queue),
            "note_review_items": len(note_review_queue),
            "notes_without_marker_pair": len(note_review_queue),
            "pages_scope_resolved": sum(page.get("scope_resolved") is True for page in compact),
            "pages_scope_unresolved": sum(page.get("scope_resolved") is False for page in compact),
            "cross_page_links": sum(
                int(link.get("marker_page", page["page"])) != int(link.get("note_page", page["page"]))
                for page in compact
                for link in page["links"]
            ),
            "scope_blocked_markers": sum(
                "scope_boundary_blocked" in reason or "scope_required_for_cross_page" in reason
                for page in compact
                for item in page.get("review_items", [])
                for reason in item.get("reasons", [])
            ),
        },
        "pages": positive,
        "note_pages": note_pages,
        "review_queue": review_queue,
    }


def scope_path_for(volume: str, pdf: Path, scope_dir: Path) -> Path:
    """Resolve the exact volume/year scope file, refusing silent fallbacks."""
    year_match = re.search(r"_(\d{4})$", pdf.stem)
    if not year_match:
        raise FileNotFoundError(f"cannot determine year from PDF name for {volume}: {pdf.name}")
    path = scope_dir / f"footnote_scopes_{volume}_{year_match.group(1)}_derived.json"
    if path.exists():
        return path
    raise FileNotFoundError(f"no exact volume/year scope file for {volume}; expected: {path}")


def legacy_path_for(volume: str, pdf: Path, template: str) -> str:
    """Resolve the page-bounded Markdown path for a legacy Git witness."""
    year_match = re.search(r"_(\d{4})$", pdf.stem)
    if not year_match:
        raise FileNotFoundError(f"cannot determine year from PDF name for {volume}: {pdf.name}")
    return template.format(volume=volume, year=year_match.group(1))


def read_legacy_git_markers(
    git_ref: str,
    git_path: str,
) -> tuple[dict[int, set[str]], str]:
    """Read and parse a page-bounded Markdown witness from Git."""
    try:
        result = subprocess.run(
            ["git", "show", f"{git_ref}:{git_path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise FileNotFoundError(
            f"cannot read legacy witness {git_ref}:{git_path}: {detail}"
        ) from exc
    source = f"git:{git_ref}:{git_path}"
    return footnote.legacy_markers_by_page(result.stdout), source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan available PCA footnote-region pages.")
    parser.add_argument("--volumes", required=True, help="Comma-separated corpus names such as ga07,ga14,ga15")
    parser.add_argument("--all-ocr", action="store_true", help="Scan every OCR page instead of layout-selected pages")
    parser.add_argument(
        "--scope-dir",
        type=Path,
        help="Optional directory containing footnote_scopes_<volume>_<year>_derived.json files",
    )
    parser.add_argument(
        "--legacy-git-ref",
        help="Optional Git ref containing a page-bounded Markdown witness",
    )
    parser.add_argument(
        "--legacy-git-path-template",
        default="markdown/{volume}_{year}.md",
        help="Path template used with --legacy-git-ref (default: markdown/{volume}_{year}.md)",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdfs = pdf_by_volume()
    reports = []
    for volume in [item.strip().lower() for item in args.volumes.split(",") if item.strip()]:
        pdf = pdfs.get(volume)
        corpus = ROOT / "ocr-bakeoff" / "corpus" / volume
        if not pdf or not corpus.exists():
            raise SystemExit(f"missing PDF or corpus for {volume}")
        scope_path = scope_path_for(volume, pdf, args.scope_dir) if args.scope_dir else None
        legacy_markers = None
        legacy_source = None
        if args.legacy_git_ref:
            legacy_path = legacy_path_for(volume, pdf, args.legacy_git_path_template)
            legacy_markers, legacy_source = read_legacy_git_markers(
                args.legacy_git_ref,
                legacy_path,
            )
        reports.append(
            scan_volume(
                volume,
                pdf,
                corpus,
                args.all_ocr,
                scope_path=scope_path,
                legacy_markers=legacy_markers,
                legacy_source=legacy_source,
            )
        )
    output = {"schema": "pca-ga.footnote-corpus-scan.v3", "reports": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "scope_policy": "scoped" if args.scope_dir else "same_page_only",
                "volumes": {volume["volume"]: volume["summary"] for volume in reports},
                "review_items": sum(len(volume.get("review_queue", [])) for volume in reports),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
