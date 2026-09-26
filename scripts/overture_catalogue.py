#!/usr/bin/env python3
"""Shared projection of curated overture records and explicit body references."""
from __future__ import annotations

import json
import importlib.util
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


_HEAD = re.compile(r"^##\s+.*General Assembly\s*\((\d{4})\)")
_LINK = re.compile(r"\]\(\.\./([^)#]+(?:#[^)]+)?)\)")
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
    """Join the curated title, disposition, and body files by page occurrence."""
    citation_parser = _case_provision_parser()
    dispositions = _jsonl(index_dir / "overture_dispositions.jsonl")
    titles = _jsonl(index_dir / "overture_titles.jsonl")
    bodies = _jsonl(index_dir / "overture_bodies.jsonl")
    if not dispositions or not titles or not bodies:
        return []

    def key(row: dict[str, Any]) -> tuple[Any, str, Any]:
        return row.get("vol"), str(row.get("number")), row.get("pdf_page")

    title_by_key = {key(row): (row.get("title") or "").strip() for row in titles}
    titles_by_record: dict[tuple[Any, str], list[str]] = defaultdict(list)
    for title_row in titles:
        title = (title_row.get("title") or "").strip()
        if title:
            titles_by_record[(title_row.get("vol"), str(title_row.get("number")))].append(title)
    body_by_key = {key(row): row for row in bodies}
    bodies_by_record: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
    for body_row in bodies:
        bodies_by_record[(body_row.get("vol"), str(body_row.get("number")))].append(body_row)

    def sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
        volume = str(row.get("vol") or "")
        assembly = re.match(r"ga(\d+)", volume)
        return (int(assembly.group(1)) if assembly else 999,
                int(row.get("number") or 0), int(row.get("pdf_page") or 0))

    records = []
    for row in sorted(dispositions, key=sort_key):
        occurrence_key = key(row)
        title = title_by_key.get(occurrence_key, "")
        if not title:
            # Some title rows carry a printed-page value where disposition
            # and body rows carry the PDF-page value. Overture numbers are
            # unique within an assembly, so recover only an unambiguous title.
            candidates = titles_by_record.get((row.get("vol"), str(row.get("number"))), [])
            if len(candidates) == 1:
                title = candidates[0]
        if not title:
            continue
        volume = str(row.get("vol") or "")
        volume_match = re.match(r"ga\d+_(\d{4})$", volume)
        year = int(volume_match.group(1)) if volume_match else None
        body = body_by_key.get(occurrence_key, {})
        number = int(row.get("number") or 0)
        page = row.get("pdf_page")
        url = f"markdown/{volume}.md"
        if page:
            url += f"#{volume.split('_')[0]}-p{page}"
        provisions: set[str] = set()
        provision_sources: dict[str, set[str]] = defaultdict(set)
        for value in row.get("bco") or []:
            if value:
                provision = f"BCO {value}"
                provisions.add(provision)
                provision_sources[provision].add("disposition_bco")
        for match in _PROV.findall(title):
            provision = match.upper()
            provisions.add(provision)
            provision_sources[provision].add("title_subject")

        evidence_by_provision: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for body_row in bodies_by_record.get((volume, str(number)), [body]):
            body_text = str(body_row.get("body") or "")
            evidence_page = body_row.get("pdf_page")
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
            "record_id": f"overture:{volume}:{number}",
            "vol": volume,
            "number": number,
            "page": page,
            "title": title,
            "source": (body.get("source") or "").strip(),
            "year": year,
            "disposition": row.get("final_disposition") or row.get("disposition") or "",
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


def _fallback_overtures(index_dir: Path) -> list[dict[str, Any]]:
    path = index_dir / "OVERTURES.md"
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    year = None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _HEAD.match(line)
        if heading:
            year = int(heading.group(1))
            continue
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        number_match = re.search(r"\[(\d+)\]", cells[0])
        number = number_match.group(1) if number_match else cells[0]
        if not number.isdigit() or not cells[1]:
            continue
        link = _LINK.search(cells[4])
        title_provisions = sorted({match.upper() for match in _PROV.findall(cells[1])})
        records.append({
            "record_id": f"overture:catalogue:{year}:{int(number)}",
            "vol": "",
            "number": int(number),
            "page": None,
            "title": cells[1],
            "source": cells[3],
            "year": year,
            "disposition": cells[2],
            "provisions": title_provisions,
            "provision_sources": {provision: ["title_subject"] for provision in title_provisions},
            "url": link.group(1) if link else "index/OVERTURES.md",
        })
    return records


def overture_records(index_dir: Path) -> list[dict[str, Any]]:
    """Use page-keyed curated data, falling back only for incomplete legacy trees."""
    return load_curated_overtures(index_dir) or _fallback_overtures(index_dir)


def search_rows(index_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for record in overture_records(index_dir):
        number = record["number"]
        source = record["source"]
        rows.append({
            "type": "Overture",
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
