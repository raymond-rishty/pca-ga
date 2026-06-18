#!/usr/bin/env python3
"""
bco_concordance.py — build a BCO amendment index + section-number crosswalk from
the PCA Historical Center change log (pcahistory.org/bco/pca/pcachanges.html),
and resolve an old citation (section, year) to its modern section number.

Outputs:
  index/bco_changes.jsonl       one row per year: which BCO sections were amended
  (reads index/bco_renumberings.jsonl — the curated structural-renumbering crosswalk)

CLI:
  bco_concordance.py build            # parse the saved HTML -> bco_changes.jsonl
  bco_concordance.py resolve 24-5 1991   # -> modern section number + the events applied
  bco_concordance.py amended 24       # years chapter 24 (any section) was amended
"""
from __future__ import annotations
import json, os, re, sys

ROOT = "/workspace"
SRC_HTML = "/tmp/pcachanges.html"
CHANGES = os.path.join(ROOT, "index", "bco_changes.jsonl")
RENUM = os.path.join(ROOT, "index", "bco_renumberings.jsonl")


def ga_for_year(y):
    return y - 1972 if y <= 2019 else y - 1973  # no GA in 2020


def _visible_text():
    h = open(SRC_HTML, encoding="utf-8", errors="replace").read()
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    h = (h.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"'))
    return re.sub(r"[ \t\r\n]+", " ", h)


SEC = re.compile(r"\b\d{1,2}-\d{1,2}(?:[.\-]\w+)*\b|\bChapter\s+\d+\b|\bChapters?\s+\d+\s*&\s*\d+\b|\bAppendix\s+\w+\b|\bPreface\b", re.I)
RENUM_KW = re.compile(r"renumber|relett|\bnow\b|became|combined|add(?:ing|ed)?\s+(?:a\s+)?new", re.I)


def build():
    txt = _visible_text()
    # isolate content between the intro and the copyright footer
    m = re.search(r"years noted\.?(.*?)(?:©|&copy;|PCA Historical Center, 123)", txt, re.S | re.I)
    body = m.group(1) if m else txt
    # split into year blocks
    parts = re.split(r"\b(19[7-9]\d|20[0-2]\d)\b\s*-", body)
    rows = []
    for i in range(1, len(parts), 2):
        year = int(parts[i]); content = parts[i + 1].strip()
        # split BCO / RAO / SJC / Bylaws segments; we keep the BCO segment
        seg = re.split(r"\bRAO\b|\bSJC Manual\b|\bOMSJC\b|\bCorporate Bylaws\b|\bSJC\b", content)[0]
        seg = re.sub(r"^\s*BCO\b", "", seg, flags=re.I).strip(" .;")
        if re.search(r"no revisions adopted|minor changes proposed|see the pamphlet", seg, re.I):
            sections = []
        else:
            sections = sorted({s.strip() for s in SEC.findall(seg)})
        rows.append({
            "year": year, "ga": ga_for_year(year),
            "bco_sections": sections,
            "bco_raw": re.sub(r"\s+", " ", seg)[:600],
            "renumbering": bool(RENUM_KW.search(seg)),
        })
    rows.sort(key=lambda r: r["year"])
    with open(CHANGES, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    yrs = [r["year"] for r in rows]
    print(f"[build] {len(rows)} years parsed ({min(yrs)}-{max(yrs)}) -> {CHANGES}")
    print(f"        years with a BCO renumbering note: "
          + ", ".join(str(r['year']) for r in rows if r['renumbering']))
    return rows


def load_renumberings():
    out = []
    if os.path.exists(RENUM):
        for l in open(RENUM):
            l = l.strip()
            if l:
                out.append(json.loads(l))
    out.sort(key=lambda e: e["adopted_year"])
    return out


def resolve(section, year):
    """Map a citation (section, year-of-citation) forward to its modern number by
    applying every renumbering event adopted AFTER that year for the same chapter."""
    chapter = section.split("-")[0]
    cur = section
    trail = []
    for e in load_renumberings():
        if e["adopted_year"] <= year or e["chapter"] != chapter:
            continue
        hit = next((m for m in e.get("mappings", []) if m["from"] == cur), None)
        if hit:
            trail.append(f"{cur}->{hit['to']} (adopted {e['adopted_year']}, GA{e['ga']})")
            cur = hit["to"]
        elif not e.get("mappings"):
            trail.append(f"[chapter {chapter} had an unmapped {e['kind']} in {e['adopted_year']} "
                         f"(status={e['status']}) — verify]")
    return cur, trail


def amended(chapter):
    rows = [json.loads(l) for l in open(CHANGES) if l.strip()]
    hits = [r["year"] for r in rows
            if any(s.split("-")[0] == str(chapter) for s in r["bco_sections"])]
    print(f"BCO chapter {chapter} amended in: {hits}")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    if cmd == "build":
        build()
    elif cmd == "resolve":
        sec, yr = sys.argv[2], int(sys.argv[3])
        cur, trail = resolve(sec, yr)
        print(f"BCO {sec} (as cited in {yr})  ->  modern BCO {cur}")
        for t in trail:
            print("   applied:", t)
        if not trail:
            print("   (no renumbering events after that year for this chapter — number unchanged)")
    elif cmd == "amended":
        amended(sys.argv[2])


if __name__ == "__main__":
    main()
