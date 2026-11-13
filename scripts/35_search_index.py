#!/usr/bin/env python3
"""35_search_index.py — build app/search_index.json for the root catalogue search.

Combines the compact per-catalogue exports into one client-side search index:
  - RPR exceptions of substance      (index/rpr_search.json, written by 33_rpr_build)
  - Constitutional inquiries         (index/inquiries_search.json, written by 30_inquiry_pages)
  - Judicial cases                   (data/cases/records/judicial_cases.jsonl)
  - Overtures                        (from curated title/disposition/body metadata, with catalogue fallback)
Each record has display metadata plus explicit searchable fields. The browser search consumes
title, identifiers, assembly/year, parties, BCO references, topics, summaries, status, and
record context. CCB advice on overtures is deliberately NOT indexed (low value for the app
audience); the overtures themselves are.

Usage: 35_search_index.py [ROOT]   (default /workspace)
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
from atomic_output import write_text_atomic

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
APP = os.path.join(ROOT, "app")
CASE_RECORDS = os.path.join(ROOT, "data", "cases", "records")


def load(name):
    p = os.path.join(IDX, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


def load_jsonl(name):
    p = os.path.join(IDX, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


_HEAD = re.compile(r"^##\s+.*General Assembly\s*\((\d{4})\)")
_LINK = re.compile(r"\]\(\.\./([^)#]+(?:#[^)]+)?)\)")   # first ../<path>[#anchor]
_PROV = re.compile(r"BCO\s+\d+-\d+(?:\.[0-9a-z]+)*", re.I)


def parse_overture_catalogue():
    """Legacy name retained for callers; projection lives in one shared helper."""
    from overture_catalogue import search_rows
    return search_rows(Path(ROOT) / "index")


def curated_overtures():
    """Legacy name retained for callers; projection lives in one shared helper."""
    from overture_catalogue import search_rows
    return search_rows(Path(ROOT) / "index")


def overture_records():
    """Use the same page-keyed overture projection as the provision catalogue."""
    return curated_overtures() or parse_overture_catalogue()


def case_page_summary(root, file_stem):
    """Use the opening facts paragraphs when a case has no catalogue summary."""
    path = Path(root) / "cases" / f"{file_stem}.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"^###\s+(?:I\.\s+)?(?:A\s+)?Summary of the Facts\s*$\n(.*?)(?=^###?\s|\Z)",
        text,
        flags=re.I | re.M | re.S,
    )
    if not match:
        return ""
    paragraphs = []
    for block in re.split(r"\n\s*\n", match.group(1)):
        block = re.sub(r"<!--.*?-->", " ", block, flags=re.S)
        block = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", block)
        block = re.sub(r"[*_`>#]", "", block)
        block = re.sub(r"\s+", " ", block).strip()
        if block:
            paragraphs.append(block)
        if len(paragraphs) == 2:
            break
    return " ".join(paragraphs)


def main():
    rows = []

    for r in load("rpr_search.json"):
        exception = re.search(r"__(\d+)\.md$", r["url"])
        identifier = f"Exception {int(exception.group(1))}" if exception else ""
        rows.append({"type": "RPR exception", "title": f"{r['presbytery']}: {r['title']}",
                     "sub": f"{r['presbytery']} Presbytery" + (" · ⚖️ SJC" if r.get("sjc") else ""),
                     "identifier": identifier,
                     "identifiers": [identifier] if identifier else [],
                     "topics": [r["title"]],
                     "provisions": r.get("provisions", []), "year": r.get("year"),
                     "disposition": r.get("disposition", ""), "url": r["url"]})

    for r in load("inquiries_search.json"):
        if r["type"] == "ccb-advice":
            continue   # CCB advice on overtures — not indexed for the app
        inquiry = re.search(r"__ci(\d+)\.md$", r["url"])
        identifier = f"CCB inquiry {int(inquiry.group(1))}" if inquiry else ""
        rows.append({"type": "Constitutional inquiry",
                     "title": r["title"], "sub": r.get("sub", ""),
                     "identifier": identifier,
                     "identifiers": [identifier] if identifier else [],
                     "topics": [r["title"]], "provisions": r.get("provisions", []),
                     "year": r.get("year"), "disposition": r.get("disposition", ""), "url": r["url"]})

    rows.extend(overture_records())

    taxonomy_path = Path(CASE_RECORDS) / "judicial_cases.jsonl"
    if taxonomy_path.exists():
        with taxonomy_path.open(encoding="utf-8") as source:
            taxonomy_rows = [json.loads(line) for line in source if line.strip()]
    else:
        taxonomy_rows = []

    # The canonical catalogue supplies case metadata and the docket aliases
    # represented on each full-text page.
    taxonomy_by_page: dict[str, list[dict]] = {}
    for item in taxonomy_rows:
        if item.get("case_page"):
            taxonomy_by_page.setdefault(item["case_page"], []).append(item)

    for file_stem in sorted(taxonomy_by_page):
        tax_rows = taxonomy_by_page.get(file_stem, [])
        tax = tax_rows[0] if tax_rows else {}
        page_numbers = list(dict.fromkeys(
            number for item in tax_rows
            for number in item.get("page_case_numbers", []) if number
        ))
        if not page_numbers:
            page_numbers = [item.get("case_id") for item in tax_rows if item.get("case_id")]
        identifiers = [f"Case {number}" for number in page_numbers]
        for item in tax_rows:
            for value in (item.get("case_id"), item.get("legacy_case_id"),
                          item.get("roster_id"), item.get("era_label")):
                if value:
                    identifiers.append(f"Case {value}" if re.match(r"^\d{4}-", str(value)) else str(value))
            identifiers.extend(item.get("minute_ids") or [])
        identifiers = list(dict.fromkeys(identifiers))
        title = tax.get("title") or file_stem
        tax_dispositions = list(dict.fromkeys(
            disposition for item in tax_rows
            for disposition in (item.get("final_dispositions") or []) if disposition
        ))
        tax_provisions = list(dict.fromkeys(
            f"BCO {provision}"
            for item in tax_rows for provision in (item.get("bco_provisions") or [])
            if re.match(r"^[\d]", str(provision))
        ))
        tax_topics = list(dict.fromkeys(
            str(topic) for item in tax_rows for topic in (item.get("topic_tags") or []) if topic
        ))
        tax_parties = []
        for item in tax_rows:
            parties = item.get("parties") or {}
            if isinstance(parties, dict):
                values = [parties.get(key) for key in (
                    "raw", "complainant_or_appellant", "respondent_or_court")]
            else:
                values = [parties]
            tax_parties.extend(str(value) for value in values if value)
        tax_parties = sorted(set(tax_parties))
        summary = next((item.get("summary") for item in tax_rows if item.get("summary")), "")
        if not summary:
            summary = case_page_summary(ROOT, file_stem)
        case_id = tax.get("case_id") or (page_numbers[0] if page_numbers else "")
        page_year = re.search(r"ga\d+_(\d{4})", str(file_stem))
        year = tax.get("decision_year") or (int(page_year.group(1)) if page_year else None)
        row = {"type": "Judicial case", "title": title,
               "sub": f"SJC/CJB case {case_id}" if case_id else "Judicial case",
               "identifier": identifiers[0] if identifiers else "Judicial case",
               "identifiers": identifiers,
               "parties": tax_parties,
               "topics": tax_topics,
               "summary": summary,
               "provisions": tax_provisions,
               "year": year,
               "disposition": tax_dispositions[0] if tax_dispositions else "",
               "case_id": tax.get("case_id"),
               "legacy_case_id": tax.get("legacy_case_id"),
               "era_id": tax.get("era_id"),
               "era_label": tax.get("era_label"),
               "minute_ids": tax.get("minute_ids") or [],
               "matter_type": tax.get("matter_type"),
               "final_dispositions": tax_dispositions,
               "standard_of_review": tax.get("standard_of_review"),
               "standard_of_review_detail": tax.get("standard_of_review_detail"),
               "review_standards": tax.get("review_standards") or [],
               "classification_status": tax.get("classification_status"),
               "url": f"cases/{file_stem}.md"}
        rows.append(row)

    for r in load("studies_pages.json"):
        topic = r.get("roster_topic") or r.get("topic") or r["title"]
        rows.append({"type": "Position paper",
                     "title": topic,
                     "sub": r.get("kind_label", ""), "provisions": [],
                     "identifier": topic,
                     "identifiers": [topic],
                     "topics": [topic],
                     "year": r.get("year"), "disposition": "",
                     "url": f"studies/{r['file']}"})

    os.makedirs(APP, exist_ok=True)
    write_text_atomic(Path(APP) / "search_index.json",
                      json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    from provision_catalogue import load_catalogue, provision_search_rows
    catalogue_path = os.path.join(IDX, "provision_catalogue.json")
    provision_rows = []
    if os.path.exists(catalogue_path):
        catalogue = load_catalogue(Path(catalogue_path))
        provision_rows = provision_search_rows(catalogue)
    write_text_atomic(Path(APP) / "provision_search.json",
                      json.dumps(provision_rows, ensure_ascii=False, separators=(",", ":")))
    sz = os.path.getsize(os.path.join(APP, "search_index.json"))
    import collections
    by = collections.Counter(r["type"] for r in rows)
    print(f"[{ROOT}] app/search_index.json: {len(rows)} records {dict(by)} ({sz // 1024}KB); "
          f"{len(provision_rows)} provision search rows")


if __name__ == "__main__":
    main()
