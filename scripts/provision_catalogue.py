#!/usr/bin/env python3
"""Build and read the shared generated provision catalogue.

The catalogue is the single joined read model used by the human, search, and API
projections. Curated corpus indexes remain the inputs that provide its evidence.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


CATALOGUE_SCHEMA_VERSION = 1
LOW_CONFIDENCE_REVIEW_FLOOR = 0.5
DISCUSSION_LABELS = {
    "Judicial case": {
        "applied_by_majority": "Applied in the majority opinion",
    },
    "RPR exception": {
        "exception_target": "Exception addresses this provision",
        "substantive_treatment": "Discusses this provision",
    },
    "Overture": {
        "amendment_target": "Proposes a change",
    },
    "CCB advice": {
        "direct_interpretation": "Discusses or applies this provision",
    },
    "Constitutional inquiry": {
        "direct_interpretation": "Discusses or applies this provision",
    },
}
CITATION_LABELS = {
    "Judicial case": {
        "material_to_majority_issue": "Relevant to a majority issue",
    },
    "Overture": {
        "materially_affected": "Proposal affects this provision",
    },
    "CCB advice": {
        "material_to_answer": "Relevant to the response",
    },
    "Constitutional inquiry": {
        "material_to_answer": "Relevant to the response",
    },
}
PRESENTATION_GROUPS = {
    "discusses": "Discusses this provision",
    "cites": "Cites this provision",
    "other_case_discussion": "Other discussion in the case",
    "other_mentions": "Other mentions",
    "review": "References to review",
}
INPUTS = (
    "scripts/provision_catalogue.py",
    "scripts/43_authority_index.py",
    "scripts/44_case_provision_index.py",
    "scripts/overture_catalogue.py",
    "scripts/provision_references.py",
    "index/cases.jsonl",
    "index/case_pages_map.json",
    "index/judicial_cases.jsonl",
    "index/case_provision_index.json",
    "index/inquiries_search.json",
    "index/rpr_search.json",
    "index/overture_titles.jsonl",
    "index/overture_bodies.jsonl",
    "index/overture_dispositions.jsonl",
    "index/OVERTURES.md",
    "index/bco_changes.jsonl",
    "index/bco_renumberings.jsonl",
)


def reference_presentation(relationship: dict[str, Any]) -> dict[str, str | None]:
    """Return the reader-facing grouping without exposing assessment internals."""
    assessment = relationship.get("relevance_assessment") or {}
    if not assessment:
        return {"group": "review", "label": None}

    role = str(assessment.get("role") or "")
    try:
        confidence = float(assessment.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    if (role in {"insufficient_source", "unrelated_or_mislinked"}
            or confidence < LOW_CONFIDENCE_REVIEW_FLOOR):
        return {"group": "review", "label": None}
    if role == "substantive_nonmajority_only":
        return {
            "group": "other_case_discussion",
            "label": PRESENTATION_GROUPS["other_case_discussion"],
        }
    if role == "incidental_reference":
        return {"group": "other_mentions", "label": "Brief mention"}

    record_type = str(relationship.get("type") or "")
    if label := DISCUSSION_LABELS.get(record_type, {}).get(role):
        return {"group": "discusses", "label": label}
    if label := CITATION_LABELS.get(record_type, {}).get(role):
        return {"group": "cites", "label": label}
    return {"group": "review", "label": None}


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_catalogue(path: Path) -> dict[str, Any]:
    catalogue = read_json(path, None)
    if not isinstance(catalogue, dict) or catalogue.get("schema_version") != CATALOGUE_SCHEMA_VERSION:
        raise ValueError(f"Missing or unsupported provision catalogue: {path}")
    return catalogue


def _load_module(path: Path, name: str, root: Path | None = None):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    saved_argv = sys.argv[:]
    try:
        sys.argv = [str(path)] + ([str(root)] if root else [])
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved_argv
    if root is not None:
        module.ROOT = str(root)
        module.IDX = str(root / "index")
        module.CASES_DIR = str(root / "cases")
        module.AUTH_DIR = str(root / "authorities")
    return module


def _authority_rows(root: Path, canonical_id=None) -> list[dict[str, Any]]:
    """Collect source rows from curated catalogues and audited source indexes."""
    module = _load_module(root / "scripts" / "43_authority_index.py", "pca_authority_sources", root)
    rows: list[dict[str, Any]] = []
    for builder in (module.build_case_rows, module.build_inquiry_rows,
                    module.build_rpr_rows, module.build_overture_rows):
        rows.extend(builder())

    if canonical_id:
        # RPR search rows contain parsed BCO/RAO tags, but Westminster citations
        # and preliminary principles also appear in the record text. Reuse the
        # audited citation parser for those references; recover other BCO cites
        # only from explicit Exception lines to avoid treating responses as exceptions.
        parser = _load_module(root / "scripts" / "44_case_provision_index.py",
                              "pca_provision_reference_parser", root)
        for item in read_json(root / "index" / "rpr_search.json", []):
            url = str(item.get("url") or "")
            source_path = root / Path(urlsplit(url).path).with_suffix(".md")
            if not source_path.is_file():
                continue
            title = f"{item.get('presbytery', '')}: {item.get('title', '')}".strip(": ")
            for evidence in _rpr_direct_evidence(parser, source_path, canonical_id):
                rows.append({
                    "provision": evidence["provision"],
                    "type": "RPR exception",
                    "authority_weight": "low-but-important",
                    "title": title,
                    "year": item.get("year"),
                    "disposition": item.get("disposition", ""),
                    "url": url,
                    "snippet": evidence["snippet"],
                    "evidence_line": evidence["line"],
                    "evidence_source": evidence["source"],
                    "evidence_basis": "direct_text",
                    "relationship_kind": ("exception_target" if evidence["source"] == "rpr_exception_header"
                                          else "body_mention"),
                    "match_method": f"rpr_markdown_line:{evidence['line']}",
                    "match_confidence": "high",
                    "reader_scope": ("contextual" if evidence["source"] == "rpr_exception_header"
                                     else "candidate"),
                })

    for item in read_json(root / "index" / "inquiries_search.json", []):
        if item.get("type") != "ccb-advice":
            continue
        for provision in item.get("provisions") or []:
            rows.append({
                "provision": provision,
                "type": "CCB advice",
                "authority_weight": "medium",
                "title": item.get("title", ""),
                "year": item.get("year"),
                "disposition": item.get("disposition", ""),
                "url": item.get("url", ""),
                "snippet": "",
                "summary": item.get("sub", ""),
                "evidence_basis": "structured_provision_tag",
                "relationship_kind": "structured_provision_tag",
                "match_method": "index/inquiries_search.json:provisions",
                "match_confidence": "medium",
                "reader_scope": "contextual",
            })
    return rows


_RPR_EXCEPTION_HEADER = re.compile(
    r"^\s*(?:>\s*)?(?:[-*]\s*)?(?:\*\*|__)?Exception\s*:", re.I
)


def _rpr_direct_evidence(parser, source_path: Path, canonical_id) -> list[dict[str, Any]]:
    """Return PP/Westminster citations from RPR text and other cites on exception headers."""
    raw_lines = source_path.read_text(encoding="utf-8").splitlines()
    body_lines, skipped_lines = parser.markdown_body_lines("\n".join(raw_lines))
    exception_lines = {
        line_number
        for line_number, line in enumerate(body_lines, start=skipped_lines + 1)
        if _RPR_EXCEPTION_HEADER.match(line)
    }

    evidence: list[dict[str, Any]] = []
    for provision, hits in parser.text_hits(source_path).items():
        identifier = canonical_id(provision) or ""
        is_preliminary_principle = identifier.startswith("bco:pp-")
        is_westminster = identifier.startswith(("wcf:", "wlc:", "wsc:"))
        for hit in hits:
            is_exception_header = hit.get("line") in exception_lines
            if not is_preliminary_principle and not is_westminster and not is_exception_header:
                continue
            evidence.append({
                "provision": provision,
                "line": hit.get("line"),
                "snippet": hit.get("snippet", ""),
                "source": ("rpr_exception_header" if is_exception_header
                           else "rpr_markdown_text"),
            })
    return evidence


def _input_fingerprint(root: Path, reader_dir: Path, reader_meta: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
    paths = [root / relative for relative in INPUTS]
    paths.extend(sorted((root / "cases").glob("*.md")))
    paths.extend(sorted((root / "inquiries").glob("*.md")))
    paths.extend(sorted((root / "rpr" / "exc").glob("*.md")))
    inputs = []
    for path in sorted(set(paths), key=lambda item: item.as_posix()):
        if path.is_file():
            inputs.append({
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    inputs.extend({"path": f"_constitution/content/{name}", "sha256": digest}
                  for name, digest in sorted(reader_meta.items()))
    reader_revision = _reader_revision(reader_dir)
    payload = {"reader_revision": reader_revision, "inputs": inputs}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                             separators=(",", ":")).encode("utf-8")).hexdigest()
    return fingerprint, inputs


def _reader_revision(reader_dir: Path) -> str:
    import subprocess
    try:
        result = subprocess.run(["git", "-C", str(reader_dir), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _record_kind(record_type: str) -> str:
    return {
        "Judicial case": "case",
        "Constitutional inquiry": "inquiry",
        "CCB advice": "ccb_advice",
        "Overture": "overture",
        "RPR exception": "rpr_exception",
        "Study or recommendation": "study_recommendation",
    }.get(record_type, re.sub(r"[^a-z0-9]+", "_", record_type.lower()).strip("_"))


def _record_id(row: dict[str, Any], record_kind: str) -> str:
    explicit = str(row.get("record_id") or "").strip()
    if explicit:
        return explicit
    path = urlsplit(str(row.get("url") or "")).path.strip("./")
    if not path:
        path = str(row.get("title") or "untitled").strip().casefold()
    return f"{record_kind}:{path}"


def _occurrence_id(relationship_id: str, occurrence: dict[str, Any]) -> str:
    marker = json.dumps(occurrence, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(marker.encode("utf-8")).hexdigest()[:12]
    return f"{relationship_id}:occ-{digest}"


def _case_evidence_by_key(root: Path, canonical_id) -> dict[tuple[str, str], dict[str, Any]]:
    evidence: dict[tuple[str, str], dict[str, Any]] = {}
    for row in read_json(root / "index" / "case_provision_index.json", []):
        provision_id = canonical_id(row.get("provision", ""))
        url = str(row.get("url") or "")
        if provision_id and url:
            evidence[(provision_id, url)] = row
    return evidence


def _relation_occurrences(row: dict[str, Any], evidence_row: dict[str, Any] | None,
                          evidence_basis: str, relationship_id: str) -> list[dict[str, Any]]:
    url = str(row.get("url") or "")
    source_parts = urlsplit(url)
    evidence_items = (evidence_row or {}).get("evidence") or []
    if not evidence_items and row.get("evidence_line") and row.get("snippet"):
        evidence_items = [{"line": row["evidence_line"], "snippet": row["snippet"]}]
    occurrences: list[dict[str, Any]] = []
    if evidence_items and evidence_basis == "direct_text":
        for evidence in evidence_items:
            occurrences.append({
                "url": url,
                "locator": {"fragment": source_parts.fragment or None, "line": evidence.get("line")},
                "excerpt": evidence.get("snippet") or "",
                "sources": ((evidence_row or {}).get("sources") or
                            (row.get("evidence_sources") or
                             ([row["evidence_source"]] if row.get("evidence_source") else []))),
                "evidence_basis": evidence_basis,
                "relationship_kind": row.get("relationship_kind") or "explicit_citation",
                "match_method": row.get("match_method") or evidence_basis,
                "match_confidence": row.get("match_confidence") or "high",
                "reader_scope": row.get("reader_scope") or "candidate",
            })
    if not occurrences:
        locator: dict[str, Any] = {}
        if source_parts.fragment:
            locator["fragment"] = source_parts.fragment
            page = re.search(r"-p(\d+)$", source_parts.fragment)
            if page:
                locator["page"] = int(page.group(1))
        if row.get("occurrence_page"):
            locator["page"] = row["occurrence_page"]
        occurrences.append({
            "url": url,
            "locator": locator,
            "excerpt": ("" if row.get("type") == "Judicial case" and evidence_basis != "direct_text"
                        else row.get("snippet") or ""),
            "sources": ((evidence_row or {}).get("sources") or row.get("evidence_sources") or
                        ([row["evidence_source"]] if row.get("evidence_source") else
                         ([row.get("match_method")] if row.get("match_method") else []))),
            "evidence_basis": evidence_basis,
            "relationship_kind": row.get("relationship_kind") or "structured_provision_tag",
            "match_method": row.get("match_method") or evidence_basis,
            "match_confidence": row.get("match_confidence") or "medium",
            "reader_scope": row.get("reader_scope") or "candidate",
        })
    unique: dict[str, dict[str, Any]] = {}
    for occurrence in occurrences:
        key = json.dumps(occurrence, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        unique.setdefault(key, occurrence)
    result = []
    for occurrence in unique.values():
        result.append({"id": _occurrence_id(relationship_id, occurrence), **occurrence})
    return result


def _evidence_basis(record_type: str, row: dict[str, Any], evidence_row: dict[str, Any] | None) -> str:
    if row.get("evidence_basis"):
        return str(row["evidence_basis"])
    if record_type == "Overture":
        if row.get("evidence_source") == "overture_body_text":
            return "direct_text"
        return "title_subject_reference"
    if record_type == "Judicial case":
        if ((evidence_row or {}).get("evidence") or []):
            return "direct_text"
        return "structured_case_metadata"
    if record_type == "RPR exception" and row.get("evidence_line"):
        return "direct_text"
    if record_type in {"Constitutional inquiry", "CCB advice", "RPR exception"}:
        return "structured_provision_tag"
    return "indexed_reference"


def _strip_fragment(url: str) -> str:
    parts = urlsplit(url)
    return parts._replace(fragment="").geturl()


def _apply_link_assessments(root: Path, source_fingerprint: str,
                            units: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Attach current advisory assessments without replacing editorial status."""
    path = root / "index" / "provision_link_adjudications.jsonl"
    if not path.is_file():
        return "", {"status": "missing", "file": "index/provision_link_adjudications.jsonl",
                    "total": 0, "applied": 0, "stale": 0, "unmatched": 0}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relationships = {
        relation["id"]: relation
        for unit in units for relation in unit.get("relationships") or []
    }
    seen: set[str] = set()
    applied = stale = unmatched = 0
    for row in read_jsonl(path):
        relationship_id = str(row.get("relationship_id") or "")
        if not relationship_id:
            continue
        if relationship_id in seen:
            raise ValueError(f"Duplicate provision-link assessment: {relationship_id}")
        seen.add(relationship_id)
        if row.get("catalogue_input_fingerprint") != source_fingerprint:
            stale += 1
            continue
        relation = relationships.get(relationship_id)
        if relation is None:
            unmatched += 1
            continue
        relation["relevance_assessment"] = {
            "role": row.get("role"),
            "confidence": row.get("confidence"),
            "probabilities": row.get("probabilities") or {},
            "model": row.get("model"),
            "rubric_version": row.get("rubric_version"),
            "source_scope": row.get("source_scope"),
            "source_sha256": row.get("source_sha256"),
            "source_input_sha256": row.get("source_input_sha256") or "",
            "evidence_basis": row.get("evidence_basis") or relation.get("evidence_basis", ""),
            "source_catalogue_fingerprint": row.get("catalogue_input_fingerprint"),
            "adjudicated_at_utc": row.get("adjudicated_at_utc"),
        }
        applied += 1
    expected = len(relationships)
    if stale:
        status = "stale"
    elif applied == expected and not unmatched:
        status = "current"
    else:
        status = "partial"
    return digest, {"status": status, "file": "index/provision_link_adjudications.jsonl",
                    "total": len(seen), "expected": expected, "applied": applied,
                    "stale": stale, "unmatched": unmatched,
                    "unassessed": max(0, expected - applied)}


