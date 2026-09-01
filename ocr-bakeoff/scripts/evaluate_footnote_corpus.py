"""Evaluate corpus scan evidence against page-level note gold labels.

This complements ``evaluate_footnote_evidence.py``.  The page-level evaluator
works on one complete detector report; this evaluator works on the compact
multi-volume scan and measures note-block/note-entry recall, plus optional
confirmed marker and link labels for the same adjudicated pages.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def metrics(predicted: set[str], expected: set[str]) -> dict[str, Any]:
    true_positive = len(predicted & expected)
    false_positive = len(predicted - expected)
    false_negative = len(expected - predicted)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None,
        "recall": true_positive / len(expected) if expected else (1.0 if not predicted else 0.0),
    }


def occurrence_metrics(predicted: list[str], expected: list[str]) -> dict[str, Any]:
    predicted_counts = Counter(str(value) for value in predicted)
    expected_counts = Counter(str(value) for value in expected)
    true_positive = sum((predicted_counts & expected_counts).values())
    false_positive = sum((predicted_counts - expected_counts).values())
    false_negative = sum((expected_counts - predicted_counts).values())
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else None,
        "recall": true_positive / len(expected) if expected else (1.0 if not predicted else 0.0),
    }


def values(item: Any) -> list[str]:
    return [str(value) for value in item] if isinstance(item, list) else []


def page_maps(report: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    positive = {
        int(page["page"]): page
        for page in report.get("pages", [])
        if isinstance(page, dict) and "page" in page
    }
    note_pages = {
        int(page["page"]): page
        for page in report.get("note_pages", [])
        if isinstance(page, dict) and "page" in page
    }
    return positive, note_pages


def evaluate(scan: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    reports = {str(report.get("volume")): report for report in scan.get("reports", [])}
    details = []
    note_block_predicted: set[str] = set()
    note_block_expected: set[str] = set()
    note_value_predicted: list[str] = []
    note_value_expected: list[str] = []
    marker_predicted: set[str] = set()
    marker_expected: set[str] = set()
    link_predicted: set[str] = set()
    link_expected: set[str] = set()
    missing_volumes = []
    missing_note_pages = []

    for item in gold.get("pages", []):
        volume = str(item["volume"])
        page_number = int(item["page"])
        report = reports.get(volume)
        if report is None:
            missing_volumes.append(volume)
            continue
        positive, note_pages = page_maps(report)
        positive_page = positive.get(page_number, {})
        note_page = note_pages.get(page_number, {})
        expected_note_block = bool(item.get("expected_note_block", bool(item.get("expected_note_values"))))
        predicted_note_block = bool(note_page.get("note_block_count", 0))
        page_key = f"{volume}:{page_number}"
        if expected_note_block:
            note_block_expected.add(page_key)
        if predicted_note_block:
            note_block_predicted.add(page_key)
        if expected_note_block and not note_page:
            missing_note_pages.append(page_key)

        expected_notes = values(item.get("expected_note_values", []))
        predicted_notes = [
            str(entry.get("value"))
            for entry in note_page.get("note_entries", [])
            if not entry.get("sequence_anomaly")
        ]
        note_value_expected.extend(f"{page_key}:{value}" for value in expected_notes)
        note_value_predicted.extend(f"{page_key}:{value}" for value in predicted_notes)

        marker_labels = item.get("expected_markers")
        if marker_labels is not None:
            expected_markers = values(marker_labels)
            predicted_markers = values(
                [cluster.get("value") for cluster in positive_page.get("confirmed", [])]
            )
            marker_expected.update(f"{page_key}:{value}" for value in set(expected_markers))
            marker_predicted.update(f"{page_key}:{value}" for value in set(predicted_markers))
        link_labels = item.get("expected_links")
        if link_labels is not None:
            expected_links = values(link_labels)
            predicted_links = values(
                [link.get("marker_value") for link in positive_page.get("links", [])]
            )
            link_expected.update(f"{page_key}:{value}" for value in set(expected_links))
            link_predicted.update(f"{page_key}:{value}" for value in set(predicted_links))

        details.append(
            {
                "volume": volume,
                "page": page_number,
                "label": item.get("label"),
                "predicted_note_block": predicted_note_block,
                "expected_note_block": expected_note_block,
                "predicted_note_values": predicted_notes,
                "expected_note_values": expected_notes,
                "note_value_occurrence_metrics": occurrence_metrics(predicted_notes, expected_notes),
                "predicted_markers": sorted(set(values([cluster.get("value") for cluster in positive_page.get("confirmed", [])]))),
                "predicted_links": sorted(set(values([link.get("marker_value") for link in positive_page.get("links", [])]))),
            }
        )

    result = {
        "schema": "pca-ga.footnote-corpus-evaluation.v1",
        "scan": scan.get("schema"),
        "gold": gold.get("source") or gold.get("name"),
        "pages_evaluated": len(details),
        "missing_volumes": sorted(set(missing_volumes)),
        "missing_note_pages": missing_note_pages,
        "note_block_metrics": metrics(note_block_predicted, note_block_expected),
        "note_value_occurrence_metrics": occurrence_metrics(note_value_predicted, note_value_expected),
        "marker_metrics": metrics(marker_predicted, marker_expected) if marker_expected else None,
        "link_metrics": metrics(link_predicted, link_expected) if link_expected else None,
        "details": details,
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate compact multi-volume footnote scan evidence.")
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = evaluate(
        json.loads(args.scan.read_text(encoding="utf-8")),
        json.loads(args.gold.read_text(encoding="utf-8")),
    )
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "pages_evaluated": result["pages_evaluated"],
                "missing_volumes": result["missing_volumes"],
                "missing_note_pages": result["missing_note_pages"],
                "note_block": result["note_block_metrics"],
                "note_values": result["note_value_occurrence_metrics"],
                "marker": result["marker_metrics"],
                "link": result["link_metrics"],
            },
            sort_keys=True,
        )
    )
    if args.strict:
        checks = [result["note_block_metrics"], result["note_value_occurrence_metrics"]]
        if result["marker_metrics"]:
            checks.append(result["marker_metrics"])
        if result["link_metrics"]:
            checks.append(result["link_metrics"])
        if result["missing_volumes"] or result["missing_note_pages"] or any(
            metric["false_positive"] or metric["false_negative"] for metric in checks
        ):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
