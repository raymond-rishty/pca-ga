#!/usr/bin/env python3
"""Project the generated provision catalogue to the versioned JSON APIs."""
from __future__ import annotations

import argparse
import copy
import html.parser
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from provision_catalogue import load_catalogue, reference_presentation


SCHEMA_VERSION = 3
SITE = "https://raymond-rishty.github.io/pca-ga"
READER = "https://raymond-rishty.github.io/pca-constitution-reader/"


class _TextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def public_url(value: str) -> str:
    value = str(value or "")
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return value
    path = parts.path.lstrip("./")
    if path.endswith(".md"):
        path = path[:-3] + ".html"
    if path.endswith(".markdown"):
        path = path[:-9] + ".html"
    return urlunsplit(("https", "raymond-rishty.github.io", "/pca-ga/" + path,
                       parts.query, parts.fragment))


def raw_url(value: str) -> str:
    parts = urlsplit(str(value or ""))
    if parts.scheme or parts.netloc:
        return str(value)
    path = parts.path.lstrip("./")
    return urlunsplit(("https", "raw.githubusercontent.com",
                       "/raymond-rishty/pca-ga/main/" + path, parts.query, ""))


def reader_url(unit: dict[str, Any]) -> str:
    if unit["book"] == "bco":
        anchor = unit["reader_ref"] if str(unit["reader_ref"]).startswith("bco/") else f"bco/{unit['reader_ref']}"
    else:
        anchor = f"{unit['book']}/{unit['reader_ref']}"
    return f"{READER}#{anchor}"


def route_url(unit: dict[str, Any]) -> str:
    return f"{SITE}/provisions/{unit['book']}/{unit['route_ref']}/"


def _api_relationship(relation: dict[str, Any]) -> dict[str, Any]:
    record_url = relation.get("record_url") or ""
    result = {
        "id": relation["id"],
        "record_id": relation["record_id"],
        "type": relation["type"],
        "title": relation["title"],
        "year": relation.get("year"),
        "disposition": relation.get("disposition") or "",
        "authority_weight": relation.get("authority_weight") or "",
        "url": public_url(record_url),
        "raw_url": raw_url(record_url),
        "evidence_basis": relation["evidence_basis"],
        "relevance_status": relation["relevance_status"],
        "occurrences": [],
    }
    result["reference_presentation"] = reference_presentation(relation)
    for occurrence in relation.get("occurrences") or []:
        path = occurrence.get("url") or record_url
        item = {
            "id": occurrence["id"],
            "url": public_url(path),
            "repository_path": path,
            "locator": copy.deepcopy(occurrence.get("locator") or {}),
            "excerpt": occurrence.get("excerpt") or "",
            "sources": occurrence.get("sources") or [],
        }
        item["raw_url"] = raw_url(path)
        result["occurrences"].append(item)
    if relation.get("metadata"):
        result["metadata"] = copy.deepcopy(relation["metadata"])
    return result


def provision_payload(unit: dict[str, Any], catalogue: dict[str, Any]) -> dict[str, Any]:
    citation = f"{unit['abbr']} {unit['ref']}"
    relationships = [_api_relationship(item) for item in unit.get("relationships") or []]
    return {
        "schema_version": SCHEMA_VERSION,
        "catalogue_version": catalogue["catalogue_version"],
        "id": unit["id"],
        "provision": citation,
        "book": unit["book"],
        "book_name": unit["book_name"],
        "abbreviation": unit["abbr"],
        "reference": unit["ref"],
        "title": unit["title"],
        "supplementary": bool(unit["supplementary"]),
        "canonical_url": route_url(unit),
        "reader_url": reader_url(unit),
        "current_text": {
            "html": unit["body"],
            "text": plain_text(unit["body"]),
        },
        "source": copy.deepcopy(catalogue["source"]),
        "input_fingerprint": catalogue["input_fingerprint"],
        "assessment_fingerprint": catalogue.get("assessment_fingerprint", ""),
        "assessment_summary": copy.deepcopy(catalogue.get("assessment_summary") or {}),
        "parent_id": unit.get("parent_id"),
        "children": list(unit.get("children") or []),
        "coverage": copy.deepcopy(unit["coverage"]),
        "relationship_count": len(relationships),
        "relationships": relationships,
        "history": copy.deepcopy(unit.get("history") or []),
    }


def bco_alias_slug(unit: dict[str, Any]) -> str:
    return re.sub(r"[^0-9a-z]+", "-", str(unit["ref"]).lower()).strip("-")


