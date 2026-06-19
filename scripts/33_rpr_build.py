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


def printed_page(anchor):
    m = re.search(r"-p(\w+)$", anchor or "")
    return m.group(1) if m else "?"


def deeplink(vol, anchor, rel="../markdown"):
    if not anchor:
        return f"{vol}"
    return f"[{vol} p.{printed_page(anchor)}]({rel}/{vol}.md#{anchor})"


def norm_dates(s):
    return re.sub(r"[^0-9]", "", s or "")[:8]        # crude date key for tuple-threading


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
            key = (r["canon"], norm_dates(r.get("dates")), "|".join(sorted(r.get("provisions") or [])))
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

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".md"):
            os.remove(os.path.join(OUT, f))

    DISP = {"raised": "raised (open)", "satisfactory": "satisfactory (closed)",
            "unsatisfactory": "unsatisfactory (outstanding)"}

    # ---- per-presbytery pages ----
    n_pages = 0
    for presb, ts in sorted(by_presb.items()):
        ts.sort(key=lambda t: (t["first_year"], t["provisions"][:1]))
        yrs = sorted({a["year"] for t in ts for a in t["appearances"]})
        L = [f"# {presb} Presbytery — Review of Records exceptions of substance", "",
             f"*{len(ts)} threaded exception(s) of substance across GA{ts[0]['first_ga']}–"
             f"{max(t['appearances'][-1]['ga_ordinal'] for t in ts)} ({yrs[0]}–{yrs[-1]}). "
             "Each row is one exception with its multi-year lifecycle and a deep link to the minutes.*", "",
             "| First raised | Provision(s) | Exception | Lifecycle | Final disposition | Minutes |",
             "|---|---|---|---|---|---|"]
        for t in ts:
            life = " → ".join(f"{DISP.get(a['finding'],a['finding']).split(' ')[0]} ({ordinal(a['ga_ordinal'])})"
                              for a in t["appearances"])
            fa = floor_for(t)
            falab = ""
            if fa:
                acts = "; ".join(f"{x['action']} {x['outcome']}" + (f" {x['vote']}" if x.get('vote') else "") for x in fa)
                falab = f" · _floor: {acts}_"
            links = " · ".join(deeplink(a["vol"], a.get("page_anchor")) for a in t["appearances"])
            L.append(f"| {ordinal(t['first_ga'])} ({t['first_year']}) | {md_escape(', '.join(t['provisions']))} "
                     f"| {md_escape(t['description'][:160])}{falab} | {md_escape(life)} "
                     f"| {DISP.get(t['final'], t['final'])} | {links} |")
        L += ["", "---", "", "[← RPR catalogue](../index/RPR.md)"]
        open(os.path.join(OUT, slug(presb) + ".md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
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
