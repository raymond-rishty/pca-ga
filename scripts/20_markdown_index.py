#!/usr/bin/env python3
"""
20_markdown_index.py — render the minutes-volume index, catalogue layers, and outlines as
portable MARKDOWN documents: human-presentable, greppable, and directly ingestible by
another researcher (or their LLM) with no database tooling.

Generates the minutes volume, overture, and outline views from the portable SQLite
database:
  INDEX.md                 — minutes index: volume cards linking to minutes and outlines
  index/OVERTURES.md       — the 3,075-overture catalogue, grouped by Assembly
  index/outlines/ga*.md    — per-volume structural table of contents

The SQLite database is built by Gradle task `buildMinutesDatabase`.

CLI:  20_markdown_index.py
"""
from __future__ import annotations
import json, os, re, sqlite3

ROOT = os.environ.get("PCA_GA_ROOT", os.getcwd())
OUT_IDX = os.path.join(ROOT, "index")
OUTLINES = os.path.join(OUT_IDX, "outlines")
DB = os.path.join(ROOT, "index", "pca_minutes.db")

def md_escape(s):
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def ordinal(n):
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def vol_of(case_id):
    return case_id.split(":")[0] if case_id else None


_anchor_cache = {}


def page_anchor(vol, page):
    """Map a volume's pdf_page -> the in-file anchor id (`<a id="ga<ord>-pN">`) that precedes that
    page's marker, so a "p.N" reference can deep-link to the page. The anchor uses the PRINTED page
    (or pdf_page when printed is null) while callers pass the pdf_page, hence the lookup."""
    if vol not in _anchor_cache:
        amap = {}
        p = os.path.join(ROOT, "markdown", vol + ".md")
        if os.path.exists(p):
            last = None
            for line in open(p, encoding="utf-8"):
                ma = re.match(r'\s*<a id="(ga\d+-p[0-9A-Za-z]+)">', line)
                if ma:
                    last = ma.group(1)
                mp = re.search(r"pdf_page=(\d+)", line)
                if mp and last:
                    amap.setdefault(int(mp.group(1)), last)
        _anchor_cache[vol] = amap
    try:
        return _anchor_cache[vol].get(int(page))
    except (TypeError, ValueError):
        return None


def page_link(vol, page, label=None):
    a = page_anchor(vol, page)
    return f"[{label or ('p.' + str(page))}](../markdown/{vol}.md{'#' + a if a else ''})"


def outline_page_link(vol, page, label=None):
    a = page_anchor(vol, page)
    return f"[{label or ('p.' + str(page))}](../../markdown/{vol}.html{'#' + a if a else ''})"


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    os.makedirs(OUTLINES, exist_ok=True)

    vols = c.execute(
        "SELECT vol, ga_ordinal, year, COUNT(*) pages, MAX(pdf_page) maxp "
        "FROM pages GROUP BY vol ORDER BY ga_ordinal").fetchall()
    ord2vol = {str(v["ga_ordinal"]): v["vol"] for v in vols}   # case_id docket numbers aren't volumes

    # ---- INDEX.md (minutes front door) ----
    L = [
        "---",
        "layout: default",
        "title: Minutes Index",
        "description: Browse 52 published volumes of the PCA General Assembly minutes (1973–2025), with a structural outline for each volume and full-text search.",
        "permalink: /index/INDEX.html",
        "---",
        "",
        "# PCA General Assembly Minutes — Minutes Index", "",
         "Browse the **52 published volumes** of the Presbyterian Church in America *Minutes "
         "of the General Assembly*, **1973–2025**. Open a volume to read its cleaned, "
         "OCR-corrected text, or follow its outline to navigate the meeting record.", "",
         "## Volumes", "",
         '<div class="minutes-volume-grid" role="list" aria-label="Published General Assembly volumes">']
    for v in vols:
        stem = v["vol"]
        L += [
            '  <article class="minutes-volume-card" role="listitem">',
            f'    <p class="minutes-volume-card__assembly">General Assembly {v["ga_ordinal"]}</p>',
            f'    <h3>{v["year"]}</h3>',
            f'    <p class="minutes-volume-card__pages">{v["pages"]} pages</p>',
            '    <div class="minutes-volume-card__links">',
            f"      <a class=\"minutes-volume-card__primary\" href=\"{{{{ '/markdown/{stem}.html' | relative_url }}}}\">Read minutes</a>",
            f"      <a href=\"{{{{ '/index/outlines/{stem}.html' | relative_url }}}}\">Outline</a>",
            '    </div>',
            '  </article>',
        ]
    L.append('</div>')
    L += [
        "",
        "## Full-text search",
        "",
        "A SQLite database named pca_minutes.db indexes every page of the Minutes. See "
        "[../PORTABLE.md](../PORTABLE.md) for query recipes.",
    ]
    open(os.path.join(OUT_IDX, "INDEX.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

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
        pg = ", ".join(page_link(r["vol"], p.strip()) for p in pgs if p.strip())
        L.append(f"| {r['number']} | {md_escape(r['title'] or '')} | {md_escape(r['final_disposition'] or '')} "
                 f"| {md_escape(r['source'])} | {pg} |")
    open(os.path.join(OUT_IDX, "OVERTURES.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    n_ov = len(rows)

    # ---- per-volume outlines ----
    n_out = 0
    for v in vols:
        stem = v["vol"]
        nodes = c.execute(
            "SELECT node_id, parent_id, type, label, title, number, source, pdf_page, printed_page, seq "
            "FROM structure WHERE vol=? ORDER BY seq", (stem,)).fetchall()
        kids = {}
        for n in nodes:
            kids.setdefault(n["parent_id"], []).append(n)
        out = [f"# {stem} — Outline", "",
               f"Structural table of contents for the {ordinal(v['ga_ordinal'])} General Assembly "
               f"({v['year']}). Page references use printed document pages where available; "
               f"full text: "
               f"[../../markdown/{stem}.html](../../markdown/{stem}.html).", ""]

        def walk(parent, depth):
            for n in kids.get(parent, []):
                pg = ""
                if n["pdf_page"]:
                    shown_page = n["printed_page"] or n["pdf_page"]
                    pg = f" *({outline_page_link(stem, n['pdf_page'], f'p.{shown_page}')})*"
                if n["type"] == "overture":
                    label = f"Overture {n['number']}: {n['source'] or ''}".strip()
                elif n["type"] == "case":
                    label = ", ".join(x for x in [n["label"], n["title"]] if x)
                else:
                    label = " ".join(x for x in [n["label"], n["title"]] if x)
                out.append(f"{'  ' * depth}- {md_escape(label)}{pg}")
                walk(n["node_id"], depth + 1)
        walk(None, 0)
        open(os.path.join(OUTLINES, f"{stem}.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
        n_out += 1

    print(f"wrote INDEX.md, OVERTURES.md ({n_ov} overtures), "
          f"and {n_out} per-volume outlines under index/outlines/")
    c.close()


if __name__ == "__main__":
    main()
