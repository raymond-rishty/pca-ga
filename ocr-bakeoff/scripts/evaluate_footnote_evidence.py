"""Evaluate confirmed footnote markers and links against a small gold file.

The gold file is deliberately page-bounded and human-adjudicated.  This
evaluator measures the production policy (confirmed markers and emitted
links), while the detector's candidate/ambiguous records remain available for
recall-oriented review.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def as_values(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values}


def metrics(predicted: set[str], expected: set[str]) -> dict[str, Any]:
    true_positive = len(predicted & expected)
    false_positive = len(predicted - expected)
    false_negative = len(expected - predicted)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": true_positive / (true_positive + false_positive) if true_positive + false_positive else None,
        "recall": true_positive / len(expected) if expected else (1.0 if not predicted else 0.0),
    }


def occurrence_metrics(predicted: list[str], expected: list[str]) -> dict[str, Any]:
    """Measure occurrences as a multiset, retaining duplicate values."""
    predicted_counts = Counter(str(value) for value in predicted)
    expected_counts = Counter(str(value) for value in expected)
    true_positive = sum((predicted_counts & expected_counts).values())
    false_positive = sum((predicted_counts - expected_counts).values())
    false_negative = sum((expected_counts - predicted_counts).values())
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": true_positive / (true_positive + false_positive) if true_positive + false_positive else None,
        "recall": true_positive / len(expected) if expected else (1.0 if not predicted else 0.0),
    }


def sorted_values(values: list[str]) -> list[str]:
    return sorted(values, key=lambda value: (len(value), value))


def evaluate(report: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    gold_pages = gold.get("pages", []) if isinstance(gold, dict) else []
    report_pages = {int(page["page"]): page for page in report.get("pages", [])}
    details = []
    marker_predicted_all: set[str] = set()
    marker_expected_all: set[str] = set()
    link_predicted_all: set[str] = set()
    link_expected_all: set[str] = set()
    marker_predicted_occurrences: list[str] = []
    marker_expected_occurrences: list[str] = []
    link_predicted_occurrences: list[str] = []
    link_expected_occurrences: list[str] = []
    missing_pages = []
    for item in gold_pages:
        page_number = int(item["page"])
        page = report_pages.get(page_number)
        if page is None:
            missing_pages.append(page_number)
            continue
        clusters = page.get("marker_clusters", []) or page.get("markers", [])
        predicted_marker_occurrences = [
            str(cluster.get("value"))
            for cluster in clusters
            if cluster.get("classification") == "confirmed"
        ]
        predicted_link_occurrences = [str(link.get("marker_value")) for link in page.get("links", [])]
        expected_marker_occurrences = [str(value) for value in (item.get("expected_markers", []) or [])]
        expected_link_occurrences = [
            str(value)
            for value in (item.get("expected_links", item.get("expected_markers", [])) or [])
        ]
        predicted_markers = set(predicted_marker_occurrences)
        predicted_links = set(predicted_link_occurrences)
        expected_markers = set(expected_marker_occurrences)
        expected_links = set(expected_link_occurrences)
        marker_predicted_all.update(f"{page_number}:{value}" for value in predicted_markers)
        marker_expected_all.update(f"{page_number}:{value}" for value in expected_markers)
        link_predicted_all.update(f"{page_number}:{value}" for value in predicted_links)
        link_expected_all.update(f"{page_number}:{value}" for value in expected_links)
        marker_predicted_occurrences.extend(f"{page_number}:{value}" for value in predicted_marker_occurrences)
        marker_expected_occurrences.extend(f"{page_number}:{value}" for value in expected_marker_occurrences)
        link_predicted_occurrences.extend(f"{page_number}:{value}" for value in predicted_link_occurrences)
        link_expected_occurrences.extend(f"{page_number}:{value}" for value in expected_link_occurrences)
        details.append(
            {
                "page": page_number,
                "label": item.get("label"),
                "predicted_markers": sorted_values(list(predicted_markers)),
                "expected_markers": sorted_values(list(expected_markers)),
                "marker_metrics": metrics(predicted_markers, expected_markers),
                "marker_occurrences": {
                    "predicted": sorted_values(predicted_marker_occurrences),
                    "expected": sorted_values(expected_marker_occurrences),
                },
                "marker_occurrence_metrics": occurrence_metrics(predicted_marker_occurrences, expected_marker_occurrences),
                "predicted_links": sorted_values(list(predicted_links)),
                "expected_links": sorted_values(list(expected_links)),
                "link_metrics": metrics(predicted_links, expected_links),
                "link_occurrences": {
                    "predicted": sorted_values(predicted_link_occurrences),
                    "expected": sorted_values(expected_link_occurrences),
                },
                "link_occurrence_metrics": occurrence_metrics(predicted_link_occurrences, expected_link_occurrences),
            }
        )
    marker_metrics = metrics(marker_predicted_all, marker_expected_all)
    link_metrics = metrics(link_predicted_all, link_expected_all)
    marker_occurrence_metrics = occurrence_metrics(marker_predicted_occurrences, marker_expected_occurrences)
    link_occurrence_metrics = occurrence_metrics(link_predicted_occurrences, link_expected_occurrences)
    return {
        "schema": "pca-ga.footnote-evaluation.v1",
        "report": report.get("pdf"),
        "gold": gold.get("source") or gold.get("volume"),
        "policy": gold.get("policy", "confirmed_only"),
        "pages_evaluated": len(details),
        "missing_report_pages": missing_pages,
        "marker_metrics": marker_metrics,
        "link_metrics": link_metrics,
        "marker_occurrence_metrics": marker_occurrence_metrics,
        "link_occurrence_metrics": link_occurrence_metrics,
        "details": details,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate confirmed footnote evidence against page-bounded gold labels.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when any evaluated metric has an error")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    result = evaluate(report, gold)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({
        "pages_evaluated": result["pages_evaluated"],
        "missing_report_pages": result["missing_report_pages"],
        "marker": result["marker_metrics"],
        "link": result["link_metrics"],
        "marker_occurrences": result["marker_occurrence_metrics"],
        "link_occurrences": result["link_occurrence_metrics"],
    }, sort_keys=True))
    if args.strict and (
        result["missing_report_pages"]
        or result["marker_metrics"]["false_positive"]
        or result["marker_metrics"]["false_negative"]
        or result["link_metrics"]["false_positive"]
        or result["link_metrics"]["false_negative"]
        or result["marker_occurrence_metrics"]["false_positive"]
        or result["marker_occurrence_metrics"]["false_negative"]
        or result["link_occurrence_metrics"]["false_positive"]
        or result["link_occurrence_metrics"]["false_negative"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
