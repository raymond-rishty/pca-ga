#!/usr/bin/env python3
"""45_bco_manifests.py — prototype provision-scoped JSON manifests.

This is a deliberately small proof of concept for the agent retrieval path:

    BCO provision -> one small manifest -> selected source artifacts

The authority rows come from ``43_authority_index.py`` (or its generated flat
JSON when that file already exists).  The prototype currently covers judicial
cases, constitutional inquiries, CCB advice, overtures, and RPR exceptions.
It does not yet infer topical relevance or tag studies whose metadata has no
constitutional provision.

Output (by default under ``<ROOT>/api/bco``):

    index.json       all indexed BCO provisions and counts
    <slug>.json      one manifest per BCO provision, e.g. ``38-1.json``

The output directory is configurable so this can be exercised in ``tmp/``
without changing the published site.

Usage:

    python3 scripts/45_bco_manifests.py [ROOT] [--out DIR]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SITE = "https://raymond-rishty.github.io/pca-ga"
RAW = "https://raw.githubusercontent.com/raymond-rishty/pca-ga/main"
SCHEMA_VERSION = 1

TYPE_INFO = {
    "Judicial case": {
        "kind": "case",
        "match_kind": "indexed_case_reference",
    },
    "Constitutional inquiry": {
        "kind": "inquiry",
        "match_kind": "structured_provision_reference",
    },
    "CCB advice": {
        "kind": "ccb_advice",
        "match_kind": "structured_provision_reference",
    },
    "Overture": {
        "kind": "overture",
        "match_kind": "subject_reference",
    },
    "RPR exception": {
        "kind": "rpr_exception",
        "match_kind": "structured_provision_reference",
    },
}

WEIGHT_RANK = {"high": 0, "medium": 1, "low-but-important": 2}
KIND_RANK = {"case": 0, "inquiry": 1, "ccb_advice": 2, "overture": 3, "rpr_exception": 4}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_authority_module(root: Path):
    """Load 43_authority_index.py without running its file-writing main()."""
    path = root / "scripts" / "43_authority_index.py"
    if not path.exists():
        raise FileNotFoundError(path)

    spec = importlib.util.spec_from_file_location("pca_authority_index", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    saved_argv = sys.argv[:]
    try:
        # 43 reads ROOT from argv at import time.  Its main() is protected, so
        # this only initializes the helper functions and module constants.
        sys.argv = [str(path), str(root)]
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved_argv

    module.ROOT = str(root)
    module.IDX = str(root / "index")
    module.CASES_DIR = str(root / "cases")
    module.AUTH_DIR = str(root / "authorities")
    return module


def authority_rows(root: Path) -> tuple[list[dict[str, Any]], str]:
    """Load the existing flat map, or build its rows in memory for a POC run."""
    flat = root / "index" / "authority_index.json"
    if flat.exists():
        return load_json(flat, []), "index/authority_index.json"

    module = load_authority_module(root)
    rows: list[dict[str, Any]] = []
    for builder in (
        module.build_case_rows,
        module.build_inquiry_rows,
        module.build_rpr_rows,
        module.build_overture_rows,
    ):
        rows.extend(builder())
    return rows, "scripts/43_authority_index.py (in-memory)"


def ccb_advice_rows(root: Path) -> list[dict[str, Any]]:
    """Add CCB advice rows, which the older authority index intentionally omits."""
    rows: list[dict[str, Any]] = []
    for row in load_json(root / "index" / "inquiries_search.json", []):
        if row.get("type") != "ccb-advice":
            continue
        for provision in row.get("provisions") or []:
            rows.append({
                "provision": provision,
                "type": "CCB advice",
                "authority_weight": "medium",
                "title": row.get("title", ""),
                "year": row.get("year"),
                "disposition": row.get("disposition", ""),
                "url": row.get("url", ""),
                "snippet": row.get("sub", ""),
            })
    return rows


def normalize_provision(value: str) -> str:
    """Normalize the BCO forms accepted by the existing authority index."""
    value = re.sub(r"\s+", " ", str(value or "").strip()).replace("–", "-")
    value = re.sub(r"^BCO\s*§?\s*", "BCO ", value, flags=re.I)
    value = re.sub(
        r"^(BCO) (\d+)[.:](\d)",
        lambda match: f"{match.group(1)} {match.group(2)}-{match.group(3)}",
        value,
        flags=re.I,
    )
    value = re.sub(r"(-\d+)\(([a-z])\)", r"\1.\2", value, flags=re.I)
    value = re.sub(r"(-\d+)([a-zA-Z])$", r"\1.\2", value)
    # Provision suffixes are identifiers, not prose: keep ``.c`` and ``.C``
    # on the same canonical route so they cannot overwrite one another.
    value = re.sub(r"(?<=\.)[A-Za-z]+$", lambda match: match.group(0).lower(), value)
    return value.rstrip(":;.,)")


def is_numbered_bco(value: str) -> bool:
    return bool(re.fullmatch(r"BCO \d+(?:-\d+)?(?:\.[0-9a-z]+)*", value, re.I))


def bco_slug(value: str) -> str:
    body = value.removeprefix("BCO ").strip().lower()
    return re.sub(r"[^0-9a-z]+", "-", body).strip("-")


def public_url(path: str) -> str:
    """Convert a repository-relative Markdown link to the public HTML URL."""
    parts = urlsplit(str(path or ""))
    if parts.scheme or parts.netloc:
        return str(path)
    repo_path = parts.path.lstrip("./")
    if repo_path.endswith(".md"):
        repo_path = repo_path[:-3] + ".html"
    return urlunsplit(("https", "raymond-rishty.github.io", "/pca-ga/" + repo_path,
                       parts.query, parts.fragment))


def raw_url(path: str) -> str:
    parts = urlsplit(str(path or ""))
    if parts.scheme or parts.netloc:
        return str(path)
    repo_path = parts.path.lstrip("./")
    return urlunsplit(("https", "raw.githubusercontent.com",
                       "/raymond-rishty/pca-ga/main/" + repo_path,
                       parts.query, ""))


def artifact_id(kind: str, path: str) -> str:
    # Keep IDs readable while making unusual/long paths safe and stable.
    clean = urlsplit(path).path.lstrip("./")
    readable = re.sub(r"[^A-Za-z0-9._/-]+", "-", clean).removesuffix(".md")
    if len(readable) <= 120:
        return f"{kind}:{readable}"
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:12]
    return f"{kind}:{readable[:100]}-{digest}"


def case_evidence(root: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Index the richer case reverse map for optional evidence enrichment."""
    rows = load_json(root / "index" / "case_provision_index.json", [])
    out: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        provision = normalize_provision(row.get("provision", ""))
        url = str(row.get("url", ""))
        if provision and url:
            out[(provision, url)].append(row)
    return out


