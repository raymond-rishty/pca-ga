#!/usr/bin/env python3
"""Shared projection of curated overture records and explicit body references."""
from __future__ import annotations

import json
import importlib.util
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from overture_identity import load_reconciled_overture_records


_PROV = re.compile(r"BCO\s+\d+-\d+(?:\.[0-9a-z]+)*", re.I)


def _case_provision_parser():
    path = Path(__file__).with_name("44_case_provision_index.py")
    spec = importlib.util.spec_from_file_location("pca_case_provision_parser", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load citation parser: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_curated_overtures(index_dir: Path) -> list[dict[str, Any]]:
    """Project reconciled records and join evidence only to the exact source page."""
    citation_parser = _case_provision_parser()
    bodies = _jsonl(index_dir / "overture_bodies.jsonl")
    catalogue = load_reconciled_overture_records(index_dir)
    if not catalogue:
        return []

    def key(row: dict[str, Any]) -> tuple[str, str, int]:
        return (str(row.get("vol") or ""), str(row.get("number") or ""),
                int(row.get("pdf_page") or row.get("source_page") or -1))

    body_candidates: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for body_row in bodies:
        body_candidates[key(body_row)].append(body_row)
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for record in catalogue:
        pair_counts[(record["vol"], str(record["number"]))] += 1

    def body_score(row: dict[str, Any]) -> tuple[int, int]:
        text = str(row.get("body") or "")
        proposal_language = re.search(
            r"\b(whereas|be it (further )?resolved|therefore|resolved,? that|now,? therefore)\b",
            text, re.I,
        )
        return (1 if proposal_language else 0, len(text))

    records = []
    for record in catalogue:
        volume = record["vol"]
        number = int(record["number"])
        page = int(record["source_page"])
        exact_key = (volume, str(number), page)
        candidates = body_candidates.get(exact_key, [])
        if not candidates and pair_counts[(volume, str(number))] == 1:
            # A unique overture may have a useful extraction on another page of
            # its own record. Reused numbers never receive this fallback.
            candidates = [body_row for body_key, rows in body_candidates.items()
                          if body_key[:2] == (volume, str(number)) for body_row in rows]
        body = max(candidates, key=body_score) if candidates else {}
        title = str(record.get("title") or "").strip()
        url = f"markdown/{volume}.md"
        if page:
            url += f"#{volume.split('_')[0]}-p{page}"
        provisions: set[str] = set()
        provision_sources: dict[str, set[str]] = defaultdict(set)
        for match in _PROV.findall(title):
            provision = match.upper()
            provisions.add(provision)
            provision_sources[provision].add("title_subject")

        evidence_by_provision: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if body:
            body_text = str(body.get("body") or "")
            evidence_page = body.get("pdf_page")
            evidence_url = f"markdown/{volume}.md"
            if evidence_page:
                evidence_url += f"#{volume.split('_')[0]}-p{evidence_page}"
            for provision, hits in citation_parser.text_hits_from_text(body_text).items():
                provisions.add(provision)
                provision_sources[provision].add("overture_body_text")
                for hit in hits:
                    evidence = {
                        "excerpt": hit.get("snippet", ""),
                        "page": evidence_page,
                        "url": evidence_url,
                        "relationship_kind": "explicit_citation",
                        "match_method": "overture_body_explicit_reference_match",
                    }
                    if evidence not in evidence_by_provision[provision]:
                        evidence_by_provision[provision].append(evidence)
        records.append({
            "record_id": record["record_id"],
            "vol": volume,
            "number": number,
            "page": page,
            "title": title,
            "source": (body.get("source") or record.get("source") or "").strip(),
            "year": record.get("year"),
            "disposition": record.get("disposition") or "",
            "provisions": sorted(provisions),
            "provision_sources": {
                provision: sorted(sources)
                for provision, sources in sorted(provision_sources.items())
            },
            "provision_evidence": [
                {"provision": provision, **evidence}
                for provision in sorted(evidence_by_provision)
                for evidence in evidence_by_provision[provision]
            ],
            "url": url,
        })
    return records


def overture_records(index_dir: Path) -> list[dict[str, Any]]:
    """Load the reconciled, page-qualified roster and its exact-page evidence."""
    return load_curated_overtures(index_dir)


def search_rows(index_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for record in overture_records(index_dir):
        number = record["number"]
        source = record["source"]
        rows.append({
            "type": "Overture",
            "record_id": record["record_id"],
            "title": record["title"],
            "sub": f"Overture {number}" + (f" · {source}" if source else ""),
            "identifier": f"Overture {number}",
            "identifiers": [f"Overture {number}"],
            "topics": [record["title"]],
            "provisions": record["provisions"],
            "year": record["year"],
            "disposition": record["disposition"],
            "url": record["url"],
        })
    return rows
