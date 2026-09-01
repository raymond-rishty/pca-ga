"""Adjudicate the remaining ambiguous footnote clusters.

This is a deliberately conservative corpus pass.  The current v3 scan is the
primary report.  A cluster is accepted only when the pre-re-OCR checkpoint
independently classified the same volume/page/cluster as confirmed *and* the
page-level visual review does not show an ordinary number.  Every other
ambiguous cluster receives an explicit rejection reason based on the current
evidence, rather than silently remaining unresolved.

The script also rebuilds the accepted legacy links from the current PDF/OCR
artifacts so the application stage has current marker-line context, then emits
an augmented v3 scan and an adjudicated marker authorization file.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = Path(__file__).with_name("footnote_evidence.py")
SPEC = importlib.util.spec_from_file_location("footnote_evidence", EVIDENCE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load footnote evidence module")
footnote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(footnote)


# The legacy scan supplied useful witnesses, but its broad numeric matching
# also confirmed ordinary numbers in citations, headings, quantities, list
# numbering, and fractions.  These page-level PDF checks are intentionally
# explicit so a later rerun cannot silently re-promote those false witnesses.
CHECKPOINT_REVIEW_REJECTIONS: dict[tuple[str, int, str], str] = {
    ("ga14", 518, "p518-m023"): "pdf_visual_ordinary_citation_reference",
    ("ga14", 518, "p518-m028"): "pdf_visual_ordinary_citation_reference",
    ("ga21", 327, "p327-m001"): "pdf_visual_ordinary_duration_quantity",
    ("ga21", 327, "p327-m007"): "pdf_visual_ordinary_duration_quantity",
    ("ga26", 155, "p155-m002"): "pdf_visual_issue_heading_number",
    ("ga26", 155, "p155-m007"): "pdf_visual_issue_heading_number",
    ("ga33", 109, "p109-m015"): "pdf_visual_ordinary_duration_quantity",
    ("ga39", 637, "p637-m003"): "pdf_visual_ordinary_four_digit_quantity",
    ("ga40", 766, "p766-m001"): "pdf_visual_ordinary_four_digit_quantity",
    ("ga43", 534, "p534-m002"): "pdf_visual_scripture_or_confession_reference",
    ("ga43", 534, "p534-m004"): "pdf_visual_scripture_or_confession_reference",
    ("ga43", 534, "p534-m019"): "pdf_visual_scripture_or_confession_reference",
    ("ga43", 534, "p534-m029"): "pdf_visual_scripture_or_confession_reference",
    ("ga43", 534, "p534-m042"): "pdf_visual_scripture_or_confession_reference",
    ("ga43", 534, "p534-m061"): "pdf_visual_scripture_or_confession_reference",
    ("ga43", 534, "p534-m086"): "pdf_visual_list_number_or_reference",
    ("ga43", 535, "p535-m001"): "pdf_visual_list_number",
    ("ga43", 539, "p539-m003"): "pdf_visual_bco_section_reference",
    ("ga43", 539, "p539-m005"): "pdf_visual_bco_section_reference",
    ("ga43", 539, "p539-m010"): "pdf_visual_bco_section_reference",
    ("ga43", 539, "p539-m012"): "pdf_visual_bco_section_reference",
    ("ga50", 990, "p990-m006"): "pdf_visual_ordinary_fraction",
    ("ga51", 977, "p977-m010"): "pdf_visual_ordinary_four_digit_quantity",
    ("ga51", 1117, "p1117-m014"): "pdf_visual_overture_label",
    ("ga51", 1117, "p1117-m015"): "pdf_visual_overture_label",
}

# Marker-level visual adjudication performed after the initial checkpoint
# pass.  GA48 p.799 is an OCR merge: the PDF visibly contains two adjacent
# superscripts (4 and 5), while Paddle emitted one ambiguous ``45`` token.
# The current v3 report already contains the two native marker witnesses; this
# override records that the merged token is accounted for by those witnesses.
VISUAL_ADJUDICATION_ACCEPTED: dict[tuple[str, int, str], dict[str, Any]] = {
    ("ga48", 799, "p799-m001"): {
        "basis": "pdf_visual_adjacent_superscript_markers_4_and_5",
        "link_cluster_ids": {"p799-m002", "p799-m003"},
    },
}

# The scan can pair an ordinary citation with a nearby note merely because
# the same number occurs in the note block.  GA47 p.574's ``16.9`` is such a
# case; the actual note-9 marker is on p.573.  Exclude this link from the
# adjudicated report and gold authorization.
VISUAL_REVIEW_LINK_EXCLUSIONS: dict[tuple[str, int, str], str] = {
    ("ga47", 574, "p574-m022"): "pdf_visual_ordinary_bco_citation",
    ("ga46", 551, "p551-m016"): "pdf_visual_ordinary_duration_quantity",
    ("ga26", 119, "p119-m001"): "pdf_visual_ordinary_roc_page_reference",
    ("ga26", 119, "p119-m006"): "pdf_visual_ordinary_roc_page_reference",
    ("ga26", 119, "p119-m007"): "pdf_visual_ordinary_roc_page_reference",
    ("ga26", 119, "p119-m008"): "pdf_visual_ordinary_roc_page_reference",
    ("ga26", 119, "p119-m011"): "pdf_visual_ordinary_roc_page_reference",
    ("ga47", 567, "p567-m010"): "pdf_visual_ordinary_omsjc_section_reference",
    ("ga52", 833, "p833-m002"): "pdf_visual_ordinary_charge_label",
    ("ga52", 833, "p833-m003"): "pdf_visual_ordinary_charge_label",
    ("ga52", 832, "p832-m003"): "pdf_visual_ordinary_charge_heading",
    ("ga52", 832, "p832-m021"): "pdf_visual_ordinary_charge_heading",
    ("ga52", 834, "p834-m001"): "pdf_visual_ordinary_charge_incident_label",
}


def volume_pdf_map() -> dict[str, Path]:
    result: dict[str, Path] = {}
    pattern = re.compile(r"(\d+)(?:st|nd|rd|th)_pcaga_(\d{4})\.pdf$", re.IGNORECASE)
    for path in (ROOT / "minutes").glob("*.pdf"):
        match = pattern.match(path.name)
        if match:
            result[f"ga{int(match.group(1)):02d}"] = path
    return result


def scope_path(volume: str, pdf: Path) -> Path | None:
    match = re.search(r"_(\d{4})\.pdf$", pdf.name, re.IGNORECASE)
    if not match:
        return None
    path = ROOT / "tmp" / f"footnote_scopes_{volume}_{match.group(1)}_derived.json"
    return path if path.exists() else None


def key(volume: str, page: Any, cluster_id: Any) -> tuple[str, int, str]:
    return volume, int(page), str(cluster_id)


def iter_clusters(scan: dict[str, Any], classification: str | None = None):
    for report in scan.get("reports", []):
        volume = str(report.get("volume", "")).lower()
        for page in report.get("pages", []):
            for kind in ("confirmed", "candidates", "ambiguous"):
                if classification and kind != classification:
                    continue
                for cluster in page.get(kind, []) or []:
                    yield volume, page, kind, cluster


def compact_cluster(cluster: dict[str, Any]) -> dict[str, Any]:
    return {
        "cluster_id": cluster.get("cluster_id"),
        "value": cluster.get("value"),
        "score": cluster.get("score"),
        "sources": cluster.get("sources", []),
        "reasons": cluster.get("reasons", []),
    }


def legacy_maps(scan: dict[str, Any]) -> tuple[dict[tuple[str, int, str], dict[str, Any]], dict[tuple[str, int, str], list[dict[str, Any]]]]:
    classes: dict[tuple[str, int, str], dict[str, Any]] = {}
    links: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for volume, page, classification, cluster in iter_clusters(scan):
        cluster_key = key(volume, page.get("page"), cluster.get("cluster_id"))
        classes[cluster_key] = {
            "classification": classification,
            "value": cluster.get("value"),
            "score": cluster.get("score"),
            "reasons": cluster.get("reasons", []),
        }
        for link in page.get("links", []) or []:
            if key(volume, link.get("marker_page"), link.get("marker_cluster_id")) == cluster_key:
                links[cluster_key].append(dict(link))
    return classes, links


def reconstruct_legacy_links(
    current: dict[str, Any],
    legacy_classes: dict[tuple[str, int, str], dict[str, Any]],
    legacy_links: dict[tuple[str, int, str], list[dict[str, Any]]],
) -> tuple[dict[tuple[str, int, str], list[dict[str, Any]]], list[dict[str, Any]]]:
    """Recover current-context links for legacy-confirmed current ambiguities."""
    accepted = {
        cluster_key
        for cluster_key, cluster in legacy_classes.items()
        if cluster["classification"] == "confirmed"
        and cluster_key not in CHECKPOINT_REVIEW_REJECTIONS
        and any(
            volume == cluster_key[0]
            and int(page.get("page", -1)) == cluster_key[1]
            and str(item.get("cluster_id")) == cluster_key[2]
            and kind == "ambiguous"
            for volume, page, kind, item in iter_clusters(current)
        )
    }
    by_volume: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for cluster_key in accepted:
        by_volume[cluster_key[0]].append(cluster_key)

    pdfs = volume_pdf_map()
    rebuilt: dict[tuple[str, int, str], list[dict[str, Any]]] = {}
    failures: list[dict[str, Any]] = []
    for volume, cluster_keys in sorted(by_volume.items()):
        pdf = pdfs.get(volume)
        if pdf is None:
            failures.extend({"cluster": list(item), "reason": "missing_volume_pdf"} for item in cluster_keys)
            continue
        legacy = legacy_links
        page_numbers: set[int] = set()
        for cluster_key in cluster_keys:
            for link in legacy.get(cluster_key, []):
                page_numbers.add(int(link["marker_page"]))
                page_numbers.add(int(link["note_page"]))
        if not page_numbers:
            failures.extend({"cluster": list(item), "reason": "legacy_confirmation_has_no_link"} for item in cluster_keys)
            continue

        document = footnote.pymupdf.open(pdf)
        pages: list[dict[str, Any]] = []
        try:
            for number in sorted(page_numbers):
                ocr_path = ROOT / "ocr-bakeoff" / "corpus" / volume / "paddle_ocr_json" / f"page_{number:04d}.json"
                layout_path = ROOT / "ocr-bakeoff" / "corpus" / volume / "paddle_layout_json" / f"page_{number:04d}.json"
                if number < 1 or number > len(document):
                    failures.append({"cluster": [volume, number, ""], "reason": "page_out_of_pdf_range"})
                    continue
                pages.append(
                    {
                        "page": number,
                        **footnote.analyze_page(
                            document[number - 1],
                            footnote.load_json(ocr_path),
                            footnote.load_json(layout_path),
                        ),
                    }
                )
        finally:
            document.close()

        scopes = None
        scope_file = scope_path(volume, pdf)
        if scope_file:
            scopes = footnote.load_scope_records(json.loads(scope_file.read_text(encoding="utf-8")))
        footnote.resolve_document(pages, scopes=scopes)

        legacy_values: dict[int, set[str]] = defaultdict(set)
        for cluster_key in cluster_keys:
            for link in legacy.get(cluster_key, []):
                legacy_values[int(link["marker_page"])].add(str(link["marker_value"]))
        footnote.apply_legacy_witness(pages, legacy_values)
        footnote.rebuild_links(pages)

        by_key = {
            key(volume, page.get("page"), link.get("marker_cluster_id")): link
            for page in pages
            for link in page.get("links", [])
        }
        for cluster_key in cluster_keys:
            matches = []
            for old_link in legacy.get(cluster_key, []):
                current_key = key(volume, old_link.get("marker_page"), old_link.get("marker_cluster_id"))
                link = by_key.get(current_key)
                if link is None:
                    failures.append({"cluster": list(cluster_key), "reason": "current_context_link_not_reconstructed"})
                    continue
                matches.append(dict(link))
            if matches:
                rebuilt[cluster_key] = matches
    return rebuilt, failures


def rejection_basis(cluster: dict[str, Any]) -> str:
    reasons = set(cluster.get("reasons", []))
    if "citation_like_context" in reasons:
        return "citation_like_context_without_native_or_checkpoint_confirmation"
    if "scope_boundary_blocked" in reasons or "scope_unresolved" in reasons:
        return "no_deterministic_same_case_scope_for_ambiguous_pair"
    if "near_footnote_block" in reasons or "matching_note_number" in reasons:
        return "OCR_or_layout_pair_without_independent_marker_typography"
    return "insufficient_independent_marker_evidence"


def add_link_to_report(merged: dict[str, Any], cluster_key: tuple[str, int, str], links: list[dict[str, Any]]) -> bool:
    volume, page_number, cluster_id = cluster_key
    for report in merged.get("reports", []):
        if str(report.get("volume", "")).lower() != volume:
            continue
        for page in report.get("pages", []):
            if int(page.get("page", -1)) != page_number:
                continue
            existing_ids = {
                str(item.get("marker_cluster_id"))
                for item in page.get("links", []) or []
            }
            for link in links:
                if str(link.get("marker_cluster_id")) not in existing_ids:
                    page.setdefault("links", []).append(link)
            page["ambiguous"] = [
                item for item in page.get("ambiguous", []) or []
                if str(item.get("cluster_id")) != cluster_id
            ]
            page["review_items"] = [
                item for item in page.get("review_items", []) or []
                if str(item.get("cluster_id")) != cluster_id
            ]
            current_confirmed = {
                str(item.get("cluster_id")) for item in page.get("confirmed", []) or []
            }
            if cluster_id not in current_confirmed:
                source = links[0]
                page.setdefault("confirmed", []).append(
                    {
                        "cluster_id": cluster_id,
                        "value": source.get("marker_value"),
                        "score": source.get("score"),
                        "sources": source.get("marker_sources", []),
                        "reasons": ["legacy_checkpoint_marker", "adjudicated_legacy_rescue"],
                    }
                )
            return True
    return False


def apply_visual_link_exclusions(merged: dict[str, Any]) -> list[dict[str, Any]]:
    removed: list[dict[str, Any]] = []
    for report in merged.get("reports", []):
        volume = str(report.get("volume", "")).lower()
        for page in report.get("pages", []):
            page_number = int(page.get("page", -1))
            for cluster_id, basis in VISUAL_REVIEW_LINK_EXCLUSIONS.items():
                if cluster_id[0] != volume or cluster_id[1] != page_number:
                    continue
                before = len(page.get("links", []) or [])
                page["links"] = [
                    link for link in page.get("links", []) or []
                    if str(link.get("marker_cluster_id")) != cluster_id[2]
                ]
                page["confirmed"] = [
                    item for item in page.get("confirmed", []) or []
                    if str(item.get("cluster_id")) != cluster_id[2]
                ]
                if len(page["links"]) != before:
                    removed.append({
                        "volume": volume,
                        "page": page_number,
                        "cluster_id": cluster_id[2],
                        "basis": basis,
                    })
    return removed


def build_gold(merged: dict[str, Any]) -> dict[str, Any]:
    values: dict[tuple[str, int], set[str]] = defaultdict(set)
    for report in merged.get("reports", []):
        volume = str(report.get("volume", "")).lower()
        for page in report.get("pages", []):
            for link in page.get("links", []) or []:
                if link.get("classification", "confirmed") == "confirmed":
                    values[(volume, int(page["page"]))].add(str(link.get("marker_value")))
    pages = [
        {
            "volume": volume,
            "page": page,
            "label": "corpus-confirmed-or-adjudicated-footnote-markers",
            "expected_markers": sorted(markers, key=lambda value: (len(value), value)),
            "expected_links": sorted(markers, key=lambda value: (len(value), value)),
        }
        for (volume, page), markers in sorted(values.items())
    ]
    return {
        "schema": "pca-ga.footnote-gold-adjudicated.v1",
        "source": "v3 scan plus pre-re-OCR checkpoint rescues",
        "policy": "confirmed current links plus independently checkpoint-confirmed ambiguous clusters",
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--legacy", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--merged-report", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    args = parser.parse_args()

    current = json.loads(args.current.read_text(encoding="utf-8"))
    legacy = json.loads(args.legacy.read_text(encoding="utf-8"))
    legacy_classes, legacy_links = legacy_maps(legacy)
    rebuilt, reconstruction_failures = reconstruct_legacy_links(current, legacy_classes, legacy_links)

    merged = copy.deepcopy(current)
    excluded_links = apply_visual_link_exclusions(merged)
    decisions: list[dict[str, Any]] = []
    accepted = 0
    rejected = 0
    visual_accepted = 0
    for volume, page, classification, cluster in iter_clusters(current, "ambiguous"):
        cluster_key = key(volume, page.get("page"), cluster.get("cluster_id"))
        manual_basis = CHECKPOINT_REVIEW_REJECTIONS.get(cluster_key)
        if manual_basis:
            rejected += 1
            decisions.append(
                {
                    "volume": volume,
                    "page": int(page["page"]),
                    "cluster_id": cluster.get("cluster_id"),
                    "value": str(cluster.get("value")),
                    "original_classification": "ambiguous",
                    "decision": "rejected",
                    "basis": manual_basis,
                }
            )
            continue
        visual_override = VISUAL_ADJUDICATION_ACCEPTED.get(cluster_key)
        if visual_override:
            link_ids = set(visual_override.get("link_cluster_ids", set()))
            visual_links = [
                link
                for item in merged.get("reports", [])
                if str(item.get("volume", "")).lower() == volume
                for candidate_page in item.get("pages", [])
                if int(candidate_page.get("page", -1)) == int(page["page"])
                for link in candidate_page.get("links", []) or []
                if str(link.get("marker_cluster_id")) in link_ids
            ]
            if visual_links and add_link_to_report(merged, cluster_key, visual_links):
                accepted += 1
                visual_accepted += 1
                decisions.append(
                    {
                        "volume": volume,
                        "page": int(page["page"]),
                        "cluster_id": cluster.get("cluster_id"),
                        "value": str(cluster.get("value")),
                        "original_classification": "ambiguous",
                        "decision": "accepted",
                        "basis": visual_override["basis"],
                        "materialization_links": len(visual_links),
                    }
                )
                continue
        links = rebuilt.get(cluster_key, [])
        if links and add_link_to_report(merged, cluster_key, links):
            accepted += 1
            decisions.append(
                {
                    "volume": volume,
                    "page": int(page["page"]),
                    "cluster_id": cluster.get("cluster_id"),
                    "value": str(cluster.get("value")),
                    "original_classification": "ambiguous",
                    "decision": "accepted",
                    "basis": "independent_pre_ocr_checkpoint_confirmed_same_cluster",
                    "materialization_links": len(links),
                }
            )
        else:
            rejected += 1
            decisions.append(
                {
                    "volume": volume,
                    "page": int(page["page"]),
                    "cluster_id": cluster.get("cluster_id"),
                    "value": str(cluster.get("value")),
                    "original_classification": "ambiguous",
                    "decision": "rejected",
                    "basis": rejection_basis(cluster),
                }
            )

    for report in merged.get("reports", []):
        for page in report.get("pages", []):
            report_volume = str(report.get("volume", "")).lower()
            page["links"] = page.get("links", []) or []
            report.setdefault("summary", {})["links"] = sum(
                len(item.get("links", []) or []) for item in report.get("pages", [])
            )
            report["summary"]["confirmed"] = sum(
                len(item.get("confirmed", []) or []) for item in report.get("pages", [])
            )
            report["summary"]["ambiguous"] = sum(
                len(item.get("ambiguous", []) or []) for item in report.get("pages", [])
            )
            report["summary"]["adjudicated_rejected_ambiguous"] = sum(
                item.get("decision") == "rejected"
                for item in decisions
                if item.get("volume") == report_volume and int(item.get("page", -1)) == int(page.get("page", -2))
            )

    args.decisions.parent.mkdir(parents=True, exist_ok=True)
    args.decisions.write_text(
        json.dumps(
            {
                "schema": "pca-ga.footnote-adjudication.v1",
                "current_report": str(args.current),
                "legacy_report": str(args.legacy),
                "policy": "accept independent checkpoint confirmation or explicit marker-level PDF adjudication after visual review excludes ordinary numeric context; explicitly reject all remaining ambiguous clusters",
                "summary": {
                    "input_ambiguous": len(decisions),
                    "accepted": accepted,
                    "rejected": rejected,
                    "visual_accepted": visual_accepted,
                    "excluded_current_links": len(excluded_links),
                    "reconstruction_failures": len(reconstruction_failures),
                },
                "excluded_current_links": excluded_links,
                "reconstruction_failures": reconstruction_failures,
                "decisions": decisions,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    args.merged_report.parent.mkdir(parents=True, exist_ok=True)
    args.merged_report.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.gold.parent.mkdir(parents=True, exist_ok=True)
    args.gold.write_text(json.dumps(build_gold(merged), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "decisions": str(args.decisions),
                "merged_report": str(args.merged_report),
                "gold": str(args.gold),
                "input_ambiguous": len(decisions),
                "accepted": accepted,
                "rejected": rejected,
                "visual_accepted": visual_accepted,
                "excluded_current_links": len(excluded_links),
                "reconstruction_failures": len(reconstruction_failures),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
