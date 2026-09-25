#!/usr/bin/env python3
"""Write a reproducible audit of authority-index relationships and coverage."""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any

from provision_catalogue import load_catalogue


def _count_dimension(rows: list[dict[str, Any]], singular: str, plural: str | None = None) -> dict[str, int]:
    counts: collections.Counter[str] = collections.Counter()
    for row in rows:
        values = row.get(plural) if plural else None
        if not isinstance(values, list):
            values = [row.get(singular)]
        for value in set(str(item) for item in values if item):
            counts[value] += 1
    return dict(sorted(counts.items()))


def build_audit(catalogue: dict[str, Any], advisory_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    relationships = [
        relation
        for provision in catalogue.get("provisions", [])
        for relation in provision.get("relationships", [])
    ]
    unmatched = catalogue.get("unmatched_relationships", [])
    occurrences = [occurrence for relation in relationships
                   for occurrence in relation.get("occurrences", [])]
    type_counts = collections.Counter(str(row.get("type") or "unknown") for row in relationships)
    primary_counts = collections.Counter(str(row.get("type") or "unknown") for row in relationships
                                         if row.get("reader_scope") == "primary")
    assessed = [row for row in relationships if row.get("relevance_assessment")]
    machine_roles: dict[str, dict[str, int]] = {}
    for relation in assessed:
        record_type = str(relation.get("type") or "unknown")
        role = str((relation.get("relevance_assessment") or {}).get("role") or "unclassified")
        machine_roles.setdefault(record_type, {})[role] = machine_roles.setdefault(record_type, {}).get(role, 0) + 1
    known_relationship_ids = {str(row.get("id") or "") for row in relationships}
    stored_assessments: collections.Counter[tuple[str, str, str]] = collections.Counter()
    stored_unrelated_by_type: collections.Counter[str] = collections.Counter()
    current_fingerprint = str(catalogue.get("input_fingerprint") or "")
    for row in advisory_rows or []:
        record_type = str(row.get("record_type") or "unknown")
        role = str(row.get("role") or "unclassified")
        if row.get("catalogue_input_fingerprint") != current_fingerprint:
            status = "stale"
        elif str(row.get("relationship_id") or "") not in known_relationship_ids:
            status = "unmatched"
        else:
            status = "current"
        stored_assessments[(record_type, role, status)] += 1
        if role == "unrelated_or_mislinked":
            stored_unrelated_by_type[record_type] += 1

    acree_rows = [
        {"provision": provision.get("abbr", "") + " " + provision.get("ref", ""),
         "record_id": relation.get("record_id"), "title": relation.get("title")}
        for provision in catalogue.get("provisions", [])
        for relation in provision.get("relationships", [])
        if relation.get("type") == "Judicial case"
        and any(re.fullmatch(r"2021-0?7", str(number)) for number in
                (relation.get("metadata", {}).get("case_numbers") or []))
        and "acree" in str(relation.get("title") or "").casefold()
    ]
    recommendation_status = collections.Counter(
        str((provision.get("coverage", {}).get("recommendations") or {}).get("status") or "unknown")
        for provision in catalogue.get("provisions", [])
    )
    return {
        "schema_version": 1,
        "catalogue_input_fingerprint": catalogue.get("input_fingerprint"),
        "provision_count": len(catalogue.get("provisions", [])),
        "relationship_count": len(relationships),
        "occurrence_count": len(occurrences),
        "unmatched_relationship_count": len(unmatched),
        "unmatched_relationships": [
            {field: row.get(field) for field in (
                "provision", "record_type", "record_id", "title", "year", "disposition",
                "url", "evidence_basis", "relationship_kind", "match_confidence", "reader_scope",
            )}
            for row in unmatched
        ],
        "relationships_by_type": dict(sorted(type_counts.items())),
        "reader_primary_by_type": dict(sorted(primary_counts.items())),
        "reader_excluded_relationships": sum(1 for row in relationships
                                              if row.get("reader_scope") != "primary"),
        "relationship_dimensions": {
            "relationship_kind": _count_dimension(relationships, "relationship_kind", "relationship_kinds"),
            "evidence_basis": _count_dimension(relationships, "evidence_basis", "evidence_bases"),
            "match_confidence": _count_dimension(relationships, "match_confidence"),
            "reader_scope": _count_dimension(relationships, "reader_scope"),
            "match_method": _count_dimension(relationships, "match_method", "match_methods"),
        },
        "occurrence_dimensions": {
            "relationship_kind": _count_dimension(occurrences, "relationship_kind"),
            "evidence_basis": _count_dimension(occurrences, "evidence_basis"),
            "match_confidence": _count_dimension(occurrences, "match_confidence"),
            "reader_scope": _count_dimension(occurrences, "reader_scope"),
            "match_method": _count_dimension(occurrences, "match_method"),
        },
        "unmatched_by_type": dict(sorted(collections.Counter(
            str(row.get("record_type") or "unknown") for row in unmatched).items())),
        "machine_relevance_roles": machine_roles,
        "machine_relevance_assessment_summary": catalogue.get("assessment_summary", {}),
        "stored_advisory_assessments": [
            {"record_type": record_type, "role": role, "status": status, "count": count}
            for (record_type, role, status), count in sorted(stored_assessments.items())
        ],
        "stored_unrelated_or_mislinked_by_type": dict(sorted(stored_unrelated_by_type.items())),
        "recommendation_coverage_status": dict(sorted(recommendation_status.items())),
        "known_case_spot_check": {
            "case": "2021-07 RE J. Lance Acree v. Tennessee Valley Presbytery",
            "indexed_relationships": acree_rows,
            "expected_provision": "BCO 43-1",
            "passes": len(acree_rows) == 1 and acree_rows[0]["provision"] == "BCO 43-1",
        },
        "limitations": [
            "Machine relevance assessments are model-generated advisory classifications, not human confirmation.",
            "Recommendation and study relationships are not comprehensively indexed by provision; per-provision coverage remains incomplete.",
            "Legacy authority_weight is a display/grouping field and does not state the legal force of a record.",
            "Match confidence describes extraction or tagging confidence, not legal relevance or authority.",
        ],
    }


def _markdown_table(title: str, counts: dict[str, int]) -> list[str]:
    lines = [f"### {title}", "", "| Value | Count |", "|-------|------:|"]
    lines.extend(f"| `{value}` | {count} |" for value, count in counts.items())
    if not counts:
        lines.append("| — | 0 |")
    lines.append("")
    return lines


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Authority index audit", "",
        f"Catalogue input fingerprint: `{audit['catalogue_input_fingerprint']}`.", "",
        f"The catalogue contains {audit['provision_count']} provisions, "
        f"{audit['relationship_count']} relationships, {audit['occurrence_count']} evidence occurrences, "
        f"and {audit['unmatched_relationship_count']} unmatched source references.", "",
        "Relationship kinds describe why a record is linked. Evidence basis describes the source of that link. "
        "Match confidence describes extraction confidence. Reader scope controls the Constitution Reader feed. "
        "These fields do not describe legal force.", "",
        "The Reader feed includes only rows scoped `primary`. CCB advice, RPR exceptions, body mentions, "
        "non-adopted overtures, and other candidate/contextual records remain available in the GA catalogue "
        "but are omitted from that feed.", "",
        "## Relationships by record type", "",
        "| Record type | Relationships | Reader primary |", "|-------------|--------------:|---------------:|",
    ]
    types = sorted(set(audit["relationships_by_type"]) | set(audit["reader_primary_by_type"]))
    for record_type in types:
        lines.append(f"| {record_type} | {audit['relationships_by_type'].get(record_type, 0)} | {audit['reader_primary_by_type'].get(record_type, 0)} |")
    lines.append("")
    for dimension in ("relationship_kind", "evidence_basis", "match_confidence", "reader_scope", "match_method"):
        lines.extend(_markdown_table(f"Relationships by {dimension.replace('_', ' ')}",
                                     audit["relationship_dimensions"].get(dimension, {})))
    for dimension in ("relationship_kind", "evidence_basis", "match_confidence", "reader_scope"):
        lines.extend(_markdown_table(f"Evidence occurrences by {dimension.replace('_', ' ')}",
                                     audit["occurrence_dimensions"].get(dimension, {})))
    lines.extend(["## Unmatched source references", "", "| Record type | Count |", "|-------------|------:|"])
    for record_type, count in audit["unmatched_by_type"].items():
        lines.append(f"| {record_type} | {count} |")
    if not audit["unmatched_by_type"]:
        lines.append("| — | 0 |")
    if audit["unmatched_relationships"]:
        lines.extend(["", "| Provision | Record type | Record ID | Evidence | Confidence | Scope | Source |",
                      "|-----------|-------------|-----------|----------|------------|-------|--------|"])
        for row in audit["unmatched_relationships"]:
            target = _audit_source_target(row.get("url"))
            source = f"[{row['title']}]({target})" if target else row.get("title") or "—"
            lines.append(f"| {row['provision']} | {row['record_type']} | `{row['record_id']}` | "
                         f"`{row['evidence_basis']}` | `{row['match_confidence']}` | "
                         f"`{row['reader_scope']}` | {source} |")
    lines.extend(["", "## Model-generated relevance assessments", "",
                  "These counts describe the existing automated advisory assessments. They are not human-reviewed findings.", ""])
    lines.extend(["| Record type | Role | Count |", "|-------------|------|------:|"])
    for record_type, roles in sorted(audit["machine_relevance_roles"].items()):
        for role, count in sorted(roles.items()):
            lines.append(f"| {record_type} | `{role}` | {count} |")
    if not audit["machine_relevance_roles"]:
        lines.append("| — | — | 0 |")
    stored = audit["stored_advisory_assessments"]
    if stored:
        lines.extend(["", "Stored advisory rows by type, role, and fingerprint status:", "",
                      "| Record type | Role | Fingerprint status | Count |",
                      "|-------------|------|--------------------|------:|"])
        for row in stored:
            lines.append(f"| {row['record_type']} | `{row['role']}` | `{row['status']}` | {row['count']} |")
        lines.extend(["", "Stored `unrelated_or_mislinked` advisory labels by record type:", ""])
        for record_type, count in audit["stored_unrelated_or_mislinked_by_type"].items():
            lines.append(f"- {record_type}: {count}")
    summary = audit.get("machine_relevance_assessment_summary") or {}
    lines.extend(["", f"Assessment status: `{summary.get('status', 'missing')}`; "
                  f"applied {summary.get('applied', 0)}, stale {summary.get('stale', 0)}, "
                  f"unassessed {summary.get('unassessed', audit['relationship_count'])}.", "",
                  "## Coverage and spot checks", "",
                  "| Recommendation coverage status | Provisions |", "|-------------------------------|-----------:|"])
    for status, count in audit["recommendation_coverage_status"].items():
        lines.append(f"| `{status}` | {count} |")
    spot = audit["known_case_spot_check"]
    lines.extend(["", f"Acree check: {'PASS' if spot['passes'] else 'FAIL'} — expected only `{spot['expected_provision']}`; "
                  f"indexed `{', '.join(row['provision'] for row in spot['indexed_relationships']) or 'none'}`.", "",
                  "## Limitations", ""])
    lines.extend(f"- {item}" for item in audit["limitations"])
    return "\n".join(lines) + "\n"


def _audit_source_target(url: str | None) -> str | None:
    if url and not url.startswith(("/", "http://", "https://", "mailto:")):
        return f"../{url}"
    return url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path.cwd(), type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    catalogue = load_catalogue(root / "index" / "provision_catalogue.json")
    advisory_path = root / "index" / "provision_link_adjudications.jsonl"
    advisory_rows = ([json.loads(line) for line in advisory_path.read_text(encoding="utf-8").splitlines()
                      if line.strip()] if advisory_path.is_file() else [])
    audit = build_audit(catalogue, advisory_rows)
    output_json = root / "index" / "authority_index_audit.json"
    output_md = root / "index" / "AUTHORITY-INDEX-AUDIT.md"
    output_json.write_text(json.dumps(audit, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown(audit), encoding="utf-8")
    print(f"Wrote {output_json} and {output_md}")
    if not audit["known_case_spot_check"]["passes"]:
        raise SystemExit("Acree spot check failed: expected one BCO 43-1 relationship")


if __name__ == "__main__":
    main()
