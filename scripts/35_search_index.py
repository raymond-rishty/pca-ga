#!/usr/bin/env python3
"""35_search_index.py — build app/search_index.json for the root catalogue search.

Combines the compact per-catalogue exports into one client-side search index:
  - RPR exceptions of substance      (index/rpr_search.json, written by 33_rpr_build)
  - Constitutional inquiries         (index/inquiries_search.json, written by 30_inquiry_pages)
  - Judicial cases                   (index/case_pages_map.json)
  - Overtures                        (from curated title/disposition/body metadata, with catalogue fallback)
Each record has display metadata plus explicit searchable fields. The browser search consumes
title, identifiers, assembly/year, parties, BCO references, topics, summaries, status, and
record context. CCB advice on overtures is deliberately NOT indexed (low value for the app
audience); the overtures themselves are.

Usage: 35_search_index.py [ROOT]   (default /workspace)
"""
from __future__ import annotations
import json, os, re, sys
from glob import glob
from pathlib import Path

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
APP = os.path.join(ROOT, "app")
CASE_SUMMARY_CHUNK_SIZE = 200


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
_CASE_PAGE = re.compile(r"\.\./cases/([^)]+\.md)")


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


def case_index_summaries():
    """Return the editorial case-index summary keyed by its rendered case page."""
    p = os.path.join(IDX, "CASES.md")
    if not os.path.exists(p):
        return {}
    out = {}
    for line in open(p, encoding="utf-8"):
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        match = _CASE_PAGE.search(line)
        summary = cells[3]
        if match and summary:
            out[match.group(1)] = summary
    return out


