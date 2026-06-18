#!/usr/bin/env python3
"""
20_markdown_index.py — render the structured index layers as MARKDOWN documents, so the
catalogues are portable the same way the minutes are: human-presentable, greppable, and
directly ingestible by another researcher (or their LLM) with no database tooling.

Generates (from pca_minutes.db, the single source of truth after 19_export):
  INDEX.md                 — corpus front door: volume table + links to everything
  index/OVERTURES.md       — the 3,075-overture catalogue, grouped by Assembly
  index/CASES.md           — the judicial-case index (number, parties, disposition, BCO cited)
  index/outlines/ga*.md    — per-volume structural table of contents

The SQLite DB stays as the optional full-text-query layer (see PORTABLE.md); these markdown
files are the presentable/ingestible layer, regenerated from the same data.

CLI:  20_markdown_index.py
"""
from __future__ import annotations
import json, os, re, sqlite3

ROOT = "/workspace"
DB = os.path.join(ROOT, "index", "pca_minutes.db")
OUT_IDX = os.path.join(ROOT, "index")
OUTLINES = os.path.join(OUT_IDX, "outlines")


def md_escape(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def ordinal(n):
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def vol_of(case_id):
    return case_id.split(":")[0] if case_id else None


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    os.makedirs(OUTLINES, exist_ok=True)

    vols = c.execute(
        "SELECT vol, ga_ordinal, year, COUNT(*) pages, MAX(pdf_page) maxp "
        "FROM pages GROUP BY vol ORDER BY ga_ordinal").fetchall()
    ord2vol = {str(v["ga_ordinal"]): v["vol"] for v in vols}   # case_id docket numbers aren't volumes

    # ---- INDEX.md (front door) ----
    L = ["# PCA General Assembly Minutes — Corpus Index", "",
         "All **52 volumes** of the Presbyterian Church in America *Minutes of the General "
         "Assembly*, **1973–2025**: cleaned, OCR-corrected, structurally-formatted markdown plus "
         "structured catalogues. Everything here is plain markdown — readable, greppable, and "
         "ingestible directly into your own research or tooling.", "",
         "## Catalogues", "",
         "- **[Overtures](OVERTURES.md)** — every overture to every Assembly (number, source "
         "presbytery, page). *\"Has the PCA considered this before?\"*",
         "- **[Judicial cases](CASES.md)** — SJC/CCB cases with parties, disposition, and the "
         "BCO provisions cited.",
         "- **[Per-volume outlines](outlines/)** — a structural table of contents for each volume.",
         "- **Full-text search:** a SQLite database (`pca_minutes.db`) indexes every page; see "
         "[../PORTABLE.md](../PORTABLE.md) for query recipes. The markdown above is generated from it.",
         "", "## Volumes", "",
         "| GA | Year | Minutes | Outline | Pages |", "|---:|---:|---|---|---:|"]
    for v in vols:
        stem = v["vol"]
        L.append(f"| {v['ga_ordinal']} | {v['year']} | [{stem}](../markdown/{stem}.md) "
                 f"| [outline](outlines/{stem}.md) | {v['pages']} |")
    open(os.path.join(OUT_IDX, "INDEX.md"), "w").write("\n".join(L) + "\n")

    # ---- OVERTURES.md ----
    L = ["# Overture Catalogue", "",
         "Every overture recorded across all General Assemblies, grouped by Assembly. "
         "Page numbers link to the volume; cite as `<volume> p.<pdf_page>`.", ""]
    rows = c.execute(
        "SELECT ga_ordinal, year, vol, number, source, pdf_page, context, title, pages, final_disposition "
        "FROM overtures ORDER BY ga_ordinal, number, pdf_page").fetchall()
    cur = None
    for r in rows:
        if r["ga_ordinal"] != cur:
            cur = r["ga_ordinal"]
            L += ["", f"## {ordinal(r['ga_ordinal'])} General Assembly ({r['year']})  ·  `{r['vol']}`", "",
                  "| Overture | Subject | Outcome | Source | Pages |", "|---:|---|---|---|---|"]
        pgs = (r["pages"].split(";") if r["pages"] else ([str(r["pdf_page"])] if r["pdf_page"] else []))
        pg = (f"[p.{pgs[0]}](../markdown/{r['vol']}.md)" + "".join(f", {p}" for p in pgs[1:])) if pgs else ""
        L.append(f"| {r['number']} | {md_escape(r['title'] or '')} | {md_escape(r['final_disposition'] or '')} "
                 f"| {md_escape(r['source'])} | {pg} |")
    open(os.path.join(OUT_IDX, "OVERTURES.md"), "w").write("\n".join(L) + "\n")
    n_ov = len(rows)

    # ---- CASES.md ----
    # case pages now come from DOCUMENT STRUCTURE (26_case_pages_structured) for the volumes that
    # pass acceptance; index/case_pages_map.json maps each case NUMBER to its structure page. Rows
    # whose volume hasn't been promoted yet are marked "extraction in progress" (no fabricated link).
    pages_map = {}
    pmap_path = os.path.join(ROOT, "index", "case_pages_map.json")
    if os.path.exists(pmap_path):
        pages_map = json.load(open(pmap_path))

    def _norm(raw):
        m = re.match(r"\D*(\d{2,4})-(\d+)([A-Za-z]?)", str(raw or ""))
        if not m:
            return None
        a, b, suf = m.group(1), int(m.group(2)), m.group(3).lower()
        if len(a) == 2:
            a = ("19" if int(a) >= 70 else "20") + a
        return f"{a}-{b:02d}{suf}"

    L = ["# Judicial Case Index", "",
         "Cases decided by the Standing Judicial Commission (SJC) and its predecessor the "
         "Committee on Judicial Business (CJB), grouped by Assembly. Includes disposition and "
         "the *Book of Church Order* provisions cited.", "",
         "Case numbers link to a full-text page (with opinions) re-extracted from the volume's "
         "structure. Volumes still being re-extracted are marked *extraction in progress*.", ""]
    rows = c.execute(
        "SELECT case_id, ga_ordinal, year, case_number, canonical_number, title, parties, "
        "disposition, bco_cited_as_s, pdf_page_start, body FROM cases "
        "ORDER BY CAST(ga_ordinal AS INT), pdf_page_start").fetchall()
    cur = None
    n_linked = 0
    for r in rows:
        if r["ga_ordinal"] != cur:
            cur = r["ga_ordinal"]
            L += ["", f"## {ordinal(r['ga_ordinal'])} General Assembly ({r['year']})", "",
                  "| Case | Parties / Title | Body | Disposition | BCO cited | Page |",
                  "|---|---|---|---|---|---|"]
        num = r["canonical_number"] or r["case_number"] or ""
        who = md_escape(r["parties"] or r["title"] or "")[:70]
        entry = pages_map.get(_norm(num) or "")
        if entry:
            numcell = f"[{md_escape(num)}](../cases/{entry['file']}.md)"
            pg = f"[full text](../cases/{entry['file']}.md)"
            n_linked += 1
        else:
            numcell = md_escape(num)
            pg = "_(extraction in progress)_"
        L.append(f"| {numcell} | {who} | {md_escape(r['body'] or '')} | "
                 f"{md_escape(r['disposition'] or '')} | {md_escape((r['bco_cited_as_s'] or '')[:40])} | {pg} |")
    open(os.path.join(OUT_IDX, "CASES.md"), "w").write("\n".join(L) + "\n")
    n_ca = len(rows)

    # ---- per-volume outlines ----
    n_out = 0
    for v in vols:
        stem = v["vol"]
        nodes = c.execute(
            "SELECT node_id, parent_id, type, label, title, number, source, pdf_page, seq "
            "FROM structure WHERE vol=? ORDER BY seq", (stem,)).fetchall()
        kids = {}
        for n in nodes:
            kids.setdefault(n["parent_id"], []).append(n)
        out = [f"# {stem} — Outline", "",
               f"Structural table of contents for the {ordinal(v['ga_ordinal'])} General Assembly "
               f"({v['year']}). Pages refer to `{stem}` PDF pages; full text: "
               f"[../../markdown/{stem}.md](../../markdown/{stem}.md).", ""]

        def walk(parent, depth):
            for n in kids.get(parent, []):
                pg = f" *(p.{n['pdf_page']})*" if n["pdf_page"] else ""
                if n["type"] == "overture":
                    label = f"Overture {n['number']}: {n['source'] or ''}".strip()
                else:
                    label = " ".join(x for x in [n["label"], n["title"]] if x)
                out.append(f"{'  ' * depth}- {md_escape(label)}{pg}")
                walk(n["node_id"], depth + 1)
        walk(None, 0)
        open(os.path.join(OUTLINES, f"{stem}.md"), "w").write("\n".join(out) + "\n")
        n_out += 1

    print(f"wrote INDEX.md, OVERTURES.md ({n_ov} overtures), CASES.md ({n_ca} cases), "
          f"and {n_out} per-volume outlines under index/outlines/")
    c.close()


if __name__ == "__main__":
    main()
