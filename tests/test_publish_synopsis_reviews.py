import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "80_publish_synopsis_reviews.py"
SPEC = importlib.util.spec_from_file_location("publish_synopsis_reviews", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def candidate_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_selected_payload_uses_candidate_for_approval():
    candidate = {
        "case_id": "2000-01",
        "summary": "Approved summary.",
        "matter_type": "complaint",
        "final_dispositions": ["sustained"],
    }
    result = MODULE.selected_payload("2000-01", {"decision": "approved"}, candidate)
    assert result["summary"] == "Approved summary."
    assert result["summary_source"] == "reviewer_approval"


def test_selected_payload_uses_correction():
    decision = {
        "decision": "corrected",
        "corrected": {
            "summary": "Corrected summary.",
            "matter_type": "appeal",
            "final_dispositions": ["denied"],
        },
    }
    result = MODULE.selected_payload(
        "2000-02",
        decision,
        {
            "case_id": "2000-02",
            "summary": "Candidate summary.",
            "matter_type": "appeal",
            "final_dispositions": ["granted"],
        },
    )
    assert result["summary"] == "Corrected summary."
    assert result["final_dispositions"] == ["denied"]
    assert result["summary_source"] == "reviewer_correction"


def test_selected_payload_normalizes_legacy_dispositions():
    candidate = {
        "case_id": "1975-01",
        "summary": "Approved summary.",
        "matter_type": "complaint",
        "dispositions": ["dismissed"],
    }
    result = MODULE.selected_payload("1975-01", {"decision": "approved"}, candidate)
    assert result["final_dispositions"] == ["dismissed"]


def test_selected_payload_allows_registry_identity_remap():
    candidate = {
        "case_id": "1988-05",
        "summary": "Approved summary.",
        "matter_type": "complaint",
        "final_dispositions": ["dismissed"],
    }
    result = MODULE.selected_payload("1988-08", {"decision": "approved"}, candidate, "1988-05")
    assert result["summary"] == "Approved summary."


def test_approval_preserves_maintained_taxonomy():
    candidate = {
        "case_id": "2007-14",
        "summary": "Approved summary.",
        "matter_type": "appeal",
        "final_dispositions": ["dismissed", "guilty"],
    }
    result = MODULE.selected_payload(
        "2007-14",
        {"decision": "approved"},
        candidate,
        prior={"matter_type": "appeal", "final_dispositions": ["guilty", "dismissed"]},
    )
    assert result["matter_type"] == "appeal"
    assert result["final_dispositions"] == ["guilty", "dismissed"]


def test_digest_detects_candidate_change(tmp_path):
    path = tmp_path / "candidate.json"
    write_json(path, {"case_id": "2000-03"})
    before = candidate_hash(path)
    write_json(path, {"case_id": "2000-04"})
    assert MODULE.digest(path) != before
