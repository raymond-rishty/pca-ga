"""Build a risk-based and statistically sampled synopsis-review queue."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
import math
from pathlib import Path
import random
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "index/synopsis_workflow/candidate-intake-1/registry.json"
DEFAULT_DECISIONS = ROOT / "index/synopsis_workflow/candidate-intake-1/audit-decisions.json"
DEFAULT_ADJUDICATIONS = ROOT / "index/synopsis_workflow/candidate-intake-1/issue-adjudications.json"
DEFAULT_OUTPUT = ROOT / "index/synopsis_workflow/candidate-intake-1/review-priorities.json"
BENCHMARKS = ROOT / "docs/JUDICIAL-SYNOPSIS-BENCHMARKS.md"
CATALOG = ROOT / "index/judicial_cases.jsonl"
WORD = re.compile(r"[a-z0-9]+")
CASE_ID = re.compile(r"\b(?:19|20)\d{2}-\d{2}[a-z]?\b")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def words(value):
    return WORD.findall((value or "").lower())


def similarity(left, right):
    a, b = " ".join(words(left)), " ".join(words(right))
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def wilson_interval(failures, total, z=1.96):
    if not total:
        return None
    p = failures / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [round(max(0, center - margin), 4), round(min(1, center + margin), 4)]


def acceptability_pass(record):
    """Separate synopsis acceptability from whether an editor made a repair."""
    if "acceptability_pass" in record:
        return record["acceptability_pass"] is True
    return record.get("decision") == "approved"


def benchmark_ids():
    found = set()
    for line in BENCHMARKS.read_text(encoding="utf-8").splitlines():
        if line.startswith("### "):
            match = CASE_ID.search(line)
            if match:
                found.add(match.group(0))
    return found


def source_size(root, candidate, row):
    paths = [item.get("path") for item in candidate.get("sources") or []]
    if row.get("case_page"):
        paths.append("cases/" + row["case_page"] + ".md")
    for value in paths:
        if not value:
            continue
        path = (root / value).resolve()
        if path.is_relative_to(root) and path.is_file():
            return len(path.read_text(encoding="utf-8", errors="replace"))
    return 0


def stratified_sample(records, count, seed):
    groups = defaultdict(list)
    for record in records:
        band = "high" if record["risk_score"] >= 7 else "medium" if record["risk_score"] >= 4 else "low"
        key = (record["provider"], record["matter_type"], band)
        groups[key].append(record)
    rng = random.Random(seed)
    for group in groups.values():
        group.sort(key=lambda item: item["case_id"])
        rng.shuffle(group)
    selected = []
    keys = sorted(groups)
    while len(selected) < count and keys:
        next_keys = []
        for key in keys:
            if groups[key] and len(selected) < count:
                selected.append(groups[key].pop())
            if groups[key]:
                next_keys.append(key)
        keys = next_keys
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--adjudications", type=Path, default=DEFAULT_ADJUDICATIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target", type=int, default=125,
                        help="Minimum total cases in the recommended queue")
    parser.add_argument("--random-sample", type=int, default=30,
                        help="Minimum unbiased sample from cases outside required review")
    parser.add_argument("--seed", type=int, default=149)
    args = parser.parse_args(argv)

    catalog = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            catalog[row.get("case_id") or "roster:" + str(row.get("roster_id"))] = row
    registry = read_json(args.registry)
    decisions = read_json(args.decisions).get("cases", {}) if args.decisions.exists() else {}
    adjudications = read_json(args.adjudications).get("cases", {}) if args.adjudications.exists() else {}
    benchmarks = benchmark_ids()
    records = []

    for entry in registry.get("candidates") or []:
        case_id = entry["case_id"]
        selected = entry["selected"]
        candidate = read_json(ROOT / selected["path"])
        row = catalog[case_id]
        old_summary = row.get("summary") or ""
        new_summary = candidate.get("summary") or ""
        sim = similarity(old_summary, new_summary)
        old_words, new_words = len(words(old_summary)), len(words(new_summary))
        ratio = new_words / old_words if old_words else None
        source_chars = source_size(ROOT, candidate, row)
        reasons, required, impact = [], False, 0
        score = 0
        adjudication = adjudications.get(case_id) or {}
        adjudication_status = adjudication.get("status") or None
        adjudication_open = adjudication_status in {
            "source_repair_required", "candidate_rejected", "canonical_repair_required"
        }

        if selected.get("identity_remapped_from"):
            score += 8; required = not adjudication or adjudication_open
            reasons.append("canonical identity was remapped from " + selected["identity_remapped_from"])
        if candidate.get("matter_type") and candidate.get("matter_type") != row.get("matter_type"):
            score += 8
            reasons.append("candidate changes the matter type")
        candidate_dispositions = candidate.get("final_dispositions") or []
        if candidate_dispositions and candidate_dispositions != (row.get("final_dispositions") or []):
            score += 8
            reasons.append("candidate changes the final disposition")
        if candidate.get("repair_needed") or selected.get("source_hashes_match") is False:
            score += 10
            if not adjudication or adjudication_open:
                required = True
                reasons.append("candidate or registry reports an unresolved source problem")
            else:
                reasons.append("source warning adjudicated: " + adjudication_status)
        if adjudication_open:
            required = True
            reasons.append("adjudication remains open: " + adjudication_status)

        limits = (candidate.get("source_limits") or "").lower()
        if any(term in limits for term in ("incomplete", "truncated", "missing", "not located", "only a notice", "no full")):
            score += 4
            reasons.append("source limitations may affect the holding")
        if not old_summary:
            score += 5; reasons.append("no prior synopsis exists")
        elif sim < .30:
            score += 5; reasons.append("candidate is fundamentally different from the prior synopsis")
        elif sim < .50:
            score += 4; reasons.append("candidate is substantially different from the prior synopsis")
        elif sim < .68:
            score += 2; reasons.append("candidate meaningfully revises the prior synopsis")
        elif sim < .82:
            score += 1; reasons.append("candidate moderately revises the prior synopsis")
        if ratio is not None and (ratio < .55 or ratio > 1.8):
            score += 2; reasons.append("candidate length differs sharply from the prior synopsis")
        if len(candidate_dispositions) > 1:
            score += 2; reasons.append("multiple dispositions require a mixed-outcome check")
        if row.get("matter_type") in {"judicial_reference", "original_jurisdiction_request", "bco_40_5_matter", "review_and_control"}:
            score += 2; reasons.append("special procedural vehicle")
        if row.get("dissent"):
            score += 2; impact += 2; reasons.append("separate opinion or recorded dissent")
        if case_id in benchmarks:
            score += 2; impact += 3; reasons.append("included in the source-checked benchmark set")
        combined = (old_summary + " " + new_summary).lower()
        if any(term in combined for term in ("constitutional", "westminster confession", " wcf ")):
            impact += 2; reasons.append("constitutional or confessional holding")
        if len(row.get("bco_provisions") or []) >= 3:
            impact += 1; reasons.append("addresses several BCO provisions")
        if source_chars > 25000:
            score += 2; reasons.append("long source record")
        elif source_chars > 12000:
            score += 1; reasons.append("substantial source record")
        elif 0 < source_chars < 1800:
            score += 2; reasons.append("sparse source record")
        if new_words < 18 or new_words > 130:
            score += 2; reasons.append("candidate length is outside the normal synopsis range")
        if selected.get("provider") == "deepseek":
            score += 1; reasons.append("DeepSeek candidate retained by the conservative gate")

        records.append({
            "case_id": case_id,
            "provider": selected.get("provider"),
            "matter_type": candidate.get("matter_type") or row.get("matter_type"),
            "risk_score": score,
            "impact_score": impact,
            "required": required,
            "issue_adjudication": adjudication or None,
            "reasons": reasons,
            "metrics": {
                "summary_similarity": round(sim, 4),
                "prior_words": old_words,
                "candidate_words": new_words,
                "source_characters": source_chars,
                "metadata_changed": any("changes the" in reason for reason in reasons),
            },
        })

    required = [item for item in records if item["required"]]
    optional = [item for item in records if not item["required"]]
    optional.sort(key=lambda item: (-item["impact_score"], -item["risk_score"], item["case_id"]))
    priority_slots = max(0, args.target - len(required) - args.random_sample)
    priority = optional[:priority_slots]
    priority_ids = {item["case_id"] for item in priority}
    pool = [item for item in optional if item["case_id"] not in priority_ids]
    sampled = stratified_sample(pool, min(args.random_sample, len(pool)), args.seed)
    sample_ids = {item["case_id"] for item in sampled}
    required_ids = {item["case_id"] for item in required}

    output_cases = {}
    for item in records:
        case_id = item["case_id"]
        if case_id in required_ids:
            basis, group = "required", "must_review"
        elif case_id in priority_ids:
            basis, group = "priority", "high_priority"
        elif case_id in sample_ids:
            basis, group = "statistical_sample", "statistical_sample"
        else:
            basis, group = "not_selected", "remaining"
        output_cases[case_id] = {
            **item,
            "audit_group": group,
            "selected_for_audit": basis != "not_selected",
            "selection_basis": basis,
        }

    sampled_reviewed = [item for item in sampled if decisions.get(item["case_id"], {}).get("decision") in {"approved", "corrected", "rejected", "source_repair"}]
    sampled_failures = [
        item for item in sampled_reviewed
        if not acceptability_pass(decisions[item["case_id"]])
    ]
    interval = wilson_interval(len(sampled_failures), len(sampled_reviewed))
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "method": "all required-risk cases; impact/risk priority fill; fixed stratified random sample by provider, matter type, and risk band",
        "counts": {
            "candidates": len(records),
            "required": len(required),
            "priority": len(priority),
            "statistical_sample": len(sampled),
            "recommended_queue": len(required) + len(priority) + len(sampled),
            "remaining": len(records) - len(required) - len(priority) - len(sampled),
        },
        "statistical_audit": {
            "population_excludes_required_and_priority_cases": True,
            "planned_sample": len(sampled),
            "reviewed_sample": len(sampled_reviewed),
            "observed_failures": len(sampled_failures),
            "observed_failure_rate": round(len(sampled_failures) / len(sampled_reviewed), 4) if sampled_reviewed else None,
            "wilson_95_percent_interval": interval,
            "note": (
                "Acceptability is recorded independently of editorial status, so a "
                "metadata-only correction need not count as a synopsis failure. Records "
                "without an explicit acceptability result retain the legacy rule that only "
                "approved decisions pass. Rebuild after reviews to update the estimate."
            ),
        },
        "cases": output_cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result["counts"], indent=2))
    print("wrote " + str(args.output))


if __name__ == "__main__":
    main()
