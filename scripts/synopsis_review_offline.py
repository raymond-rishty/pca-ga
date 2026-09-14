"""Export the synopsis reviewer as a self-contained file or import its decisions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import synopsis_review_server as review


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "index/synopsis_workflow/candidate-review/offline-review.html"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_report(output: Path) -> None:
    store = review.ReviewStore(
        ROOT, review.DEFAULT_REGISTRY, review.DEFAULT_DECISIONS,
        review.DEFAULT_PRIORITIES)
    index = store.index()
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_sha256": digest(review.DEFAULT_REGISTRY),
        "index": index,
        "cases": {item["case_id"]: store.case(item["case_id"])
                  for item in index["items"]},
        "baseline_decisions": store.decisions().get("cases", {}),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("</", "<\\/")
    template = review.APP.read_text(encoding="utf-8")
    marker = "<!-- OFFLINE_DATA -->"
    if marker not in template:
        raise ValueError("Offline-data marker is missing from reviewer template")
    html = template.replace(
        marker, f"<script>window.__SYNOPSIS_REVIEW_OFFLINE__={encoded};</script>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(json.dumps({
        "output": output.relative_to(ROOT).as_posix(),
        "cases": len(index["items"]),
        "bytes": output.stat().st_size,
        "registry_sha256": payload["registry_sha256"],
    }, indent=2))


def import_decisions(source: Path) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported offline decision schema")
    if payload.get("publication_authorized") is not False:
        raise ValueError("Offline decisions must not authorize publication")
    expected = digest(review.DEFAULT_REGISTRY)
    if payload.get("registry_sha256") != expected:
        raise ValueError("Candidate registry changed after offline report export")
    store = review.ReviewStore(
        ROOT, review.DEFAULT_REGISTRY, review.DEFAULT_DECISIONS,
        review.DEFAULT_PRIORITIES)
    changed = 0
    for case_id, record in (payload.get("cases") or {}).items():
        body = {
            "decision": record.get("decision"),
            "reviewer": record.get("reviewer", ""),
            "notes": record.get("notes", ""),
        }
        if "acceptability_pass" in record:
            body["acceptability_pass"] = record["acceptability_pass"]
        if record.get("decision") == "corrected":
            corrected = record.get("corrected") or {}
            body.update(corrected)
        store.save_decision(case_id, body)
        changed += 1
    print(json.dumps({"imported": changed, "source": str(source)}, indent=2))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export_parser = sub.add_parser("export")
    export_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    import_parser = sub.add_parser("import")
    import_parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    if args.command == "export":
        export_report(args.output.resolve())
    else:
        import_decisions(args.source.resolve())


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