def build_catalogue(root: Path, reader_dir: Path) -> dict[str, Any]:
    """Join current provision text and curated references once for all projections."""
    root = root.resolve()
    reader_dir = reader_dir.resolve()
    research = _load_module(root / "scripts" / "46_provision_research.py", "pca_provision_research")
    units, reader_meta = research.load_units(reader_dir)
    unit_by_id = {unit["id"]: unit for unit in units}
    source_rows = _authority_rows(root, research.canonical_id)
    evidence_by_key = _case_evidence_by_key(root, research.canonical_id)

    relationships: dict[tuple[str, str], dict[str, Any]] = {}
    unmatched: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in source_rows:
        provision_id = research.canonical_id(row.get("provision", ""))
        if not provision_id:
            continue
        record_type = str(row.get("type") or "")
        kind = _record_kind(record_type)
        record_id = _record_id(row, kind)
        evidence_row = evidence_by_key.get((provision_id, str(row.get("url") or ""))) if kind == "case" else None
        basis = _evidence_basis(record_type, row, evidence_row)
        if provision_id not in unit_by_id:
            key = (str(row.get("provision") or ""), record_type, record_id)
            unmatched.setdefault(key, {
                "provision": str(row.get("provision") or ""),
                "record_type": record_type,
                "record_id": record_id,
                "title": str(row.get("title") or ""),
                "year": row.get("year"),
                "disposition": row.get("disposition") or "",
                "url": str(row.get("url") or ""),
                "authority_weight": row.get("authority_weight") or "",
                "evidence_basis": basis,
                "relationship_kind": row.get("relationship_kind") or "unclassified_reference",
                "match_confidence": row.get("match_confidence") or "unassessed",
                "reader_scope": row.get("reader_scope") or "candidate",
                "relevance_status": "unreviewed",
            })
            continue

        relationship_id = f"{provision_id}--{record_id}"
        key = (provision_id, record_id)
        relationship = relationships.get(key)
        if relationship is None:
            relationship = {
                "id": relationship_id,
                "record_id": record_id,
                "type": record_type,
                "title": str(row.get("title") or ""),
                "year": row.get("year"),
                "disposition": row.get("disposition") or "",
                "authority_weight": row.get("authority_weight") or "",
                "record_url": _strip_fragment(str(row.get("url") or "")),
                "evidence_basis": basis,
                "evidence_bases": [],
                "relationship_kind": row.get("relationship_kind") or "unclassified_reference",
                "relationship_kinds": [],
                "match_confidence": row.get("match_confidence") or "unassessed",
                "match_methods": [],
                "reader_scope": row.get("reader_scope") or "candidate",
                "relevance_status": "unreviewed",
                "occurrences": [],
                "metadata": {},
            }
            relationships[key] = relationship
        if not relationship.get("year") and row.get("year"):
            relationship["year"] = row["year"]
        if not relationship.get("disposition") and row.get("disposition"):
            relationship["disposition"] = row["disposition"]
        for field in ("topics", "standard_of_review", "review_standards", "source", "case_numbers", "summary"):
            value = row.get(field)
            if value not in (None, [], ""):
                relationship["metadata"][field] = value
        if evidence_row:
            for field in ("case_numbers", "body", "synopsis"):
                value = evidence_row.get(field)
                if value not in (None, [], ""):
                    relationship["metadata"].setdefault(field, value)
        relationship["occurrences"].extend(
            _relation_occurrences(row, evidence_row, basis, relationship_id)
        )
        relationship["evidence_bases"].append(basis)
        relationship["relationship_kinds"].append(
            row.get("relationship_kind") or "unclassified_reference"
        )
        relationship["match_methods"].append(row.get("match_method") or basis)
        confidence_rank = {"unassessed": 0, "low": 1, "medium": 2, "high": 3}
        if confidence_rank.get(str(row.get("match_confidence") or "unassessed"), 0) > confidence_rank.get(
                str(relationship.get("match_confidence") or "unassessed"), 0):
            relationship["match_confidence"] = row.get("match_confidence")
        scope_rank = {"candidate": 1, "contextual": 2, "primary": 3}
        if scope_rank.get(str(row.get("reader_scope") or "candidate"), 0) > scope_rank.get(
                str(relationship.get("reader_scope") or "candidate"), 0):
            relationship["reader_scope"] = row.get("reader_scope")

    for unit in units:
        child_units = unit.get("children") or []
        unit["children"] = [child["id"] for child in child_units]
        unit.pop("groups", None)
        unit["relationships"] = []
        unit["history"] = []
        unit["coverage"] = {
            "relationships": "indexed_records",
            "recommendations": {
                "status": "incomplete",
                "note": "Recommendation and study papers are not comprehensively indexed by provision.",
            },
            "history": "partial" if unit["book"] == "bco" else "not_available",
        }
        for child_id in unit["children"]:
            if child_id in unit_by_id:
                unit_by_id[child_id]["parent_id"] = unit["id"]

    for (provision_id, _), relationship in relationships.items():
        relationship["evidence_bases"] = sorted(set(relationship["evidence_bases"]))
        relationship["relationship_kinds"] = sorted(set(relationship["relationship_kinds"]))
        relationship["match_methods"] = sorted(set(relationship["match_methods"]))
        if len(relationship["evidence_bases"]) != 1:
            relationship["evidence_basis"] = "multiple"
        if len(relationship["relationship_kinds"]) != 1:
            relationship["relationship_kind"] = "multiple"
        else:
            relationship["relationship_kind"] = relationship["relationship_kinds"][0]
        occurrences = {occurrence["id"]: occurrence for occurrence in relationship["occurrences"]}
        relationship["occurrences"] = sorted(occurrences.values(), key=lambda item: (
            str(item.get("url") or ""),
            int((item.get("locator") or {}).get("line") or 0),
            str(item.get("id") or ""),
        ))
        unit_by_id[provision_id]["relationships"].append(relationship)

    research._history_for_units(root, unit_by_id)
    for unit in units:
        unit["relationships"].sort(key=lambda item: (
            item["type"], -(int(item.get("year") or 0)), item["title"].casefold(), item["record_id"]
        ))
        for history in unit["history"]:
            key = f"{history.get('kind')}:{history.get('ga')}:{history.get('year')}:{history.get('note')}"
            history["id"] = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]

    fingerprint, inputs = _input_fingerprint(root, reader_dir, reader_meta)
    assessment_fingerprint, assessment_summary = _apply_link_assessments(root, fingerprint, units)
    return {
        "schema_version": CATALOGUE_SCHEMA_VERSION,
        "catalogue_version": 1,
        "source": {
            "name": "PCA Constitution Reader",
            "revision": _reader_revision(reader_dir),
            "edition": "Current Reader text",
            "files": reader_meta,
        },
        "input_fingerprint": fingerprint,
        "input_files": inputs,
        "assessment_fingerprint": assessment_fingerprint,
        "assessment_summary": assessment_summary,
        "relationship_count": sum(len(unit["relationships"]) for unit in units),
        "unmatched_relationships": sorted(unmatched.values(), key=lambda item: (
            item["provision"], item["record_type"], item["record_id"]
        )),
        "provisions": units,
    }


