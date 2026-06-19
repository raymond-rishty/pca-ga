#!/usr/bin/env python3
"""33_rpr_build.py — build the Review of Presbytery Records (RPR) catalogue from the per-volume
extractions (index/rpr/<vol>.json, GA18-52) + floor-action provenance (index/rpr_floor_actions.json).

Steps: normalize presbytery names -> thread each exception of substance across years (by explicit
YYYY-NN id where present, else (presbytery, minute-date, provisions)) -> render markdown:
  index/RPR.md              hub: corpus stats, most-cited provisions, per-presbytery index, by-year
  index/RPR-BY-PROVISION.md  cross-reference: each BCO/RAO/WCF provision -> who/when/outcome
  rpr/<presbytery>.md        per presbytery: every exception with its multi-year lifecycle + deep-links

Usage: 33_rpr_build.py [ROOT]   (ROOT defaults to /workspace)
"""
from __future__ import annotations
import glob, json, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
IDX = os.path.join(ROOT, "index")
OUT = os.path.join(ROOT, "rpr")

# presbytery-name normalization: OCR fixes / abbreviations / renames (conservative)
CORR = {
    "korean sw orange county": "Korean Southwest Orange County",
    "korean southwestern": "Korean Southwest",
    "suncoast flo rida": "Suncoast Florida",
    "sioux lands": "Siouxlands",
    "highlands western carolina": "Highlands",
}


def ordinal(n):
    n = int(n)
    return f"{n}{'th' if 10<=n%100<=20 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"


def canon_presb(name):
    if not name:
        return None
    n = re.sub(r"\s+", " ", name).strip()
    n = re.sub(r"^(the\s+)?presbytery of (the\s+)?", "", n, flags=re.I)
    n = re.sub(r"\s*\(.*?\)\s*$", "", n)            # drop trailing "(Western Carolina)"
    n = n.rstrip(" .,")
    key = re.sub(r"[^a-z ]", "", n.lower()).strip()
    if key in CORR:
        return CORR[key]
    return n.title() if (n.islower() or n.isupper()) else n


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def md_escape(s):
    return re.sub(r"\s+", " ", (s or "")).replace("|", "\\|").strip()


def strip_md(s):
    s = re.sub(r"<a id=[^>]*>|</a>|<!--.*?-->", "", s or "")
    return re.sub(r"\s+", " ", re.sub(r"[*_`>#]+", "", s)).strip()


def printed_page(anchor):
    m = re.search(r"-p(\w+)$", anchor or "")
    return m.group(1) if m else "?"


def deeplink(vol, anchor, rel="../markdown"):
    if not anchor:
        return f"{vol}"
    return f"[{vol} p.{printed_page(anchor)}]({rel}/{vol}.md#{anchor})"


def norm_dates(s):
    return re.sub(r"[^0-9]", "", s or "")[:8]        # crude date key for tuple-threading


_md_cache = {}
_DROP = re.compile(r'^\s*(<a id=|<!--|#*\s*\d*\s*MINUTES OF THE GENERAL ASSEMBLY|JOURNAL\b|APPENDI)')
# a bled-in journal minute header ("37-28 Report of the Standing Judicial Commission", "36-12 Committee
# on ...") — when a slice overruns into the next minute, stop there so its content doesn't pollute.
_MINUTE = re.compile(r'^\s*\*{0,2}\d{1,2}-\d{1,3}\s+(Report|Partial Report|Committee|[A-Z][a-z]+ (Report|Committee))')


