#!/usr/bin/env python3
"""34_ga53_overtures.py — render the GA53 (2026) overture research layer to markdown.

For each of the 90 overtures before the 53rd General Assembly (2026), the source findings list the
PAST ACTIONS bearing on it (SJC/CJB cases, constitutional inquiries + CCB overture-advice, prior
overtures, RPR exceptions). Unlike the other catalogues, the GA53 findings are RESEARCH PROSE, not
derived from pca_minutes.db — so the source of truth is a set of per-overture markdown files, and this
renderer's job is layout + link-normalization + the catalogue index (it does not extract data).

Reads (from GA53_SRC, default /workspace/ga53 — the BUILD tree; the same source feeds both trees,
mirroring 20_markdown_index.py's build-tree pin):
  - overtures_full.tsv          : <num>\\t<targets>\\t<title>\\t<source>\\t<pdf_url>   (×90, ordering)
  - findings/O<NN>.md           : the research body for each overture
  - _header.md                  : the catalogue intro + thematic cluster map (optional)

Writes, mirroring CASES.md / cases/* and INQUIRIES.md / inquiries/*:
  - <ROOT>/ga53/O<NN>.md           : one page per overture (bearing past actions, deep-linked)
  - <ROOT>/index/GA53-OVERTURES.md : the catalogue, with the cluster map + a table linking each page

Bracket-label citations in the source ([OVERTURES.md], [CCB-OVERTURE-ADVICE.md], [cases/<f>.md], …)
are converted to real relative links into the published catalogues/pages; a case/inquiry/rpr page link
is only emitted if that file actually exists under <ROOT> (so 0 broken links).

Usage:  34_ga53_overtures.py [ROOT]      (ROOT defaults to /workspace)
"""
from __future__ import annotations
import os, re, sys, shutil, json

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
SRC = os.environ.get("GA53_SRC", "/workspace/ga53")
FIND = os.path.join(SRC, "findings")
OUT_PAGES = os.path.join(ROOT, "ga53")
OUT_IDX = os.path.join(ROOT, "index")

DEFAULT_UPDATED = "2026-06-20"   # initial publish; bump a per-overture date in ga53/updated.json when amended
try:
    UPDATED = json.load(open(os.path.join(SRC, "updated.json"), encoding="utf-8"))
except Exception:
    UPDATED = {}

# Overtures Committee (2026) recommendations to the Assembly (partial; only acted-on overtures).
try:
    COMMITTEE_RECS = {k: v for k, v in json.load(
        open(os.path.join(SRC, "committee_recs.json"), encoding="utf-8")).items() if not k.startswith("_")}
except Exception:
    COMMITTEE_RECS = {}

_REC_FULL = {"Affirmative": "Answer in the affirmative",
             "Affirmative as amended": "Answer in the affirmative, as amended",
             "Negative": "Answer in the negative",
             "Refer": "Refer"}


def rec_page_line(num):
    """Markdown line for the per-overture page (links a 'Reference to O<N>' to that overture)."""
    rec = COMMITTEE_RECS.get(num)
    if not rec:
        return ""
    m = re.match(r"Reference to (O\d+)$", rec)
    shown = f"Answer by reference to [{m.group(1)}]({m.group(1)}.md)" if m else _REC_FULL.get(rec, rec)
    return f"**Overtures Committee (2026) recommends:** {shown}"

CATALOGUES = {
    "OVERTURES.md": "OVERTURES.md",
    "CASES.md": "CASES.md",
    "cases.jsonl": "CASES.md",
    "INQUIRIES.md": "INQUIRIES.md",
    "CCB-OVERTURE-ADVICE.md": "CCB-OVERTURE-ADVICE.md",
    "RPR-BY-PROVISION.md": "RPR-BY-PROVISION.md",
    "RPR.md": "RPR.md",
}


def read_overtures():
    rows = []
    for ln in open(os.path.join(SRC, "overtures_full.tsv"), encoding="utf-8"):
        ln = ln.rstrip("\n")
        if not ln.strip():
            continue
        p = ln.split("\t")
        rows.append({"num": p[0], "n": int(p[0][1:]), "targets": p[1],
                     "title": p[2], "source": p[3], "url": p[4] if len(p) > 4 else ""})
    rows.sort(key=lambda r: r["n"])
    return rows


def normalize_links(body: str, page_rel: str) -> str:
    body = body.replace("[pca_minutes.db]", "the full-text database")

    def cat_sub(m):
        label = m.group(1)
        target = CATALOGUES.get(label)
        if not target:
            return m.group(0)
        shown = "CASES.md" if label == "cases.jsonl" else label
        return f"[{shown}]({page_rel}index/{target})"
    body = re.sub(r"\[(" + "|".join(re.escape(k) for k in CATALOGUES) + r")\]", cat_sub, body)

    def item_sub(m):
        rel = m.group(1)
        if os.path.exists(os.path.join(ROOT, rel)):
            stem = os.path.basename(rel)[:-3]
            return f"[{stem}]({page_rel}{rel})"
        return m.group(0)
    body = re.sub(r"\[((?:cases|inquiries|rpr)/[A-Za-z0-9_.\-]+\.md)\]", item_sub, body)

    body = re.sub(r"(\*\*PDF:\*\*\s+)(https?://\S+)", r"\1[\2](\2)", body)
    return body


