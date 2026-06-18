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

    # CJB-era pages are STRUCTURE-FIRST (agent-located, verbatim-sliced; 27_cjb_pages). Their docket
    # numbers (e.g. 4-12/4-65) don't fit the table's scheme, so for CJB-era Assemblies we list the
    # located cases directly instead of the table's noisy rows.
    cjb_pages = {}
    cjb_path = os.path.join(ROOT, "index", "cjb_pages.json")
    if os.path.exists(cjb_path):
        cjb_by_ga = {}
        for p in json.load(open(cjb_path)):
            cjb_by_ga.setdefault(int(p["ga"]), []).append(p)
        cjb_pages = cjb_by_ga
    # stub pages: matters disposed without a published opinion (out of order / withdrawn / moot)
    stub_pages = {}
    stub_path = os.path.join(ROOT, "index", "stub_pages.json")
    if os.path.exists(stub_path):
        stub_pages = json.load(open(stub_path))

    L = ["# Judicial Case Index", "",
         "Cases decided by the Standing Judicial Commission (SJC) and its predecessor the "
         "Committee on Judicial Business (CJB), grouped by Assembly.", "",
         "This index is **structure-first**: every case listed links to a full-text page "
         "re-extracted verbatim from the volume (with its opinions). After the decided cases, an "
         "Assembly may list extra rows from the underlying case table: *decided at Nth GA* — the "
         "case was only listed here (deferred to a later Assembly, or cited from an earlier one) "
         "and links to where it was actually decided; *reference / no separate decision* — a "
         "cross-reference, roll-up, or out-of-order/withdrawn matter with no published decision; "
         "*not yet re-extracted* — the volume is still pending.", ""]
    rows = c.execute(
        "SELECT ga_ordinal, year, case_number, canonical_number, title, parties, "
        "disposition, has_dissent, pdf_page_start FROM cases "
        "ORDER BY CAST(ga_ordinal AS INT), pdf_page_start").fetchall()
    yr_of = {int(v["ga_ordinal"]): v["year"] for v in vols}
    # table metadata keyed by normalized number (disposition/dissent/page) + table rows per GA
    tmeta = {}
    byga = {}
    for r in rows:
        ga = int(r["ga_ordinal"]) if r["ga_ordinal"] is not None else 0
        byga.setdefault(ga, []).append(r)
        nn = _norm(r["canonical_number"] or r["case_number"] or "")
        if nn and nn not in tmeta:
            tmeta[nn] = {"disp": r["disposition"] or "", "dissent": r["has_dissent"] in (1, "1"),
                         "page": r["pdf_page_start"]}

    # invert the SJC structure-page map to unique pages grouped by GA (page == one decision)
    sjc_by_ga = {}
    seen_files = set()
    for v in pages_map.values():
        if v["file"] in seen_files:
            continue
        seen_files.add(v["file"])
        ga = int(re.match(r"ga(\d+)", v["vol"]).group(1))
        sjc_by_ga.setdefault(ga, []).append(v)

    # stub pages (disposed without an opinion), grouped by the GA where the matter was disposed
    stub_by_ga = {}
    for num, s in stub_pages.items():
        stub_by_ga.setdefault(int(s["ga"]), []).append({**s, "num": num})

    def _noise_label(r, year, vol):
        ny = _norm(r["canonical_number"] or r["case_number"] or "")
        meta = (r["title"] or "") + " " + (r["disposition"] or "")
        if ny and year and int(ny[:4]) < int(year) - 2:
            note = "_reference (decided earlier)_"
        elif re.search(r"(?i)withdrew|withdrawn|out of order|completed its work|no action|"
                       r"moot|abandoned|not received|carried over", meta):
            note = "_no separate decision_"
        else:
            note = "_no separate decision located_"
        return (f"{note} · [{vol} p.{r['pdf_page_start']}](../markdown/{vol}.md)"
                if vol and r["pdf_page_start"] else note)

    n_linked = 0
    for ga in sorted(set(byga) | set(cjb_pages) | set(sjc_by_ga) | set(stub_by_ga)):
        if ga <= 0:
            continue
        year = yr_of.get(ga) or (cjb_pages.get(ga, [{}])[0].get("year") if cjb_pages.get(ga) else "")
        L += ["", f"## {ordinal(ga)} General Assembly ({year})", "",
              "| Case | Parties / Title | Disposition | Page |", "|---|---|---|---|"]
        covered_nums = set()
        # 1) structure-first: the decided cases we extracted (CJB located + SJC structure pages)
        for p in sorted(cjb_pages.get(ga, []), key=lambda x: x["file"]):
            who = md_escape(p["parties"])[:80] + ("  ·  *dissent*" if p["has_dissent"] else "")
            numcell = f"[{md_escape(p['number'] or 'case')}](../cases/{p['file']}.md)"
            L.append(f"| {numcell} | {who} | {md_escape(p['disposition'])} | "
                     f"[full text](../cases/{p['file']}.md) |")
            n_linked += 1
        for p in sorted(sjc_by_ga.get(ga, []), key=lambda x: x["numbers"]):
            nums = p["numbers"]
            covered_nums.update(nums)
            disp = next((tmeta[n]["disp"] for n in nums if tmeta.get(n) and tmeta[n]["disp"]), "")
            diss = any(tmeta.get(n, {}).get("dissent") for n in nums)
            who = md_escape(p["title"])[:90] + ("  ·  *dissent*" if diss else "")
            numcell = f"[{md_escape('/'.join(nums))}](../cases/{p['file']}.md)"
            L.append(f"| {numcell} | {who} | {md_escape(disp)} | [full text](../cases/{p['file']}.md) |")
            n_linked += 1
        # stub pages: matters DISPOSED here without a published opinion (out of order / withdrawn)
        for s in sorted(stub_by_ga.get(ga, []), key=lambda x: x["num"]):
            covered_nums.add(s["num"])
            who = md_escape(s.get("parties") or "")[:80]
            L.append(f"| [{md_escape(s['num'])}](../cases/{s['file']}.md) | {who} | "
                     f"{md_escape(s['disposition'])} | [disposition](../cases/{s['file']}.md) |")
            n_linked += 1
        # 2) leftover table rows (not a decided/extracted case here) — honest noise/pending labels
        structured = ga in cjb_pages or ga in sjc_by_ga or ga in stub_by_ga
        for r in byga.get(ga, []):
            num = r["canonical_number"] or r["case_number"] or ""
            # some table rows have a BLANK number but cite a case in the title (a fragment of another
            # case's reasoning, e.g. "Case 2009-03: ... SJC Reasoning concluded ..."); recover the
            # number from the title so it forward-links to where that case was actually resolved.
            lookup = _norm(num)
            if not lookup:
                tm = re.search(r"(?i)\bcase\s+(\d{2,4}-\d{1,3}[a-z]?)", r["title"] or "")
                lookup = _norm(tm.group(1)) if tm else None
            if lookup and lookup in covered_nums:
                continue
            if ga in cjb_pages:               # CJB era is fully structure-first; skip table rows
                continue
            vol = ord2vol.get(str(ga))
            who = md_escape(r["parties"] or r["title"] or "")[:80]
            shown = md_escape(num) or (lookup or "")
            mapped = pages_map.get(lookup or "")
            stub = stub_pages.get(lookup or "")
            # where the case was actually resolved
            target = (int(re.match(r"ga(\d+)", mapped["vol"]).group(1)) if mapped
                      else int(stub["ga"]) if stub else None)
            if target is not None and target < ga:
                # resolved at an EARLIER Assembly than this one => the case was merely CITED here as
                # precedent (not introduced-and-deferred), so it is not a case OF this Assembly — omit.
                continue
            if mapped:
                # introduced here (or near) and decided at a LATER Assembly — a genuine deferral.
                pg = f"_decided at {ordinal(target)} GA_ · [full text](../cases/{mapped['file']}.md)"
            elif stub:
                pg = f"_disposed at {ordinal(target)} GA_ · [disposition](../cases/{stub['file']}.md)"
            elif ga in (1, 2):                # earliest Assemblies have no judicial-case section
                pg = (f"_no judicial cases in this volume_ · [{vol} p.{r['pdf_page_start']}]"
                      f"(../markdown/{vol}.md)" if vol and r["pdf_page_start"]
                      else "_no judicial cases in this volume_")
            elif structured:
                pg = _noise_label(r, year, vol)
            else:
                pg = (f"_not yet re-extracted_ · [{vol} p.{r['pdf_page_start']}](../markdown/{vol}.md)"
                      if vol and r["pdf_page_start"] else "_not yet re-extracted_")
            L.append(f"| {shown} | {who} | {md_escape(r['disposition'] or '')} | {pg} |")
    open(os.path.join(OUT_IDX, "CASES.md"), "w").write("\n".join(L) + "\n")
    n_ca = n_linked

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
