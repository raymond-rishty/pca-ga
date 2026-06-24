#!/usr/bin/env python3
"""35_search_index.py — build app/search_index.json for the human-facing PWA.

Combines the compact per-catalogue exports into one client-side search index:
  - RPR exceptions of substance      (index/rpr_search.json, written by 33_rpr_build)
  - Constitutional inquiries         (index/inquiries_search.json, written by 30_inquiry_pages)
  - Judicial cases                   (index/case_pages_map.json)
  - Overtures                        (parsed from index/OVERTURES.md; each links to the verbatim minutes)
Each record: {type, title, sub, provisions, year, disposition, url} where url is relative to the
site root (the PWA lives at /app/ and links up to ../<url>). CCB advice on overtures is deliberately
NOT indexed (low value for the app audience); the overtures themselves are.

Usage: 35_search_index.py [ROOT]   (default /workspace)
"""
from __future__ import annotations
import json, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
APP = os.path.join(ROOT, "app")


def load(name):
    p = os.path.join(IDX, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []


_HEAD = re.compile(r"^##\s+.*General Assembly\s*\((\d{4})\)")
_LINK = re.compile(r"\]\(\.\./([^)#]+(?:#[^)]+)?)\)")   # first ../<path>[#anchor]
_PROV = re.compile(r"BCO\s+\d+-\d+(?:\.[0-9a-z]+)*", re.I)


def parse_overtures():
    """Parse index/OVERTURES.md into search records, each linked to the verbatim minutes page."""
    p = os.path.join(IDX, "OVERTURES.md")
    if not os.path.exists(p):
        return []
    out, year = [], None
    for line in open(p, encoding="utf-8"):
        h = _HEAD.match(line)
        if h:
            year = int(h.group(1))
            continue
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not cells[0].isdigit():   # skip header/separator/malformed
            continue
        num, subject, outcome, source, pages = cells[0], cells[1], cells[2], cells[3], cells[4]
        if not subject:
            continue
        m = _LINK.search(pages)
        url = m.group(1) if m else "index/OVERTURES.md"
        out.append({"type": "Overture", "title": subject,
                    "sub": f"Overture {num}" + (f" · {source}" if source else ""),
                    "provisions": sorted({m.split()[-1] for m in _PROV.findall(subject)}),
                    "year": year, "disposition": outcome, "url": url})
    return out


def main():
    rows = []

    for r in load("rpr_search.json"):
        rows.append({"type": "RPR exception", "title": f"{r['presbytery']}: {r['title']}",
                     "sub": f"{r['presbytery']} Presbytery" + (" · ⚖️ SJC" if r.get("sjc") else ""),
                     "provisions": r.get("provisions", []), "year": r.get("year"),
                     "disposition": r.get("disposition", ""), "url": r["url"]})

    for r in load("inquiries_search.json"):
        if r["type"] == "ccb-advice":
            continue   # CCB advice on overtures — not indexed for the app
        rows.append({"type": "Constitutional inquiry",
                     "title": r["title"], "sub": r.get("sub", ""), "provisions": r.get("provisions", []),
                     "year": r.get("year"), "disposition": r.get("disposition", ""), "url": r["url"]})

    rows.extend(parse_overtures())

    # Build case_number -> BCO provisions lookup from cases.jsonl
    def _norm_num(n):
        mm = re.match(r'^(\d{4})-(\d+)([a-z]?)$', str(n))
        return f"{mm.group(1)}-{int(mm.group(2))}{mm.group(3)}" if mm else str(n)

    cases_jsonl_p = os.path.join(IDX, "cases.jsonl")
    case_provs: dict = {}       # norm_num -> list of "BCO X-Y" strings
    case_disps: dict = {}       # norm_num -> disposition string
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
        for n in c.get("numbers", [num]):
            key = _norm_num(n)
            file_provs.extend(case_provs.get(key, []))
            if not file_disp:
                file_disp = case_disps.get(key, "")
        rows.append({"type": "Judicial case", "title": c.get("title") or num,
                     "sub": f"SJC/CJB case {num}",
                     "provisions": sorted(set(file_provs)),
                     "year": int(m.group(1)) if m else None,
                     "disposition": file_disp,
                     "url": f"cases/{c['file']}.md"})

    for r in load("studies_pages.json"):
        rows.append({"type": "Position paper",
                     "title": r.get("roster_topic") or r.get("topic") or r["title"],
                     "sub": r.get("kind_label", ""), "provisions": [],
                     "year": r.get("year"), "disposition": "",
                     "url": f"studies/{r['file']}"})

    os.makedirs(APP, exist_ok=True)
    json.dump(rows, open(os.path.join(APP, "search_index.json"), "w"), ensure_ascii=False,
              separators=(",", ":"))
    sz = os.path.getsize(os.path.join(APP, "search_index.json"))
    import collections
    by = collections.Counter(r["type"] for r in rows)
    print(f"[{ROOT}] app/search_index.json: {len(rows)} records {dict(by)} ({sz // 1024}KB)")


if __name__ == "__main__":
    main()
