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
INPUTS = (
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
    """Collect current source rows in memory; never read authority_index.json."""
    module = _load_module(root / "scripts" / "43_authority_index.py", "pca_authority_sources", root)
    rows: list[dict[str, Any]] = []
    for builder in (module.build_case_rows, module.build_inquiry_rows,
                    module.build_rpr_rows, module.build_overture_rows):
        rows.extend(builder())

    # The judicial evidence index recognizes Preface / Preliminary Principle
    # citations that the legacy authority extractor does not. Bring those audited
    # rows into the shared catalogue so they appear with the other case links.
    case_rows = read_json(root / "index" / "case_provision_index.json", [])
    if canonical_id:
        for item in case_rows:
            if not str(canonical_id(item.get("provision", "")) or "").startswith("bco:pp-"):
                continue
            rows.append({
                "provision": item.get("provision", ""),
                "type": "Judicial case",
                "authority_weight": "high",
                "title": item.get("title", ""),
                "year": item.get("year"),
                "disposition": item.get("disposition", ""),
                "standard_of_review": item.get("standard_of_review"),
                "review_standards": item.get("review_standards") or [],
                "case_numbers": item.get("case_numbers") or [],
                "body": item.get("body", ""),
                "synopsis": item.get("synopsis", ""),
                "url": item.get("url", ""),
            })

        # RPR search rows contain curated BCO-section tags, but preliminary
        # principles are often named only in the exception text. Reuse the same
        # audited text parser used for judicial cases to add those occurrences.
        parser = _load_module(root / "scripts" / "44_case_provision_index.py",
                              "pca_provision_reference_parser", root)
        for item in read_json(root / "index" / "rpr_search.json", []):
            url = str(item.get("url") or "")
            source_path = root / Path(urlsplit(url).path).with_suffix(".md")
            if not source_path.is_file():
                continue
            title = f"{item.get('presbytery', '')}: {item.get('title', '')}".strip(": ")
            for provision, hits in parser.text_hits(source_path).items():
                identifier = canonical_id(provision) or ""
                if not identifier.startswith("bco:pp-"):
                    continue
                for hit in hits:
                    rows.append({
                        "provision": provision,
                        "type": "RPR exception",
                        "authority_weight": "low-but-important",
                        "title": title,
                        "year": item.get("year"),
                        "disposition": item.get("disposition", ""),
                        "url": url,
                        "snippet": hit.get("snippet", ""),
                        "evidence_line": hit.get("line"),
                        "evidence_source": "rpr_markdown_text",
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
                "snippet": item.get("sub", ""),
            })
    return rows


def _input_fingerprint(root: Path, reader_dir: Path, reader_meta: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
    paths = [root / relative for relative in INPUTS]
    paths.extend(sorted((root / "cases").glob("*.md")))
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
                            ([row["evidence_source"]] if row.get("evidence_source") else [])),
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
            "sources": ((evidence_row or {}).get("sources") or
                        ([row["evidence_source"]] if row.get("evidence_source") else [])),
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
                "relevance_status": "unreviewed",
                "occurrences": [],
                "metadata": {},
            }
            relationships[key] = relationship
        if not relationship.get("year") and row.get("year"):
            relationship["year"] = row["year"]
        if not relationship.get("disposition") and row.get("disposition"):
            relationship["disposition"] = row["disposition"]
        for field in ("topics", "standard_of_review", "review_standards", "source", "case_numbers"):
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
                "relevance_status": relationship["relevance_status"],
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