def format_meta(body):
    """Put the header metadata lines into their own paragraphs (they otherwise glom into one)."""
    body = re.sub(r"\n(\*\*What it does:\*\*)", r"\n\n\1", body)
    body = re.sub(r"\n(\*\*Cites in its own grounds:\*\*)", r"\n\n\1", body)
    return re.sub(r"\n{3,}", "\n\n", body)


def render_pages(overs):
    os.makedirs(OUT_PAGES, exist_ok=True)
    n = 0
    for o in overs:
        src = os.path.join(FIND, f"{o['num']}.md")
        if not os.path.exists(src):
            continue
        body = open(src, encoding="utf-8").read().strip()
        body = re.sub(r"^##\s+O", "# O", body, count=1)
        rl = rec_page_line(o["num"])           # add the committee recommendation to the metadata block
        if rl:
            body = re.sub(r"(^# O\d+ .*\n)", lambda mm: mm.group(1) + rl + "\n", body, count=1)
        body = format_meta(normalize_links(body, "../"))
        title = (o["num"] + " \u2014 " + o["title"]).replace('"', "'")
        upd = UPDATED.get(o["num"], DEFAULT_UPDATED)
        fm = f'---\nlayout: ga53-overture\ntitle: "{title}"\nupdated: "{upd}"\n---\n\n'
        open(os.path.join(OUT_PAGES, f"{o['num']}.md"), "w", encoding="utf-8").write(fm + body + "\n")
        n += 1
    return n


def coverage(overs):
    secs = {"Judicial cases": 0, "Constitutional inquiries": 0,
            "Prior overtures": 0, "RPR exceptions": 0}
    enders = ["### Constitutional", "### Prior overtures", "### RPR", "### Note"]
    for o in overs:
        src = os.path.join(FIND, f"{o['num']}.md")
        if not os.path.exists(src):
            continue
        txt = open(src, encoding="utf-8").read()
        for key, head in [("Judicial cases", "### Judicial"),
                          ("Constitutional inquiries", "### Constitutional"),
                          ("Prior overtures", "### Prior overtures"),
                          ("RPR exceptions", "### RPR")]:
            i = txt.find(head)
            if i < 0:
                continue
            j = min([txt.find(e, i + 1) for e in enders if txt.find(e, i + 1) > 0] or [len(txt)])
            if re.search(r"^\s*-\s+", txt[i:j], re.M):
                secs[key] += 1
    return secs


def linkify_clusters(text: str) -> str:
    return re.sub(r"(?<![\w/\-])O(\d{1,2})\b(?!\])",
                  lambda m: f"[O{m.group(1)}](../ga53/O{m.group(1)}.md)", text)


