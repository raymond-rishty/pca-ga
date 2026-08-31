#!/usr/bin/env python3
"""Build and validate the extracted-document source registry.

The registry is durable data, while this script is the deterministic projection
from the repository's source indexes. Use --write when an authoritative source
index changes and --check in CI.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

VOLUME_RE = re.compile(r"^ga\d+_\d{4}$")
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
PDF_URL_RE = re.compile(r"^https://(?:www\.)?pcahistory\.org/.+\.pdf(?:#page=\d+)?$", re.I)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def canonical_pdf_url(url: str) -> str:
    return str(url).split("#", 1)[0].split("?", 1)[0]


def inquiry_groups(inquiries: Any) -> list[dict[str, Any]]:
    """Accept both the legacy object and the current list inquiry index shapes."""
    if isinstance(inquiries, dict):
        return [group for group in inquiries.values() if isinstance(group, dict)]
    if isinstance(inquiries, list):
        return [group for group in inquiries if isinstance(group, dict)]
    raise ValueError("index/inquiries_located.json must contain inquiry groups")


def valid_volume(value: Any) -> bool:
    return isinstance(value, str) and bool(VOLUME_RE.fullmatch(value))


def ordinal_suffix(value: int) -> str:
    if 10 <= value % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")


def minutes_filename(volume: str) -> str:
    match = re.fullmatch(r"ga(\d+)_(\d{4})", volume)
    if not match:
        raise ValueError(f"invalid volume: {volume}")
    ordinal = int(match.group(1))
    return f"{ordinal}{ordinal_suffix(ordinal)}_pcaga_{match.group(2)}.pdf"


def minutes_url(volume: str) -> str:
    return f"https://www.pcahistory.org/pca/ga/{minutes_filename(volume)}"


def safe_name(value: Any) -> str:
    text = re.sub(r"\.pdf$", "", str(value), flags=re.I)
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    return text or "unknown"


def normalize_case(value: Any) -> str | None:
    if value is None:
        return None
    match = re.search(r"(?:^|[^\d])(\d{4})[-–](\d{1,3})(?:$|[^\d])", str(value))
    return f"{match.group(1)}-{int(match.group(2))}" if match else str(value).strip()


def case_numbers(row: dict[str, Any]) -> list[str]:
    text = " ".join(str(row[key]) for key in ("case_number", "case_number_raw", "title") if row.get(key))
    values: list[str] = []
    for match in re.finditer(
        r"(?:^|[^\d])((?:19|20)\d{2})[-–](\d{1,3})(?:$|[^\d])", text
    ):
        value = f"{match.group(1)}-{int(match.group(2))}"
        if value not in values:
            values.append(value)
    primary = normalize_case(row.get("case_number")) or normalize_case(row.get("case_number_raw"))
    if primary and primary not in values:
        values.append(primary)
    return values


def url_path(url: str) -> str:
    match = re.match(r"https?://[^/]+/(.*)$", url)
    return match.group(1) if match else url.lstrip("/")


def build(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cases = load_jsonl(root / "index/cases.jsonl")
    roster = load_jsonl(root / "index/sjc_official/roster.jsonl")
    inquiries = load_json(root / "index/inquiries_located.json")
    studies = load_json(root / "index/studies_pages.json")
    manifest = load_json(root / "index/studies_pdf_manifest.json")
    pcahistory = load_json(root / "index/studies_pcahistory.json")
    overtures = load_jsonl(root / "index/overture_bodies.jsonl")
    rpr_rows: list[dict[str, Any]] = []
    for path in sorted((root / "index" / "rpr").glob("ga*.json")):
        parsed = load_json(path)
        rows = parsed if isinstance(parsed, list) else parsed.get("records", [])
        for source_index, row in enumerate(rows):
            rpr_rows.append({**row, "_source_index": source_index})

    sources: dict[str, dict[str, Any]] = {}
    mappings: dict[str, list[str]] = {}
    inventory: dict[str, dict[str, Any]] = {}
    volumes: set[str] = set()

    def add_volume(volume: Any) -> None:
        if valid_volume(volume):
            volumes.add(volume)

    def add_source(source: dict[str, Any]) -> None:
        source_id = source.get("source_id")
        if not source_id:
            return
        existing = sources.get(source_id)
        if existing:
            if existing.get("url") and source.get("url") and existing["url"] != source["url"]:
                raise ValueError(f"source URL collision: {source_id}")
            for key, value in source.items():
                if existing.get(key) is None:
                    existing[key] = value
        else:
            sources[source_id] = source

    def add_minutes(volume: Any) -> str | None:
        if not valid_volume(volume):
            return None
        add_volume(volume)
        match = re.fullmatch(r"ga(\d+)_(\d{4})", volume)
        source_id = f"minutes:{volume}"
        add_source({
            "source_id": source_id,
            "kind": "minutes",
            "volume": volume,
            "ga_ordinal": int(match.group(1)),
            "year": int(match.group(2)),
            "pdf_path": f"pca/ga/{minutes_filename(volume)}",
            "url": minutes_url(volume),
            "status": "canonical",
            "local_pdf_path": None,
        })
        return source_id

    def add_mapping(record_id: str, source_ids: list[str | None]) -> None:
        if not record_id:
            return
        target = mappings.setdefault(record_id, [])
        for source_id in source_ids:
            if source_id and source_id not in target:
                target.append(source_id)
        if not target:
            mappings.pop(record_id, None)

    def add_dedicated(
        prefix: str,
        url: str | None,
        record_type: str,
        record_id: str | None,
        inventory_source: str,
        status: str = "listed",
        local_artifact_path: str | None = None,
        notes: str | None = None,
    ) -> str | None:
        if not url or not re.search(r"\.pdf(?:[?#]|$)", url, re.I):
            return None
        clean = canonical_pdf_url(url)
        source_id = f"{prefix}-pdf:{safe_name(clean.rsplit('/', 1)[-1])}"
        source = {
            "source_id": source_id,
            "kind": "dedicated_pdf",
            "record_type": record_type,
            "pdf_path": url_path(clean),
            "url": clean,
            "status": status,
            "inventory_source": inventory_source,
            "local_pdf_path": None,
        }
        if local_artifact_path:
            source["local_artifact_path"] = local_artifact_path
        if notes:
            source["notes"] = notes
        add_source(source)
        if clean not in inventory:
            item = {
                "source_id": source_id,
                "record_type": record_type,
                "record_id": record_id,
                "url": clean,
                "pdf_path": url_path(clean),
                "status": status,
                "inventory_source": inventory_source,
                "local_pdf_path": None,
            }
            if local_artifact_path:
                item["local_artifact_path"] = local_artifact_path
            item["notes"] = notes or "Canonical external PDF is indexed but not vendored in this repository."
            inventory[clean] = item
        return source_id

    for row in cases:
        if row.get("ga_ordinal") is not None and row.get("year") is not None:
            add_volume(f"ga{int(row['ga_ordinal']):02d}_{int(row['year'])}")
    for group in inquiry_groups(inquiries):
        add_volume(group.get("stem"))
    for row in studies:
        add_volume(row.get("vol"))
    for doc in manifest.get("documents", []):
        for source_range in doc.get("ranges", []):
            add_volume(source_range.get("vol"))
    for row in overtures:
        add_volume(row.get("vol"))
    for row in rpr_rows:
        add_volume(row.get("vol"))
    for volume in sorted(volumes):
        add_minutes(volume)

    roster_by_number: dict[str, list[str]] = {}
    for row in roster:
        numbers = case_numbers(row)
        if not numbers or not row.get("has_pdf") or not row.get("pdf_url"):
            continue
        source_id = add_dedicated(
            "case",
            row["pdf_url"],
            "case",
            numbers[0],
            "index/sjc_official/roster.jsonl",
            notes="Listed by the repository's SJC official roster; PDF binary is external and not vendored.",
        )
        for number in numbers:
            roster_by_number.setdefault(number, [])
            if source_id and source_id not in roster_by_number[number]:
                roster_by_number[number].append(source_id)
            add_mapping(f"case:{number}", [source_id])

    manifest_by_url: dict[str, str] = {}
    manifest_sources: dict[int, str] = {}
    for index, doc in enumerate(manifest.get("documents", [])):
        file = doc.get("pcahistory_file")
        url = doc.get("pcahistory_url") or (
            f"https://www.pcahistory.org/pca/digest/studies/{file}"
            if file and str(file).lower().endswith(".pdf") else None
        )
        if not url or not re.search(r"\.pdf(?:[?#]|$)", url, re.I):
            continue
        source_id = add_dedicated(
            "study",
            url,
            "study",
            file or doc.get("topic"),
            "index/studies_pdf_manifest.json",
            status=doc.get("status") or "manifest",
            local_artifact_path=doc.get("pdf_text_artifact"),
            notes="Listed by the committed study PDF manifest; PDF binary is external and not vendored.",
        )
        if source_id:
            manifest_sources[index] = source_id
            manifest_by_url[canonical_pdf_url(url)] = source_id

    for doc in pcahistory.get("docs", []):
        file = doc.get("file")
        url = (
            f"https://www.pcahistory.org/pca/digest/studies/{file}"
            if file and str(file).lower().endswith(".pdf") else None
        )
        add_dedicated(
            "study",
            url,
            "study",
            file,
            "index/studies_pcahistory.json",
            status="pdf_only",
            notes="Roster-gap study source listed in the PCA Historical Center index; not vendored.",
        )

    for row in cases:
        ids: list[str | None] = []
        for number in case_numbers(row):
            ids.extend(roster_by_number.get(number, []))
        volume = (
            f"ga{int(row['ga_ordinal']):02d}_{int(row['year'])}"
            if row.get("ga_ordinal") is not None and row.get("year") is not None else None
        )
        ids.append(add_minutes(volume))
        add_mapping(f"case:{row.get('case_id')}", ids)
        for number in case_numbers(row):
            add_mapping(f"case:{number}", ids)

    inquiry_count = 0
    for group in inquiry_groups(inquiries):
        source_id = add_minutes(group.get("stem"))
        for index, result in enumerate(group.get("results", [])):
            inquiry_count += 1
            ids = [source_id]
            add_mapping(f"inquiry:{group.get('stem')}:{index}", ids)
            if result.get("minute_para"):
                add_mapping(
                    f"inquiry:{group.get('stem')}:{result['minute_para']}:{index}", ids
                )

    for index, row in enumerate(overtures):
        source_id = add_minutes(row.get("vol"))
        number = str(row.get("number", "")).strip()
        if valid_volume(row.get("vol")) and number:
            add_mapping(f"overture:{row['vol']}:{number}", [source_id])
        add_mapping(f"overture:{row.get('vol')}:{number}:{index}", [source_id])

    for index, row in enumerate(rpr_rows):
        source_id = add_minutes(row.get("vol"))
        sequence = row.get("seq")
        fallback = f"{row.get('vol', 'unknown')}:{sequence if sequence is not None else row['_source_index']}"
        record_id = str(row.get("id") or fallback)
        add_mapping(f"rpr:{record_id}", [source_id])
        if valid_volume(row.get("vol")):
            add_mapping(f"rpr:{row['vol']}:{record_id}", [source_id])

    def overlaps(page: dict[str, Any], source_range: dict[str, Any]) -> bool:
        return (
            valid_volume(page.get("vol"))
            and page.get("vol") == source_range.get("vol")
            and int(page.get("line_start") or 0) > 0
            and int(page.get("line_end") or 0) >= int(page.get("line_start") or 0)
            and int(source_range.get("line_start") or 0) > 0
            and int(source_range.get("line_end") or 0) >= int(source_range.get("line_start") or 0)
            and int(page["line_start"]) <= int(source_range["line_end"])
            and int(source_range["line_start"]) <= int(page["line_end"])
        )

    study_count = 0
    study_with_source = 0
    for index, page in enumerate(studies):
        study_count += 1
        dedicated_ids: list[str | None] = []
        minutes_ids: list[str | None] = []
        key = f"study:{page.get('file', index)}"
        external = page.get("external_url")
        if external and canonical_pdf_url(external) in manifest_by_url:
            dedicated_ids.append(manifest_by_url[canonical_pdf_url(external)])
        for manifest_index, doc in enumerate(manifest.get("documents", [])):
            if any(overlaps(page, source_range) for source_range in doc.get("ranges", [])):
                dedicated_ids.append(manifest_sources.get(manifest_index))
                for source_range in doc.get("ranges", []):
                    if overlaps(page, source_range):
                        minutes_ids.append(add_minutes(source_range.get("vol")))
        ids = dedicated_ids + minutes_ids
        if not ids and valid_volume(page.get("vol")):
            ids.append(add_minutes(page.get("vol")))
        add_mapping(key, ids)
        if ids:
            study_with_source += 1

    for manifest_index, doc in enumerate(manifest.get("documents", [])):
        ids = [manifest_sources.get(manifest_index)]
        ids.extend(add_minutes(source_range.get("vol")) for source_range in doc.get("ranges", []))
        add_mapping(f"study-manifest:{doc.get('pcahistory_file') or doc.get('topic')}", ids)

    source_list = sorted(sources.values(), key=lambda item: item["source_id"].casefold())
    inventory_list = sorted(inventory.values(), key=lambda item: item["source_id"].casefold())
    registry = {
        "schema_version": 1,
        "description": "Durable source identities for extracted PCA documents. Source IDs separate provenance data from URL rendering.",
        "generated_from": [
            "index/cases.jsonl",
            "index/sjc_official/roster.jsonl",
            "index/inquiries_located.json",
            "index/overture_bodies.jsonl",
            "index/rpr/*.json",
            "index/studies_pages.json",
            "index/studies_pdf_manifest.json",
            "index/studies_pcahistory.json",
        ],
        "source_precedence": ["dedicated_pdf", "minutes"],
        "sources": source_list,
        "record_sources": {key: mappings[key] for key in sorted(mappings)},
        "coverage": {
            "cases": {
                "records": len(cases),
                "with_source": sum(bool(mappings.get(f"case:{row.get('case_id')}")) for row in cases),
            },
            "inquiries": {"records": inquiry_count, "with_source": inquiry_count},
            "overtures": {"records": len(overtures), "with_source": len(overtures)},
            "rpr": {"records": len(rpr_rows), "with_source": len(rpr_rows)},
            "studies": {"records": study_count, "with_source": study_with_source},
        },
        "dedicated_inventory": {
            "count": len(inventory_list),
            "statuses": {
                status: sum(item["status"] == status for item in inventory_list)
                for status in sorted({item["status"] for item in inventory_list})
            },
        },
    }
    inventory_doc = {
        "schema_version": 1,
        "description": "Curated dedicated-PDF inventory. pdf_path is the stable external path beneath pcahistory.org; local_pdf_path is null because this repository does not vendor source PDF binaries.",
        "generated_from": [
            "index/sjc_official/roster.jsonl",
            "index/studies_pdf_manifest.json",
            "index/studies_pcahistory.json",
        ],
        "verification_policy": "Entries are source-indexed from the committed roster or manifest. The inventory does not claim that external binaries are vendored; content verification can be recorded per entry without changing source IDs.",
        "sources": inventory_list,
    }
    return registry, inventory_doc


def validate_registry(root: Path) -> list[str]:
    errors: list[str] = []
    registry_path = root / "index" / "source_registry.json"
    inventory_path = root / "index" / "dedicated_pdf_inventory.json"
    if not registry_path.exists():
        return [f"missing {registry_path.relative_to(root)}"]
    if not inventory_path.exists():
        return [f"missing {inventory_path.relative_to(root)}"]

    registry = load_json(registry_path)
    inventory = load_json(inventory_path)
    expected_registry, expected_inventory = build(root)
    if registry != expected_registry:
        errors.append("source_registry.json is stale; run scripts/build_source_registry.py --write")
    if inventory != expected_inventory:
        errors.append("dedicated_pdf_inventory.json is stale; run scripts/build_source_registry.py --write")

    if registry.get("schema_version") != 1:
        errors.append("source registry schema_version must be 1")
    if inventory.get("schema_version") != 1:
        errors.append("dedicated inventory schema_version must be 1")

    sources = registry.get("sources", [])
    source_map: dict[str, dict[str, Any]] = {}
    for source in sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
            errors.append(f"invalid source_id: {source_id!r}")
            continue
        if source_id in source_map:
            errors.append(f"duplicate source_id: {source_id}")
        source_map[source_id] = source
        kind = source.get("kind")
        if kind == "minutes":
            volume = source.get("volume")
            if not isinstance(volume, str) or not VOLUME_RE.fullmatch(volume):
                errors.append(f"minutes source {source_id} has invalid volume")
            if not source.get("pdf_path", "").lower().endswith(".pdf"):
                errors.append(f"minutes source {source_id} has no PDF path")
            if source.get("local_pdf_path") is not None:
                errors.append(f"minutes source {source_id} claims a local PDF")
        elif kind == "dedicated_pdf":
            url = source.get("url", "")
            if not PDF_URL_RE.fullmatch(url):
                errors.append(f"dedicated source {source_id} has invalid URL: {url}")
            if not source.get("pdf_path", "").lower().endswith(".pdf"):
                errors.append(f"dedicated source {source_id} has no PDF path")
            if source.get("local_pdf_path") is not None:
                errors.append(f"dedicated source {source_id} claims a local PDF")
        else:
            errors.append(f"source {source_id} has unknown kind {kind!r}")

    inventory_entries = inventory.get("sources", [])
    inventory_ids: set[str] = set()
    inventory_urls: set[str] = set()
    for entry in inventory_entries:
        source_id = entry.get("source_id")
        url = entry.get("url", "")
        if source_id in inventory_ids:
            errors.append(f"duplicate inventory source_id: {source_id}")
        inventory_ids.add(source_id)
        if source_id not in source_map:
            errors.append(f"inventory source is absent from registry: {source_id}")
        if not PDF_URL_RE.fullmatch(url):
            errors.append(f"inventory source has invalid URL: {url}")
        clean_url = canonical_pdf_url(url)
        if clean_url in inventory_urls:
            errors.append(f"duplicate dedicated PDF URL: {clean_url}")
        inventory_urls.add(clean_url)
        if entry.get("local_pdf_path") is not None:
            errors.append(f"inventory entry {source_id} claims a local PDF")
        if not entry.get("inventory_source"):
            errors.append(f"inventory entry {source_id} has no evidence source")

    if {
        source_id for source_id, source in source_map.items()
        if source.get("kind") == "dedicated_pdf"
    } != inventory_ids:
        errors.append("registry dedicated sources and inventory sources differ")

    record_sources = registry.get("record_sources", {})
    if not isinstance(record_sources, dict):
        errors.append("record_sources must be an object")
        record_sources = {}
    for record_id, ids in record_sources.items():
        if not isinstance(ids, list) or not ids:
            errors.append(f"record {record_id} has no source ID list")
            continue
        for source_id in ids:
            if source_id not in source_map:
                errors.append(f"record {record_id} references unknown source {source_id}")

    for relative in (
        "index/cases.jsonl",
        "index/sjc_official/roster.jsonl",
        "index/inquiries_located.json",
        "index/overture_bodies.jsonl",
        "index/studies_pages.json",
        "index/studies_pdf_manifest.json",
        "index/rpr",
    ):
        if not (root / relative).exists():
            errors.append(f"registry input is missing: {relative}")

    coverage = registry.get("coverage", {})
    for record_type in ("cases", "inquiries", "overtures", "rpr", "studies"):
        item = coverage.get(record_type)
        if not isinstance(item, dict):
            errors.append(f"missing coverage entry for {record_type}")
        elif item.get("records", 0) < item.get("with_source", 0):
            errors.append(f"coverage counts are inverted for {record_type}")
        elif item.get("records") != item.get("with_source"):
            errors.append(f"coverage is incomplete for {record_type}")

    case_records = load_jsonl(root / "index/cases.jsonl")
    for row in case_records:
        key = f"case:{row.get('case_id')}"
        if key not in record_sources:
            errors.append(f"case index row has no registry mapping: {key}")

    roster_urls = {
        canonical_pdf_url(row["pdf_url"])
        for row in load_jsonl(root / "index/sjc_official/roster.jsonl")
        if row.get("has_pdf") and row.get("pdf_url")
    }
    inventory_urls_clean = {canonical_pdf_url(url) for url in inventory_urls}
    missing_roster_urls = sorted(roster_urls - inventory_urls_clean)
    if missing_roster_urls:
        errors.append(f"{len(missing_roster_urls)} dedicated case PDFs from the roster are not inventoried")

    manifest = load_json(root / "index/studies_pdf_manifest.json")
    manifest_urls = set()
    for doc in manifest.get("documents", []):
        file = str(doc.get("pcahistory_file", ""))
        if not file.lower().endswith(".pdf"):
            continue
        url = doc.get("pcahistory_url") or f"https://www.pcahistory.org/pca/digest/studies/{file}"
        manifest_urls.add(canonical_pdf_url(url))
    missing_manifest_urls = sorted(manifest_urls - inventory_urls_clean)
    if missing_manifest_urls:
        errors.append(f"{len(missing_manifest_urls)} study PDFs from the manifest are not inventoried")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="validate committed data")
    parser.add_argument("--write", action="store_true", help="rewrite registry and inventory from indexes")
    args = parser.parse_args()
    if args.write:
        registry, inventory = build(args.root)
        (args.root / "index" / "source_registry.json").write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (args.root / "index" / "dedicated_pdf_inventory.json").write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print("wrote source registry and dedicated-PDF inventory")
        return 0
    errors = validate_registry(args.root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    registry = load_json(args.root / "index" / "source_registry.json")
    inventory = load_json(args.root / "index" / "dedicated_pdf_inventory.json")
    print(
        "source registry valid: "
        f"{len(registry.get('sources', []))} sources, "
        f"{len(registry.get('record_sources', {}))} record mappings; "
        f"{len(inventory.get('sources', []))} dedicated PDFs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
