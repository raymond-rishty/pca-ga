#!/usr/bin/env python3
"""Publish approved synopsis-review decisions to editorial overrides.

The reviewer state is deliberately non-canonical.  This command verifies each
selected candidate against the hash recorded when it was reviewed, merges only
``approved`` and ``corrected`` decisions into the maintained editorial override
file, and writes a publication receipt.  Rejected, source-repair, and unreviewed
records are never published.

Usage:
    python scripts/80_publish_synopsis_reviews.py
    python scripts/80_publish_synopsis_reviews.py --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECISIONS = ROOT / "index/synopsis_workflow/candidate-intake-1/audit-decisions.json"
DEFAULT_REGISTRY = ROOT / "index/synopsis_workflow/candidate-intake-1/registry.json"
DEFAULT_BASELINE_REPORT = ROOT / "index/synopsis_workflow/candidate-review/offline-review.html"
DEFAULT_OVERRIDES = ROOT / "index/judicial_case_editorial_overrides.json"
DEFAULT_RECEIPT = ROOT / "index/synopsis_workflow/candidate-intake-1/publication-receipt.json"
PUBLISHABLE = {"approved", "corrected"}


def load_json(path: Path):
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_path(root: Path, recorded: str) -> Path:
    path = (root / recorded).resolve()
    if root.resolve() not in path.parents:
        raise ValueError(f"Candidate is outside the repository: {recorded}")
    return path


def load_review_baselines(path: Path) -> dict[str, dict]:
    """Read the maintained catalog snapshot embedded in the offline reviewer."""
    marker = "window.__SYNOPSIS_REVIEW_OFFLINE__="
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        raise ValueError(f"Offline review payload not found: {path}")
    payload = json.loads(text.split(marker, 1)[1].split(";</script>", 1)[0])
    return {
        case_id: item.get("catalog") or {}
        for case_id, item in (payload.get("cases") or {}).items()
    }


def selected_payload(
    case_id: str,
    decision: dict,
    candidate: dict,
    identity_remapped_from: str | None = None,
    prior: dict | None = None,
) -> dict:
    allowed_candidate_ids = {case_id}
    if identity_remapped_from:
        allowed_candidate_ids.add(identity_remapped_from)
    if candidate.get("case_id") not in allowed_candidate_ids:
        raise ValueError(
            f"Candidate identity mismatch for {case_id}: {candidate.get('case_id')}"
        )
    status = decision["decision"]
    payload = decision.get("corrected") if status == "corrected" else candidate
    if not isinstance(payload, dict):
        raise ValueError(f"Missing corrected payload for {case_id}")
    summary = str(payload.get("summary") or "").strip()
    matter_type = payload.get("matter_type")
    dispositions = payload.get("final_dispositions")
    if dispositions is None:
        # Early bake-off candidates used the shorter field name.  Normalize it
        # at publication so the canonical override schema stays consistent.
        dispositions = payload.get("dispositions")
    if not summary or not matter_type or not isinstance(dispositions, list) or not dispositions:
        raise ValueError(f"Incomplete publishable payload for {case_id}")
    result = {
        "summary": summary,
        "summary_review_status": "audited",
        "summary_source": "reviewer_correction" if status == "corrected" else "reviewer_approval",
    }
    # The reviewer primarily adjudicates synopsis prose.  An ordinary approval
    # must not regress taxonomy that was separately checked against the case
    # text.  Explicit corrections replace all three reviewed fields; approvals
    # fill matter/disposition only where the maintained override has no value.
    prior = prior or {}
    if status == "corrected":
        result["matter_type"] = matter_type
        result["final_dispositions"] = dispositions
    else:
        result["matter_type"] = prior.get("matter_type", matter_type)
        result["final_dispositions"] = prior.get("final_dispositions", dispositions)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--baseline-report", type=Path, default=DEFAULT_BASELINE_REPORT)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    decisions_path = args.decisions.resolve()
    registry_path = args.registry.resolve()
    baseline_path = args.baseline_report.resolve()
    overrides_path = args.overrides.resolve()
    receipt_path = args.receipt.resolve()
    decisions = load_json(decisions_path)
    registry = load_json(registry_path)
    overrides = load_json(overrides_path)
    baselines = load_review_baselines(baseline_path)
    registry_cases = {item["case_id"]: item["selected"] for item in registry["candidates"]}

    published = []
    counts = {"approved": 0, "corrected": 0}
    for case_id, decision in sorted((decisions.get("cases") or {}).items()):
        status = decision.get("decision")
        if status not in PUBLISHABLE:
            continue
        selected = registry_cases.get(case_id)
        if not selected:
            raise ValueError(f"Approved case is absent from candidate registry: {case_id}")
        if selected.get("path") != decision.get("candidate_path"):
            raise ValueError(f"Reviewed candidate is no longer selected: {case_id}")
        if selected.get("sha256") != decision.get("candidate_sha256"):
            raise ValueError(f"Registry hash differs from reviewed hash: {case_id}")
        path = candidate_path(root, decision["candidate_path"])
        actual_hash = digest(path)
        expected_hash = decision.get("candidate_sha256")
        if actual_hash != expected_hash:
            raise ValueError(f"Candidate changed after review: {case_id}")
        candidate = load_json(path)
        prior = overrides.get(case_id) or {}
        reviewed_baseline = baselines.get(case_id) or prior
        payload = selected_payload(
            case_id,
            decision,
            candidate,
            selected.get("identity_remapped_from"),
            reviewed_baseline,
        )
        overrides[case_id] = {**prior, **payload}
        counts[status] += 1
        published.append({
            "case_id": case_id,
            "decision": status,
            "candidate_path": decision["candidate_path"],
            "candidate_sha256": expected_hash,
            "reviewer": decision.get("reviewer"),
            "reviewed_at": decision.get("updated_at"),
        })

    receipt = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_decisions": decisions_path.relative_to(root).as_posix(),
        "source_registry": registry_path.relative_to(root).as_posix(),
        "source_baseline_report": baseline_path.relative_to(root).as_posix(),
        "target_overrides": overrides_path.relative_to(root).as_posix(),
        "publication_authorized": bool(args.write),
        "counts": {**counts, "total": len(published)},
        "cases": published,
    }

    print(
        f"publishable={len(published)} approved={counts['approved']} "
        f"corrected={counts['corrected']} mode={'write' if args.write else 'dry-run'}"
    )
    if args.write:
        overrides_path.write_text(
            json.dumps(overrides, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {overrides_path}")
        print(f"wrote {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