def main():
    rows = []
    case_summaries = {}

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

    # Build case_number -> BCO provisions lookup from cases.jsonl
    def _norm_num(n):
        mm = re.match(r'^(\d{4})-(\d+)([a-z]?)$', str(n))
        return f"{mm.group(1)}-{int(mm.group(2))}{mm.group(3)}" if mm else str(n)

    cases_jsonl_p = os.path.join(IDX, "cases.jsonl")
    case_provs: dict = {}       # norm_num -> list of "BCO X-Y" strings
    case_disps: dict = {}       # norm_num -> disposition string
    case_synopses: dict = {}    # norm_num -> editorial case headnote
    case_topics: dict = {}      # norm_num -> topics from the case metadata
    case_parties: dict = {}     # norm_num -> party/court names from the case metadata
    case_synopses_by_title: dict = {}
    case_synopses_by_file = case_index_summaries()
    # Prefer the canonical editorial/search layer when it has been built, while
    # retaining cases.jsonl as a portable fallback for older worktrees.
    taxonomy_rows = load_jsonl("judicial_cases.jsonl")
    taxonomy_by_key = {
        _norm_num(r["case_id"]): r for r in taxonomy_rows if r.get("case_id")
    }
    if os.path.exists(cases_jsonl_p):
        for line in open(cases_jsonl_p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            nn = c.get("case_number")
            if not nn:
                continue
            key = _norm_num(nn)
            bco = [f"BCO {b}" for b in (c.get("bco_cited_as") or [])
                   if re.match(r'^[\d]', b)]
            if bco:
                case_provs[key] = sorted(set(case_provs.get(key, []) + bco))
            if c.get("disposition"):
                case_disps[key] = c["disposition"]
            topics = [str(topic) for topic in (c.get("topics") or []) if topic]
            if topics:
                case_topics[key] = sorted(set(case_topics.get(key, []) + topics))
            parties = c.get("parties") or {}
            if isinstance(parties, dict):
                party_values = [parties.get(name) for name in (
                    "raw", "complainant_or_appellant", "respondent_or_court")]
            else:
                party_values = [parties]
            party_values = [str(value) for value in party_values if value]
            if party_values:
                case_parties[key] = sorted(set(case_parties.get(key, []) + party_values))
            if c.get("synopsis"):
                case_synopses[key] = c["synopsis"]
                case_synopses_by_title.setdefault(c.get("title"), c["synopsis"])

    cases = {}
    p = os.path.join(IDX, "case_pages_map.json")
    if os.path.exists(p):
        cases = json.load(open(p, encoding="utf-8"))
    seen = set()
    for num, c in cases.items():
        if c["file"] in seen:
            continue
        seen.add(c["file"])
        m = re.match(r"(\d{4})", num or "")
        # Gather provisions and disposition from all case numbers sharing this file
        file_provs: list = []
        file_disp = ""
        file_topics: list = []
        file_parties: list = []
        for n in c.get("numbers", [num]):
            key = _norm_num(n)
            file_provs.extend(case_provs.get(key, []))
            file_topics.extend(case_topics.get(key, []))
            file_parties.extend(case_parties.get(key, []))
            if not file_disp:
                file_disp = case_disps.get(key, "")
        tax_rows = [taxonomy_by_key[key] for key in dict.fromkeys(
            _norm_num(n) for n in c.get("numbers", [num])
        ) if key in taxonomy_by_key]
        tax = tax_rows[0] if tax_rows else taxonomy_by_key.get(_norm_num(num), {})
        tax_title = tax.get("title") or ""
        tax_summary = tax.get("summary") or ""
        tax_matter_type = tax.get("matter_type") or ""
        tax_dispositions = tax.get("final_dispositions") or []
        tax_provisions = [f"BCO {b}" for item in tax_rows
                          for b in (item.get("bco_provisions") or [])
                          if re.match(r"^[\d]", str(b))]
        tax_topics = [str(topic) for item in tax_rows
                      for topic in (item.get("topic_tags") or []) if topic]
        tax_identifiers = []
        for item in tax_rows:
            for value in (item.get("case_id"), item.get("legacy_case_id"), item.get("era_label")):
                if value and value not in tax_identifiers:
                    tax_identifiers.append(value)
            for value in item.get("minute_ids") or []:
                if value and value not in tax_identifiers:
                    tax_identifiers.append(value)
        title = tax_title or c.get("title") or num
        identifiers = [f"Case {n}" for n in c.get("numbers", [num])]
        identifiers.extend(
            f"Case {value}" if re.match(r"^\d{4}-", str(value)) else str(value)
            for value in tax_identifiers
        )
        identifiers = list(dict.fromkeys(identifiers))
        summary = tax_summary or case_synopses.get(_norm_num(num), "")
        if not summary:
            summary = next((case_synopses.get(_norm_num(n), "") for n in c.get("numbers", []) if case_synopses.get(_norm_num(n))), "")
        if not summary:
            summary = case_synopses_by_title.get(c.get("title"), "")
        if not summary:
            summary = case_synopses_by_file.get(f"{c['file']}.md", "")
        row = {"type": "Judicial case", "title": title,
               "sub": f"SJC/CJB case {tax.get('case_id') or num}",
               "identifier": identifiers[0] if identifiers else f"Case {num}",
               "identifiers": identifiers,
               "parties": sorted(set(file_parties)),
               "topics": sorted(set(file_topics + tax_topics)),
               "summary": summary,
               "provisions": sorted(set(file_provs + tax_provisions)),
               "year": int(m.group(1)) if m else None,
               "disposition": tax_dispositions[0] if tax_dispositions else file_disp,
               "case_id": tax.get("case_id"),
               "legacy_case_id": tax.get("legacy_case_id"),
               "era_id": tax.get("era_id"),
               "era_label": tax.get("era_label"),
               "minute_ids": tax.get("minute_ids") or [],
               "matter_type": tax_matter_type,
               "final_dispositions": tax_dispositions,
               "standard_of_review": tax.get("standard_of_review"),
               "standard_of_review_detail": tax.get("standard_of_review_detail"),
               "review_standards": tax.get("review_standards") or [],
               "classification_status": tax.get("classification_status"),
               "url": f"cases/{c['file']}.md"}
        if summary:
            case_summaries[num] = summary
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
    with open(os.path.join(APP, "search_index.json"), "w", encoding="utf-8") as output:
        json.dump(rows, output, ensure_ascii=False, separators=(",", ":"))
    for path in glob(os.path.join(APP, "case_summaries_*.json")):
        os.remove(path)
    summary_items = sorted(case_summaries.items())
    for part, offset in enumerate(range(0, len(summary_items), CASE_SUMMARY_CHUNK_SIZE), start=1):
        summary_chunk = dict(summary_items[offset:offset + CASE_SUMMARY_CHUNK_SIZE])
        with open(os.path.join(APP, f"case_summaries_{part}.json"), "w", encoding="utf-8") as output:
            json.dump(summary_chunk, output, ensure_ascii=False, separators=(",", ":"))
    from provision_catalogue import load_catalogue, provision_search_rows
    catalogue_path = os.path.join(IDX, "provision_catalogue.json")
    provision_rows = []
    if os.path.exists(catalogue_path):
        catalogue = load_catalogue(Path(catalogue_path))
        provision_rows = provision_search_rows(catalogue)
    with open(os.path.join(APP, "provision_search.json"), "w", encoding="utf-8") as output:
        json.dump(provision_rows, output, ensure_ascii=False, separators=(",", ":"))
    sz = os.path.getsize(os.path.join(APP, "search_index.json"))
    import collections
    by = collections.Counter(r["type"] for r in rows)
    print(f"[{ROOT}] app/search_index.json: {len(rows)} records {dict(by)} ({sz // 1024}KB); "
          f"{len(case_summaries)} case summaries in {part if case_summaries else 0} chunks; "
          f"{len(provision_rows)} provision search rows")


if __name__ == "__main__":
    main()