def write_catalogue(path: Path, catalogue: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def provision_search_rows(catalogue: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for unit in catalogue["provisions"]:
        canonical = f"{unit['abbr']} {unit['ref']}"
        rows.append({
            "type": "Supplementary rule" if unit["supplementary"] else "Constitutional provision",
            "title": f"{canonical} · {unit['title']}",
            "sub": unit["book_label"],
            "identifier": canonical,
            "identifiers": [canonical],
            "topics": [unit["book_name"], unit["title"]],
            "provisions": [canonical],
            "provision_id": unit["id"],
            "year": None,
            "disposition": "",
            "url": f"provisions/{unit['book']}/{unit['route_ref']}/",
        })
    return rows


def authority_projection(catalogue: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for unit in catalogue["provisions"]:
        provision = f"{unit['abbr']} {unit['ref']}"
        for relationship in unit["relationships"]:
            occurrence = relationship["occurrences"][0] if relationship["occurrences"] else {}
            rows.append({
                "provision": provision,
                "type": relationship["type"],
                "authority_weight": relationship.get("authority_weight", ""),
                "title": relationship["title"],
                "year": relationship.get("year"),
                "disposition": relationship.get("disposition", ""),
                "url": occurrence.get("url") or relationship.get("record_url", ""),
                "snippet": occurrence.get("excerpt", ""),
                "record_id": relationship["record_id"],
                "relationship_id": relationship["id"],
                "evidence_basis": relationship["evidence_basis"],
                "evidence_bases": relationship.get("evidence_bases", []),
                "relationship_kind": relationship.get("relationship_kind", ""),
                "relationship_kinds": relationship.get("relationship_kinds", []),
                "match_confidence": relationship.get("match_confidence", "unassessed"),
                "match_methods": relationship.get("match_methods", []),
                "reader_scope": relationship.get("reader_scope", "candidate"),
                "relevance_status": relationship["relevance_status"],
                "relevance_assessment": relationship.get("relevance_assessment"),
                "occurrences": relationship["occurrences"],
                **relationship.get("metadata", {}),
            })
    for row in catalogue.get("unmatched_relationships", []):
        rows.append({
            **row,
            "type": row["record_type"],
            "snippet": "",
            "relationship_id": f"unmatched:{row['record_id']}:{row['provision']}",
        })
    return rows