def _write(path: Path, payload: Any, pretty: bool) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None,
                      separators=None if pretty else (",", ":")) + "\n"
    data = text.encode("utf-8")
    path.write_bytes(data)
    return data


def _remove_stale_json(output: Path, expected: set[Path]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for path in output.rglob("*.json"):
        if path not in expected:
            path.unlink()


def project_catalogue(root: Path, catalogue: dict[str, Any], bco_out: Path,
                      provisions_out: Path, pretty: bool = False) -> tuple[int, int]:
    provisions = catalogue["provisions"]
    expected_provision_paths: set[Path] = set()
    expected_bco_paths: set[Path] = set()
    provision_entries = []
    bco_entries = []
    aliases: dict[str, list[dict[str, Any]]] = {}
    for unit in provisions:
        if unit["book"] != "bco" or not re.fullmatch(r"\d+(?:[-.][0-9a-z]+)*", unit["ref"], re.I):
            continue
        aliases.setdefault(bco_alias_slug(unit), []).append(unit)

    for unit in provisions:
        relpath = Path(unit["book"]) / f"{unit['route_ref']}.json"
        provision_path = provisions_out / relpath
        expected_provision_paths.add(provision_path)
        payload = provision_payload(unit, catalogue)
        contents = _write(provision_path, payload, pretty)
        provision_url = f"{SITE}/api/provisions/{relpath.as_posix()}"
        bco_slug = bco_alias_slug(unit) if unit["book"] == "bco" else ""
        bco_url = ""
        if unit["book"] == "bco" and bco_slug and len(aliases.get(bco_slug, [])) == 1:
            bco_path = bco_out / f"{bco_slug}.json"
            expected_bco_paths.add(bco_path)
            # Compatibility endpoint is a byte-identical copy of the canonical API payload.
            bco_path.parent.mkdir(parents=True, exist_ok=True)
            bco_path.write_bytes(contents)
            bco_url = f"{SITE}/api/bco/{bco_slug}.json"
            bco_entries.append({
                "id": unit["id"],
                "provision": f"{unit['abbr']} {unit['ref']}",
                "slug": bco_slug,
                "api_url": bco_url,
                "canonical_api_url": provision_url,
                "canonical_url": route_url(unit),
            })
        provision_entries.append({
            "id": unit["id"],
            "provision": f"{unit['abbr']} {unit['ref']}",
            "book": unit["book"],
            "reference": unit["ref"],
            "api_url": provision_url,
            "canonical_url": route_url(unit),
            "bco_compatibility_url": bco_url or None,
            "relationship_count": payload["relationship_count"],
        })

    provision_index = {
        "schema_version": SCHEMA_VERSION,
        "catalogue_version": catalogue["catalogue_version"],
        "source": catalogue["source"],
        "input_fingerprint": catalogue["input_fingerprint"],
        "provision_count": len(provision_entries),
        "provisions": provision_entries,
    }
    bco_index = {
        "schema_version": SCHEMA_VERSION,
        "catalogue_version": catalogue["catalogue_version"],
        "source": catalogue["source"],
        "input_fingerprint": catalogue["input_fingerprint"],
        "provision_count": len(bco_entries),
        "provisions": bco_entries,
    }
    expected_provision_paths.add(provisions_out / "index.json")
    expected_bco_paths.add(bco_out / "index.json")
    _remove_stale_json(provisions_out, expected_provision_paths)
    _remove_stale_json(bco_out, expected_bco_paths)
    _write(provisions_out / "index.json", provision_index, pretty)
    _write(bco_out / "index.json", bco_index, pretty)
    return len(provision_entries), len(bco_entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path.cwd(), type=Path)
    parser.add_argument("--out", type=Path, help="BCO compatibility output directory (default: ROOT/api/bco)")
    parser.add_argument("--provisions-out", type=Path,
                        help="canonical provision API directory (default: ROOT/api/provisions)")
    parser.add_argument("--catalogue", type=Path,
                        help="generated catalogue path (default: ROOT/index/provision_catalogue.json)")
    parser.add_argument("--pretty", action="store_true", help="write indented JSON for inspection")
    args = parser.parse_args()
    root = args.root.resolve()
    bco_out = (args.out or root / "api" / "bco").resolve()
    provisions_out = (args.provisions_out or root / "api" / "provisions").resolve()
    catalogue = load_catalogue((args.catalogue or root / "index" / "provision_catalogue.json").resolve())
    provision_count, bco_count = project_catalogue(root, catalogue, bco_out, provisions_out, args.pretty)
    print(f"Wrote {provision_count} provision API records and {bco_count} BCO compatibility aliases")


if __name__ == "__main__":
    main()
