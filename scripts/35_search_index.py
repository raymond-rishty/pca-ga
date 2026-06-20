#!/usr/bin/env python3
"""35_search_index.py — build app/search_index.json for the human-facing PWA.

Combines the compact per-catalogue exports into one client-side search index:
  - RPR exceptions of substance      (index/rpr_search.json, written by 33_rpr_build)
  - Constitutional inquiries + CCB advice (index/inquiries_search.json, written by 30_inquiry_pages)
  - Judicial cases                   (index/case_pages_map.json)
Each record: {type, title, sub, provisions, year, disposition, url} where url is relative to the
site root (the PWA lives at /app/ and links up to ../<url>). Overtures (no per-item page) are linked
from the catalogue, not indexed here.

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


def main():
    rows = []

    for r in load("rpr_search.json"):
        rows.append({"type": "RPR exception", "title": f"{r['presbytery']}: {r['title']}",
                     "sub": f"{r['presbytery']} Presbytery" + (" · ⚖️ SJC" if r.get("sjc") else ""),
                     "provisions": r.get("provisions", []), "year": r.get("year"),
                     "disposition": r.get("disposition", ""), "url": r["url"]})

    for r in load("inquiries_search.json"):
        rows.append({"type": "CCB advice" if r["type"] == "ccb-advice" else "Constitutional inquiry",
                     "title": r["title"], "sub": r.get("sub", ""), "provisions": r.get("provisions", []),
                     "year": r.get("year"), "disposition": r.get("disposition", ""), "url": r["url"]})

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
        rows.append({"type": "Judicial case", "title": c.get("title") or num,
                     "sub": f"SJC/CJB case {num}", "provisions": [],
                     "year": int(m.group(1)) if m else None, "disposition": "",
                     "url": f"cases/{c['file']}.md"})

    os.makedirs(APP, exist_ok=True)
    json.dump(rows, open(os.path.join(APP, "search_index.json"), "w"), ensure_ascii=False,
              separators=(",", ":"))
    sz = os.path.getsize(os.path.join(APP, "search_index.json"))
    import collections
    by = collections.Counter(r["type"] for r in rows)
    print(f"[{ROOT}] app/search_index.json: {len(rows)} records {dict(by)} ({sz // 1024}KB)")


if __name__ == "__main__":
    main()