def slice_md(vol, a, b):
    """Verbatim slice of a volume's markdown (1-based inclusive), dropping page-break anchors/comments
    and running headers, and stopping if the slice overruns into the next journal minute."""
    if vol not in _md_cache:
        p = os.path.join(ROOT, "markdown", vol + ".md")
        _md_cache[vol] = open(p, encoding="utf-8").read().split("\n") if os.path.exists(p) else []
    lines = _md_cache[vol]
    if not (a and b):
        return ""
    out = []
    for k, ln in enumerate(lines[int(a) - 1:int(b)]):
        if k > 1 and _MINUTE.match(ln):
            break
        if not _DROP.match(ln):
            out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def main():
    recs = []
    for f in sorted(glob.glob(os.path.join(IDX, "rpr", "*.json"))):
        recs += json.load(open(f))
    floor = json.load(open(os.path.join(IDX, "rpr_floor_actions.json")))

    dropped = sum(1 for r in recs if not r.get("presbytery"))
    for r in recs:
        r["canon"] = canon_presb(r.get("presbytery"))
    recs = [r for r in recs if r["canon"]]

    # thread: group appearances of the same exception across years
    threads = {}
    for r in recs:
        if r.get("id"):
            key = (r["canon"], r["id"])
        else:
            nd = norm_dates(r.get("dates"))
            pv = "|".join(sorted(r.get("provisions") or []))
            if nd or pv:
                key = (r["canon"], nd, pv)            # stable cross-year key (minute-date + provisions)
            else:
                # scanned "N) <desc>" items with NO date and NO provision: the tuple key would be
                # empty and collapse every such exception of a presbytery into one. Key on a
                # description signature so distinct exceptions stay distinct (same-text restatements
                # across years still join).
                sig = re.sub(r"^[\d).\s]*(par\.?\s*\d+\s*)?", "", (r.get("description") or "").lower())
                sig = re.sub(r"[^a-z]", "", sig)[:45]
                key = (r["canon"], "sig", sig or f"{r['vol']}:{r.get('line_start')}")
        t = threads.setdefault(key, {"canon": r["canon"], "id": r.get("id"),
                                     "provisions": [], "description": "", "appearances": []})
        t["appearances"].append(r)
        for p in (r.get("provisions") or []):
            if p not in t["provisions"]:
                t["provisions"].append(p)
        # keep the longest description (the raised one is usually fullest)
        if len(r.get("description") or "") > len(t["description"]):
            t["description"] = r["description"]
    for t in threads.values():
        t["appearances"].sort(key=lambda a: a["year"])
        t["first_year"] = t["appearances"][0]["year"]
        t["first_ga"] = t["appearances"][0]["ga_ordinal"]
        t["final"] = t["appearances"][-1]["finding"]

    # attach floor-action provenance (match by canon presbytery + exception id, where available)
    fmap = {}
    for fa in floor:
        fmap.setdefault((canon_presb(fa["presbytery"]), (fa.get("exception_id") or "").replace("-0", "-")), []).append(fa)
    def floor_for(t):
        out = []
        for a in t["appearances"]:
            k = (t["canon"], (a.get("id") or "").replace("-0", "-"))
            out += fmap.get(k, [])
        return out

    by_presb = {}
    for t in threads.values():
        by_presb.setdefault(t["canon"], []).append(t)

    # ---- BCO 40-5 citations to the SJC, matched to cases ----
    STEMS = {18:"ga18_1990",19:"ga19_1991",20:"ga20_1992",21:"ga21_1993",22:"ga22_1994",23:"ga23_1995",
             24:"ga24_1996",25:"ga25_1997",26:"ga26_1998",27:"ga27_1999",28:"ga28_2000",29:"ga29_2001",
             30:"ga30_2002",31:"ga31_2003",32:"ga32_2004",33:"ga33_2005",34:"ga34_2006",35:"ga35_2007",
             36:"ga36_2008",37:"ga37_2009",38:"ga38_2010",39:"ga39_2011",40:"ga40_2012",41:"ga41_2013",
             42:"ga42_2014",43:"ga43_2015",44:"ga44_2016",45:"ga45_2017",46:"ga46_2018",47:"ga47_2019",
             48:"ga48_2021",49:"ga49_2022",50:"ga50_2023",51:"ga51_2024",52:"ga52_2025"}
    SJC_HDR = re.compile(r"[Cc]ite the following.{0,40}[Pp]resbyter", re.I)
    known = {canon_presb(p): p for p in by_presb}
    cases = json.load(open(os.path.join(IDX, "case_pages_map.json"))) if os.path.exists(os.path.join(IDX, "case_pages_map.json")) else {}
    sjc_by_presb = {}
    for ga, stem in STEMS.items():
        year = int(stem.split("_")[1])
        p = os.path.join(ROOT, "markdown", stem + ".md")
        if not os.path.exists(p):
            continue
        lines = open(p, encoding="utf-8").read().split("\n")
        for i, l in enumerate(lines):
            if SJC_HDR.search(l) and any("judicial" in lines[j].lower() for j in range(i, min(i + 5, len(lines)))):
                for j in range(i + 1, min(i + 18, len(lines))):
                    cand = canon_presb(re.sub(r"^[-\s]*\*{0,2}[a-z]?\.?\*{0,2}\s*", "", strip_md(lines[j])).split("(")[0])
                    if cand in known:
                        sjc_by_presb.setdefault(known[cand], {}).setdefault(ga, year)
    # match presbytery -> SJC cases, but ONLY GA-initiated citation cases (40-5 escalations),
    # not unrelated individual complaints that merely name the presbytery.
    CITESTYLE = re.compile(r"\b(PCA v|In re|Citation of|Citation re|Review of Presbytery Records|"
                           r"failing to submit|grossly unconstitutional|important delinquency)", re.I)
    def cases_for(presb):
        key = re.sub(r"[^a-z ]", "", presb.lower())
        seen, hits = set(), []
        for num, c in cases.items():
            title = c.get("title") or ""
            if key and key in re.sub(r"[^a-z ]", "", title.lower()) and CITESTYLE.search(title):
                if c["file"] not in seen:
                    seen.add(c["file"])
                    hits.append((num, c["file"], re.sub(r"\s*#+\s*$", "", title).strip()))
        return hits
    # presbyteries cited via the RPR section-IV scan OR named in a citation-style case
    allp = set(sjc_by_presb) | {p for p in by_presb if cases_for(p)}
    sjc_full = {}
    for presb in allp:
        cs = cases_for(presb)
        sjc_full[presb] = {"citations": [{"ga": g, "year": y} for g, y in sorted(sjc_by_presb.get(presb, {}).items())],
                           "cases": [{"num": n, "label": f"{t[:55]} ({n})" if t else n,
                                      "link": f"cases/{f}.md"} for n, f, t in cs[:5]]}
    # presbytery-level 40-5 citation (banner/hub)
    for t in threads.values():
        t["sjc"] = sjc_full.get(t["canon"])
    # PER-EXCEPTION SJC involvement: this specific exception's own text references the SJC / a case
    SJC_TEXT = re.compile(r"Standing Judicial Commission|\bSJC\b", re.I)
    CASE_NUM = re.compile(r"Case\s+No\.?\s*(\d{4}-\d{1,3})|Case\s+(\d{4}-\d{1,3})|\b(\d{4}-\d{2})\b", re.I)
    for t in threads.values():
        # detect from the CLEANED verbatim slice (slice_md truncates at a bled journal minute), so a
        # slice that overran into the SJC report no longer false-tags the exception.
        blob = " ".join(slice_md(a["vol"], a.get("line_start"), a.get("line_end")) for a in t["appearances"])
        t["sjc_row"] = bool(SJC_TEXT.search(blob))
        nums = []
        if t["sjc_row"]:
            for win in re.findall(r".{0,55}(?:Standing Judicial Commission|\bSJC\b).{0,55}", blob, re.I):
                for cm in CASE_NUM.finditer(win):
                    n = cm.group(1) or cm.group(2) or cm.group(3)
                    if n and n in cases and n not in nums:
                        nums.append(n)
        t["sjc_text_cases"] = nums

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".md"):
            os.remove(os.path.join(OUT, f))

    DISP = {"raised": "raised (open)", "satisfactory": "satisfactory (closed)",
            "unsatisfactory": "unsatisfactory (outstanding)"}

    EXC = os.path.join(OUT, "exc")
    os.makedirs(EXC, exist_ok=True)
    for f in os.listdir(EXC):
        if f.endswith(".md"):
            os.remove(os.path.join(EXC, f))
    HEAD = {"raised": "Raised", "satisfactory": "Response found satisfactory",
            "unsatisfactory": "Response found unsatisfactory"}

    def lifecycle(t):
        return " → ".join(f"{a['finding']} ({ordinal(a['ga_ordinal'])})" for a in t["appearances"])

    def write_exc_page(t, fname, presb_slug):
        a0 = t["appearances"][0]
        subj = md_escape(t["description"][:80]).rsplit(" ", 1)[0]
        L = [f"# {t['canon']} Presbytery — {md_escape(', '.join(t['provisions']) or 'exception of substance')}", ""]
        if subj:
            L += [f"*{subj}…*", ""]
        hdr = [f"**Presbytery:** {md_escape(t['canon'])}", f"**First raised:** {ordinal(t['first_ga'])} ({t['first_year']})",
               f"**Final disposition:** {DISP.get(t['final'], t['final'])}"]
        if t["provisions"]:
            hdr.append("**Provisions:** " + ", ".join(t["provisions"]))
        L += ["  ·  ".join(hdr), "", f"**Lifecycle:** {lifecycle(t)}", ""]
        fa = floor_for(t)
        if fa:
            L += ["**General Assembly floor action(s):**"]
            for x in fa:
                L.append(f"- {x['action']} — *{x['outcome']}*" + (f" ({x['vote']})" if x.get("vote") else "")
                         + (f"; finding → {x['new_finding']}" if x.get("new_finding") else ""))
            L += [""]
        # Per-exception SJC involvement: only when THIS exception's own text references the SJC / a
        # case (not the presbytery-level 40-5 citation, which lives on the presbytery page + hub).
        if t.get("sjc_row"):
            L += ["**⚖️ This exception involves the Standing Judicial Commission** (referenced in its text below)."]
            for n in t.get("sjc_text_cases", []):
                c = cases[n]
                L.append(f"- SJC case: [{md_escape((c.get('title') or n)[:55])} ({n})](../../cases/{c['file']}.md)")
            L += [""]
        L += ["---", ""]
        for a in t["appearances"]:
            L += [f"## {HEAD.get(a['finding'], a['finding'])} — {ordinal(a['ga_ordinal'])} General Assembly ({a['year']})",
                  f"*{deeplink(a['vol'], a.get('page_anchor'), rel='../../markdown')}*", "",
                  slice_md(a["vol"], a.get("line_start"), a.get("line_end")) or md_escape(a.get("description", "")), ""]
        L += ["---", "",
              f"[← {md_escape(t['canon'])} Presbytery](../{presb_slug}.md)  ·  [RPR catalogue](../../index/RPR.md)"]
        open(os.path.join(EXC, fname), "w", encoding="utf-8").write("\n".join(L) + "\n")

    # ---- per-presbytery pages (+ per-exception pages) ----
    n_pages = n_exc = 0
    for presb, ts in sorted(by_presb.items()):
        ts.sort(key=lambda t: (t["first_year"], t["provisions"][:1]))
        ps = slug(presb)
        yrs = sorted({a["year"] for t in ts for a in t["appearances"]})
        L = [f"# {presb} Presbytery — Review of Records exceptions of substance", "",
             f"*{len(ts)} threaded exception(s) of substance across GA{ts[0]['first_ga']}–"
             f"{max(t['appearances'][-1]['ga_ordinal'] for t in ts)} ({yrs[0]}–{yrs[-1]}). "
             "Each row links to the full exception with its year-by-year text.*", ""]
        if sjc_full.get(presb) and (sjc_full[presb]["citations"] or sjc_full[presb]["cases"]):
            s = sjc_full[presb]
            cl = ("**⚖️ Cited to the Standing Judicial Commission (BCO 40-5)** at the "
                  + "; ".join(f"{ordinal(c['ga'])} GA ({c['year']})" for c in s["citations"]) + ".") if s["citations"] \
                else "**⚖️ Related Standing Judicial Commission case(s) (BCO 40-5):**"
            rel = ("  Related case(s): " if s["citations"] else "  ") + \
                  ", ".join(f"[{md_escape(c['label'])}](../{c['link']})" for c in s["cases"]) if s["cases"] else ""
            L += ["> " + cl + rel, ""]
        L += ["| First raised | Provision(s) | Exception | Lifecycle | Final disposition |",
              "|---|---|---|---|---|"]
        for i, t in enumerate(ts):
            efn = f"{ps}__{i + 1:03d}.md"
            t["_page"] = f"exc/{efn}"
            write_exc_page(t, efn, ps)
            n_exc += 1
            life = " → ".join(f"{a['finding'].split(' ')[0]} ({ordinal(a['ga_ordinal'])})" for a in t["appearances"])
            sjc = " · ⚖️SJC" if t.get("sjc_row") else ""
            L.append(f"| {ordinal(t['first_ga'])} ({t['first_year']}) | {md_escape(', '.join(t['provisions']))} "
                     f"| [{md_escape(t['description'][:110])}…](exc/{efn}){sjc} | {md_escape(life)} "
                     f"| {DISP.get(t['final'], t['final'])} |")
        L += ["", "---", "", "[← RPR catalogue](../index/RPR.md)"]
        open(os.path.join(OUT, ps + ".md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
        n_pages += 1

    # ---- provision cross-reference ----
    prov_map = {}
    for t in threads.values():
        for p in t["provisions"]:
            prov_map.setdefault(p, []).append(t)
    def prov_sort(p):
        m = re.match(r"(BCO|RAO|WCF|WLC|WSC|RONR)\s*(\d+)[-.]?(\d+)?", p)
        return (m.group(1), int(m.group(2)), int(m.group(3) or 0)) if m else ("ZZ", 999, 0)
    L = ["# RPR Exceptions of Substance — by Constitutional Provision", "",
         "Every *Book of Church Order* / *RAO* / Westminster Standards provision cited in a Review of "
         "Presbytery Records exception of substance, with the presbyteries and years cited and the final "
         "disposition. *\"Which presbyteries have been cited under this provision, and was it resolved?\"*", ""]
    for p in sorted(prov_map, key=prov_sort):
        ts = sorted(prov_map[p], key=lambda t: t["first_year"])
        L.append(f"\n## {p}  ·  {len(ts)} citation(s)\n")
        L.append("| Presbytery | First raised | Exception | Final |")
        L.append("|---|---|---|---|")
        for t in ts:
            L.append(f"| [{md_escape(t['canon'])}](../rpr/{slug(t['canon'])}.md) | {ordinal(t['first_ga'])} ({t['first_year']}) "
                     f"| {md_escape(t['description'][:120])} | {DISP.get(t['final'],t['final'])} |")
    open(os.path.join(IDX, "RPR-BY-PROVISION.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

    # ---- hub ----
    import collections
    fin = collections.Counter(t["final"] for t in threads.values())
    provc = collections.Counter(p for t in threads.values() for p in t["provisions"])
    L = ["# Review of Presbytery Records (RPR) — Exceptions of Substance", "",
         "Each year the General Assembly's **Committee on Review of Presbytery Records** reviews every "
         "presbytery's minutes and flags **exceptions of substance** — apparent violations of the "
         "Constitution. This catalogue threads each exception across the years it was disputed (raised → "
         "the presbytery responds → a later GA finds the response **satisfactory** or **unsatisfactory**), "
         "drawn from the RPR appendix of every volume GA18–52 (1990–2025). The published appendix reflects "
         "the **adopted** state (floor strikes already removed); floor-action provenance is noted per row.", "",
         "## Corpus", "",
         f"- **{len(threads)} threaded exceptions of substance** across **{len(by_presb)} presbyteries**, "
         f"GA18–52 (1990–2025), from {len(recs)} report appearances.",
         f"- Final disposition: **{fin['satisfactory']} satisfactory (closed)**, "
         f"**{fin['unsatisfactory']} unsatisfactory (outstanding)**, **{fin['raised']} raised** (most-recent year, "
         "not yet adjudicated).",
         "- Cross-reference by provision: **[RPR exceptions by BCO/RAO/WCF provision](RPR-BY-PROVISION.md)**.", "",
         "## Most-cited provisions", "",
         "| Provision | Citations |", "|---|---:|"]
    for p, c in provc.most_common(15):
        L.append(f"| {p} | {c} |")
    if sjc_full:
        L += ["", "## Citations to the Standing Judicial Commission (BCO 40-5)", "",
              "Presbyteries cited to the SJC for repeated failure to submit minutes/responses or for "
              "serious non-compliance — the terminal escalation of the RPR process — with the related "
              "judicial case where one resulted.", "",
              "| Presbytery | Cited | Related SJC case(s) |", "|---|---|---|"]
        for presb in sorted(sjc_full):
            s = sjc_full[presb]
            cg = ", ".join(f"{ordinal(c['ga'])} ({c['year']})" for c in s["citations"]) or "—"
            cc = "; ".join(f"[{md_escape(c['label'])}](../{c['link']})" for c in s["cases"]) or "—"
            L.append(f"| [{md_escape(presb)}](../rpr/{slug(presb)}.md) | {cg} | {cc} |")
    L += ["", "## Presbyteries", "",
          "| Presbytery | Exceptions | Satisfactory | Outstanding | Years |", "|---|---:|---:|---:|---|"]
    for presb, ts in sorted(by_presb.items()):
        yrs = sorted({t["first_year"] for t in ts})
        sat = sum(1 for t in ts if t["final"] == "satisfactory")
        out = sum(1 for t in ts if t["final"] == "unsatisfactory")
        L.append(f"| [{md_escape(presb)}](../rpr/{slug(presb)}.md) | {len(ts)} | {sat} | {out} "
                 f"| {yrs[0]}–{yrs[-1]} |")
    open(os.path.join(IDX, "RPR.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

    print(f"[{ROOT}] RPR catalogue: {len(threads)} threads, {len(by_presb)} presbyteries, "
          f"{n_pages} pages; {len(prov_map)} provisions; dropped {dropped} no-presbytery records")


if __name__ == "__main__":
    main()