def case_metadata(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in load_jsonl(root / "index" / "cases.jsonl"):
        number = row.get("case_number")
        if number:
            out[str(number)] = row
    return out


def merge_unique(items: list[Any], additions: list[Any]) -> list[Any]:
    seen = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in items}
    for item in additions:
        marker = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if marker not in seen:
            items.append(item)
            seen.add(marker)
    return items


def build_artifacts(root: Path, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    evidence_by_key = case_evidence(root)
    metadata_by_number = case_metadata(root)
    by_provision: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)

    for row in rows:
        info = TYPE_INFO.get(row.get("type", ""))
        if not info:
            continue
        provision = normalize_provision(row.get("provision", ""))
        if not is_numbered_bco(provision):
            continue
        source_path = str(row.get("url", "")).strip()
        if not source_path:
            continue

        kind = info["kind"]
        key = artifact_id(kind, source_path)
        artifact = by_provision[provision].get(key)
        if artifact is None:
            source_parts = urlsplit(source_path)
            artifact = {
                "id": key,
                "type": kind,
                "authority_weight": row.get("authority_weight", ""),
                "title": row.get("title", ""),
                "year": row.get("year"),
                "disposition": row.get("disposition", ""),
                "url": public_url(source_path),
                "raw_url": raw_url(source_path),
                "matches": [],
            }
            if source_parts.fragment:
                artifact["anchor"] = source_parts.fragment
            by_provision[provision][key] = artifact

        snippet = str(row.get("snippet", "") or "").strip()
        match_kind = info["match_kind"]
        if kind == "case":
            case_rows = evidence_by_key.get((provision, source_path), [])
            has_text_evidence = any(item.get("evidence") for item in case_rows)
            snippet_has_reference = bool(snippet) and bool(re.search(
                r"BCO\s+" + re.escape(provision.removeprefix("BCO ")), snippet, re.I
            ))
            if has_text_evidence or snippet_has_reference:
                match_kind = "case_text_reference"
            else:
                # The older authority index may have supplied a fallback
                # heading snippet when the relation came from cases.jsonl.
                snippet = ""
                match_kind = "structured_case_metadata_reference"
        match = {
            "kind": match_kind,
            "provision": provision,
            "evidence": snippet,
            "source": "authority_index",
        }
        if match not in artifact["matches"]:
            artifact["matches"].append(match)

        if kind == "case":
            for enriched in evidence_by_key.get((provision, source_path), []):
                artifact["case_numbers"] = merge_unique(
                    artifact.get("case_numbers", []),
                    list(enriched.get("case_numbers") or []),
                )
                if enriched.get("body") and not artifact.get("body"):
                    artifact["body"] = enriched["body"]
                if enriched.get("synopsis") and not artifact.get("synopsis"):
                    artifact["synopsis"] = enriched["synopsis"]
                for evidence in enriched.get("evidence") or []:
                    evidence_match = {
                        "kind": "case_text_evidence",
                        "provision": provision,
                        "evidence": evidence.get("snippet", ""),
                        "line": evidence.get("line"),
                        "source": "case_provision_index",
                    }
                    if evidence_match not in artifact["matches"]:
                        artifact["matches"].append(evidence_match)

            locators = []
            for number in artifact.get("case_numbers", []):
                case = metadata_by_number.get(str(number))
                if not case:
                    continue
                locator = {
                    "case_number": number,
                    "ga_ordinal": case.get("ga_ordinal"),
                    "printed_page_start": case.get("printed_page_start"),
                    "printed_page_end": case.get("printed_page_end"),
                    "pdf_page_start": case.get("pdf_page_start"),
                    "pdf_page_end": case.get("pdf_page_end"),
                }
                if locator not in locators:
                    locators.append(locator)
            if locators:
                artifact["minutes_locators"] = locators

    result: dict[str, list[dict[str, Any]]] = {}
    for provision, artifact_map in by_provision.items():
        artifacts = list(artifact_map.values())
        artifacts.sort(key=lambda item: (
            WEIGHT_RANK.get(item.get("authority_weight", ""), 9),
            KIND_RANK.get(item.get("type", ""), 9),
            -(int(item["year"]) if str(item.get("year", "")).isdigit() else 0),
            str(item.get("title", "")).casefold(),
            item["id"],
        ))
        result[provision] = artifacts
    return result