def render_catalogue(overs):
    os.makedirs(OUT_IDX, exist_ok=True)
    cov = coverage(overs)
    L = ["# Overtures to the 53rd General Assembly (2026) — Bearing Past Actions", "",
         "For each of the **90 overtures** before the 53rd General Assembly, this catalogue links to a "
         "page listing the **past actions that bear on it**: SJC/CJB **judicial cases**, "
         "**constitutional inquiries** and CCB **overture/amendment advice**, **prior overtures**, and "
         "**RPR exceptions of substance** — drawn from this corpus (PCA GA minutes, 1973–2025) and each "
         "overture's own text on [pcaga.org](https://pcaga.org/resources/). Part of the "
         "[corpus index](INDEX.md).", "",
         "\U0001F4F1 **[Open the GA53 Overtures app](../ga53/app/)** \u2014 search the 90 "
         "proposals by provision, topic, or presbytery; installable and works offline.", "",
         f"*Coverage: judicial cases for {cov['Judicial cases']}/90 · inquiries/CCB advice for "
         f"{cov['Constitutional inquiries']}/90 · prior overtures for {cov['Prior overtures']}/90 · "
         f"RPR exceptions for {cov['RPR exceptions']}/90. \"None found\" is stated honestly where a "
         f"category turned up nothing.*", ""]
    hdr = os.path.join(SRC, "_header.md")
    if os.path.exists(hdr):
        h = open(hdr, encoding="utf-8").read()
        m = re.search(r"## Thematic clusters.*", h, re.S)
        if m:
            L += [linkify_clusters(m.group(0).split("\n---")[0].strip()), ""]
    L += ["## All 90 overtures", "",
          "| # | Subject | Targets | Source presbytery |", "|---:|---|---|---|"]
    for o in overs:
        L.append(f"| [{o['num']}](../ga53/{o['num']}.md) | {o['title'].replace('|','\\|')} "
                 f"| {o['targets'].replace('|','\\|')} | {o['source']} |")
    L += ["", "---", "", "*Caveats: the corpus ends at GA52 (2025); BCO sections were renumbered over "
          "the decades (topic searches mitigate this); inquiry/overture subject titles are partly "
          "machine-generated (~97% accurate). \"None found\" does not always mean nothing exists — only "
          "that nothing surfaced in this corpus.*"]
    open(os.path.join(OUT_IDX, "GA53-OVERTURES.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


def render_combined(overs):
    """One long, ingestible doc: header + every overture's (link-normalized) findings."""
    parts = ["---\nlayout: ga53-overture\ntitle: \"GA53 overtures (2026) — all 90\"\n---", ""]
    hdr = os.path.join(SRC, "_header.md")
    if os.path.exists(hdr):
        parts.append(open(hdr, encoding="utf-8").read().strip())
    for o in overs:
        src = os.path.join(FIND, f"{o['num']}.md")
        if not os.path.exists(src):
            continue
        parts.append(format_meta(normalize_links(open(src, encoding="utf-8").read().strip(), "../")))
        parts.append("---")
    open(os.path.join(OUT_PAGES, "GA53-OVERTURE-RESEARCH.md"), "w", encoding="utf-8").write(
        "\n\n".join(parts) + "\n")


def _parse_provs(targets):
    provs, kind = [], "BCO"
    for tok in re.split(r"[,\s]+", targets):
        u = tok.upper().strip("().")
        if u in ("BCO", "RAO"):
            kind = u; continue
        m = re.match(r"(BCO|RAO)?(\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)", tok)
        if m and re.search(r"\d", tok):
            if m.group(1):
                kind = m.group(1).upper()
            provs.append(f"{kind} {m.group(2)}")
    return provs


def _clusters():
    """Map O<NN> -> short cluster label, parsed from _header.md's cluster bullets (first match wins)."""
    out = {}
    hdr = os.path.join(SRC, "_header.md")
    if not os.path.exists(hdr):
        return out
    text = open(hdr, encoding="utf-8").read()
    m = re.search(r"## Thematic clusters.*", text, re.S)
    if not m:
        return out
    for line in m.group(0).split("\n"):
        b = re.match(r"\s*-\s+\*\*(.+?)\*\*\s*(.*)", line)
        if not b:
            continue
        label = re.sub(r"\s*\(.*?\)", "", b.group(1)).strip().rstrip(":")
        label = re.sub(r"\s*[—-]\s.*$", "", label).strip()
        for num in re.findall(r"\bO(\d{1,2})\b", b.group(2)):
            out.setdefault("O" + num, label)
    return out


def render_app(overs):
    """Build the standalone GA53 PWA: copy the shell + write search_index.json over the 90 overtures."""
    app = os.path.join(OUT_PAGES, "app")
    os.makedirs(app, exist_ok=True)
    shell = os.path.join(SRC, "app_shell")
    for f in ("index.html", "sw.js", "icon.svg", "icon-192.png", "icon-512.png", "icon-180.png", "icon-maskable-512.png"):
        src = os.path.join(shell, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(app, f))
    psw_src = os.path.join(SRC, "sw.js")
    psw_dst = os.path.join(OUT_PAGES, "sw.js")
    if os.path.exists(psw_src) and os.path.abspath(psw_src) != os.path.abspath(psw_dst):
        shutil.copy2(psw_src, psw_dst)
    njs_src = os.path.join(SRC, "notes.js")
    njs_dst = os.path.join(OUT_PAGES, "notes.js")
    if os.path.exists(njs_src) and os.path.abspath(njs_src) != os.path.abspath(njs_dst):
        shutil.copy2(njs_src, njs_dst)
    man_src = os.path.join(SRC, "manifest.json")
    man_dst = os.path.join(OUT_PAGES, "manifest.json")
    if os.path.exists(man_src) and os.path.abspath(man_src) != os.path.abspath(man_dst):
        shutil.copy2(man_src, man_dst)
    clusters = _clusters()
    recs = [{"num": o["num"], "title": o["title"], "source": o["source"],
             "provisions": _parse_provs(o["targets"]),
             "cluster": clusters.get(o["num"], "Other"),
             "url": o["num"] + ".md",
             **({"rec": COMMITTEE_RECS[o["num"]]} if o["num"] in COMMITTEE_RECS else {})}
            for o in overs]
    json.dump(recs, open(os.path.join(app, "search_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    return len(recs)


def main():
    overs = read_overtures()
    n = render_pages(overs)
    render_catalogue(overs)
    render_combined(overs)
    na = render_app(overs)
    print(f"[{ROOT}] wrote {n} GA53 pages + index/GA53-OVERTURES.md + ga53/GA53-OVERTURE-RESEARCH.md + ga53/app/ ({na} overtures)")


if __name__ == "__main__":
    main()