def counts(artifacts: list[dict[str, Any]]) -> dict[str, int]:
    result = collections.Counter(item.get("type", "unknown") for item in artifacts)
    return {
        key: result[key]
        for key in ("case", "inquiry", "ccb_advice", "overture", "rpr_exception")
        if result[key]
    }


def write_json(path: Path, payload: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="/workspace", type=Path)
    parser.add_argument("--out", type=Path, help="output directory (default: ROOT/api/bco)")
    parser.add_argument("--pretty", action="store_true", help="write indented JSON for inspection")
    args = parser.parse_args()
    root = args.root.resolve()
    out = (args.out or (root / "api" / "bco")).resolve()

    rows, source = authority_rows(root)
    ccb_rows = ccb_advice_rows(root)
    if ccb_rows:
        rows.extend(ccb_rows)
        source += "; index/inquiries_search.json (CCB advice)"
    grouped = build_artifacts(root, rows)
    out.mkdir(parents=True, exist_ok=True)

    provision_rows = []
    for provision in sorted(grouped, key=lambda value: (
        [int(part) for part in re.findall(r"\d+", value)], value
    )):
        slug = bco_slug(provision)
        artifacts = grouped[provision]
        counts_for_provision = counts(artifacts)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "provision": provision,
            "constitution_url": (
                f"https://raymond-rishty.github.io/pca-constitution-reader/#bco/{slug}"
            ),
            "scope": "GA1–GA52",
            "source_map": source,
            "counts": counts_for_provision,
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        }
        write_json(out / f"{slug}.json", manifest, pretty=args.pretty)
        provision_rows.append({
            "provision": provision,
            "slug": slug,
            "manifest": f"{SITE}/api/bco/{slug}.json",
            "counts": counts_for_provision,
            "artifact_count": len(artifacts),
        })

    write_json(out / "index.json", {
        "schema_version": SCHEMA_VERSION,
        "scope": "GA1–GA52",
        "source_map": source,
        "provision_count": len(provision_rows),
        "provisions": provision_rows,
    }, pretty=args.pretty)

    total = sum(len(artifacts) for artifacts in grouped.values())
    print(f"Wrote {len(provision_rows)} provision manifests and {total} deduplicated artifacts to {out}")
    for target in ("BCO 38-1", "BCO 17-3", "BCO 34-10", "BCO 24"):
        if target in grouped:
            print(f"  {target}: {len(grouped[target])} artifacts ({counts(grouped[target])})")
        else:
            print(f"  {target}: no indexed artifacts")


if __name__ == "__main__":
    main()
