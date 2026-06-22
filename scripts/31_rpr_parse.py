#!/usr/bin/env python3
"""31_rpr_parse.py — parse the Review of Presbytery Records (RPR) per-presbytery report.

Phase 1 (this script): the explicit-ID born-digital years GA51-52, whose Section "Report
Concerning the Minutes of Each Presbytery" tags every exception of substance with a stable
`YYYY-NN` id (origin-year + sequence) that recurs verbatim in later years' satisfactory/
unsatisfactory sections — so threading is reliable.

Per presbytery block (`N. That the Minutes of <Presbytery> Presbytery: <vote>`):
  a. approved without exception      b. exception of form
  c. exception of substance  -> NEW exceptions raised this GA
  d. responses found SATISFACTORY    e. responses found UNSATISFACTORY  (carried-over)
Each exception line: `**YYYY-NN: <dates>** ( <BCO/RAO/WCF cites> ) — <description>`, with
`**Response:**` / `**Rationale:**` blocks following in d/e.

Outputs (to <ROOT>/index/):
  rpr_exceptions.json — one record per (volume, presbytery, exception appearance)
  rpr_threads.json    — grouped by (presbytery, id): the multi-year timeline + final disposition

Usage: 31_rpr_parse.py [ROOT]   (ROOT defaults to /workspace)
"""
from __future__ import annotations
import json, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")
# Deterministic coverage = the volumes whose "Report Concerning the Minutes of Each Presbytery"
# uses the regular **a/b/c/d/e** structure (bold or list-dash): GA44-48, 50 (bare "Exception:") and
# GA51-52 (explicit YYYY-NN ids). The heterogeneous GA31-43, 49 (missing heading / plain-letter
# sections / wrapped layout) and scanned GA18-30 are handled by the agent workflow -> index/rpr/<vol>.json.
VOLS = ["ga31_2003", "ga32_2004", "ga33_2005", "ga34_2006", "ga35_2007", "ga36_2008", "ga37_2009",
        "ga38_2010", "ga39_2011", "ga40_2012", "ga41_2013", "ga42_2014", "ga43_2015", "ga44_2016",
        "ga45_2017", "ga46_2018", "ga47_2019", "ga48_2021", "ga49_2022", "ga50_2023",
        "ga51_2024", "ga52_2025"]

REGION = re.compile(r"Report Concerning the Minutes of", re.I)
TOP_SECTION = re.compile(r"^\*\*([IVX]+)\.")               # next roman-numeral top section ends the region
PRESBY = re.compile(r"^[-\s]*\d+\.\s*That the Minutes of\s+(.*?)\s+Presbytery", re.I)
SECT = re.compile(r"^[-\s]*\*{0,2}([a-e])\*{0,2}\s*[.)]\*{0,2}(?:\s|$)")           # a/b/c/d/e sub-part (bold optional both sides)
SECT_FIND = re.compile(r"found\s+(satisfactory|unsatisfactory)", re.I)
EXC = re.compile(r"^[-\s]*\*\*(\d{4})-(\d{1,3}):\s*(.+?)\*\*\s*(.*)$")   # GA51-52: **YYYY-NN: dates** rest
EXC_NOID = re.compile(r"^[-\s]*\*\*(?:\d+\.\s*)?Exception:\s*(.+?)\*\*\s*(.*)$", re.I)   # GA31-50: **Exception: dates** rest
# GA33-style: "**Exception** : **<date>** : <desc + trailing cite>" (bold closes before the colon)
EXC_NOID2 = re.compile(r"^[-\s]*\*{0,2}(?:\d+\.\s*)?Exception\*{0,2}\s*:\s*\*{0,2}(.+?)\*{0,2}\s*:\s*(.*)$", re.I)
RESP = re.compile(r"^[-\s]*\*\*(Response|Rationale)(\s*\[\d{4}\])?\s*:\*\*\s*(.*)$", re.I)
PROV = re.compile(r"(BCO|RAO|WCF|WLC|WSC|RONR)\s*[  ]*\d[\d\-.:a-z()]*", re.I)
ANCHOR = re.compile(r'<a id="(ga\d+-p[0-9A-Za-z]+)">')


def strip_md(s: str) -> str:
    s = re.sub(r"<a id=[^>]*>|</a>|<!--.*?-->", "", s or "")   # drop page-break anchors/comments
    s = re.sub(r"[*_`]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def provisions(text: str) -> list:
    out = []
    for m in PROV.finditer(text or ""):
        p = re.sub(r"\s+", " ", m.group(0)).strip()
        while p.endswith(")") and p.count("(") < p.count(")"):   # drop the enclosing ")", keep "(1)"
            p = p[:-1]
        p = p.rstrip(".,;")
        if p not in out:
            out.append(p)
    return out


def parse_volume(stem: str):
    ga = int(stem[2:4])
    year = int(stem.split("_")[1])
    lines = open(os.path.join(MD, stem + ".md"), encoding="utf-8").read().split("\n")

    # region: the per-presbytery heading that is actually followed by presbytery entries (skip TOC
    # lines and stray earlier mentions, e.g. GA49's summary ref before the real Appendix report).
    cands = [i for i, l in enumerate(lines)
             if REGION.search(l) and "...." not in l and not re.search(r"p\.\s*\d+\s*$", l)]
    if not cands:
        return []
    # a volume can mention the heading more than once (partial ref + the real appendix report);
    # pick the one with the MOST presbytery entries following it.
    def presby_count(c, window=800):
        return sum(1 for j in range(c + 1, min(c + window, len(lines))) if PRESBY.match(lines[j]))
    start = max(cands, key=presby_count)
    if presby_count(start) == 0:
        return []
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if TOP_SECTION.match(lines[i]) and "Presbytery" not in lines[i]:
            end = i
            break

    # track page anchors so each record can deep-link
    anchor_at = {}
    cur_anchor = None
    for i in range(len(lines)):
        m = ANCHOR.search(lines[i])
        if m:
            cur_anchor = m.group(1)
        anchor_at[i] = cur_anchor

    recs = []
    presby = None
    section = None         # 'c' raised / 'd' satisfactory / 'e' unsatisfactory
    finding = None
    cur = None             # current exception record being filled

    def close(cur, endln):
        if not cur:
            return
        cur["line_end"] = endln
        desc = strip_md(" ".join(cur.pop("_desc")))
        if not cur["provisions"]:                      # provisions wrapped to a continuation line
            cur["provisions"] = provisions(desc[:240])
            m = re.match(r"\(?[^)]*\)\s*[—–-]\s*", desc)
            if m and cur["provisions"]:
                desc = desc[m.end():].strip()
        cur["description"] = desc
        cur["responses"] = [strip_md(x) for x in cur.pop("_resp")]
        recs.append(cur)

    i = start
    while i < end:
        ln = lines[i]
        mp = PRESBY.match(ln)
        if mp:
            close(cur, i); cur = None
            presby = strip_md(mp.group(1))
            section = finding = None
            i += 1; continue
        ms = SECT.match(ln)
        if ms:
            close(cur, i); cur = None
            section = ms.group(1)
            mf = SECT_FIND.search(ln)
            finding = (mf.group(1).lower() if mf else None)
            i += 1; continue
        # carried/response section header that SECT misses (e.g. "d **. That as no responses to the
        # 31st GA were received, these should be submitted..."): PRIOR-year exceptions, NEVER newly
        # raised. Match on the markdown-stripped line (the "31** **[st]** **GA" markup breaks raw matching).
        sl = strip_md(ln)
        # these carried-response headers START the line ("d. That as no responses to the 31st GA were
        # received…", "Responses to the 18th GA…"). The OLD loose "responses? to the" matched ordinary
        # mid-sentence prose ("…taken in response to the concerns of the 21st General Assembly…") and
        # closed the record early, truncating the response — so anchor to the line start to tell them apart.
        if re.search(r"^\W*(?:[a-eA-E]\W+)?(?:that\s+(?:as\s+)?)?(?:no )?responses? to the\b.{0,80}"
                     r"(\bga\b|general assembly|received|submitted|previous assembl)", sl, re.I) \
                and not re.match(r"(?:\d+\.\s*)?Exception", sl, re.I):
            close(cur, i); cur = None
            mf = SECT_FIND.search(sl)
            section = "d" if (mf and mf.group(1).lower() == "satisfactory") else "e"
            finding = "satisfactory" if section == "d" else "unsatisfactory"
            i += 1; continue
        me = EXC.match(ln)
        if me and section in ("c", "d", "e"):
            close(cur, i); cur = None
            yr, seq, dates, rest = me.groups()
            rs = strip_md(rest)                          # drop _BCO_ / ** emphasis before parsing
            md = re.search(r"[—–]\s*", rs)               # provisions "(...)" — description
            if md:
                prov_part, desc0 = rs[:md.start()], rs[md.end():]
            else:
                prov_part, desc0 = rs, re.sub(r"^\(.*\)\s*", "", rs)
            cur = {"vol": stem, "ga_ordinal": ga, "year": year, "presbytery": presby,
                   "section": section,
                   "finding": ("raised" if section == "c" else (finding or ("satisfactory" if section == "d" else "unsatisfactory"))),
                   "id": f"{yr}-{int(seq):02d}", "origin_year": int(yr), "seq": int(seq),
                   "dates": strip_md(dates), "provisions": provisions(prov_part),
                   "page_anchor": anchor_at.get(i), "line_start": i + 1,
                   "_desc": [desc0], "_resp": []}
            i += 1; continue
        m2 = EXC_NOID.match(ln)
        if m2 and section in ("c", "d", "e"):
            close(cur, i); cur = None
            dates, rest = m2.groups()
            rs = strip_md(rest)
            md = re.search(r"[—–]\s*", rs)
            if md:
                prov_part, desc0 = rs[:md.start()], rs[md.end():]
            else:
                prov_part, desc0 = rs, re.sub(r"^\(.*\)\s*", "", rs)
            cur = {"vol": stem, "ga_ordinal": ga, "year": year, "presbytery": presby,
                   "section": section,
                   "finding": ("raised" if section == "c" else (finding or ("satisfactory" if section == "d" else "unsatisfactory"))),
                   "id": None, "origin_year": None, "seq": None,
                   "dates": strip_md(dates).rstrip(":,; "), "provisions": provisions(prov_part),
                   "page_anchor": anchor_at.get(i), "line_start": i + 1,
                   "_desc": [desc0], "_resp": []}
            i += 1; continue
        m2b = EXC_NOID2.match(ln)
        if m2b and section in ("c", "d", "e"):
            close(cur, i); cur = None
            dates, desc0 = m2b.group(1), strip_md(m2b.group(2))
            cur = {"vol": stem, "ga_ordinal": ga, "year": year, "presbytery": presby,
                   "section": section,
                   "finding": ("raised" if section == "c" else (finding or ("satisfactory" if section == "d" else "unsatisfactory"))),
                   "id": None, "origin_year": None, "seq": None,
                   "dates": strip_md(dates).rstrip(":,; "), "provisions": provisions(desc0),
                   "page_anchor": anchor_at.get(i), "line_start": i + 1,
                   "_desc": [desc0], "_resp": []}
            i += 1; continue
        mr = RESP.match(ln)
        if mr and cur is not None:
            cur["_resp"].append(strip_md(mr.group(3)))
            i += 1; continue
        # continuation text
        if cur is not None and strip_md(ln):
            (cur["_resp"] if cur["_resp"] else cur["_desc"]).append(strip_md(ln))
        i += 1
    close(cur, end)
    return recs


def main():
    allrecs = []
    rprdirs = [os.path.join(IDX, "rpr"), "/workspace/dist/pca-ga/index/rpr"]
    for d in rprdirs:
        os.makedirs(d, exist_ok=True)
    for stem in VOLS:
        r = parse_volume(stem)
        for d in rprdirs:                       # write per-volume too (one home for all eras)
            json.dump(r, open(os.path.join(d, stem + ".json"), "w"), indent=1, ensure_ascii=False)
        print(f"{stem}: {len(r)} exception appearances "
              f"(raised={sum(1 for x in r if x['section']=='c')}, "
              f"satisfactory={sum(1 for x in r if x['section']=='d')}, "
              f"unsatisfactory={sum(1 for x in r if x['section']=='e')}); "
              f"presbyteries={len({x['presbytery'] for x in r})}")
        allrecs += r
    json.dump(allrecs, open(os.path.join(IDX, "rpr_exceptions.json"), "w"), indent=1, ensure_ascii=False)

    # thread by (presbytery, id)
    threads = {}
    for r in allrecs:
        # explicit id (GA51-52) else tuple key (presbytery + minute-date + provisions)
        k = (f"{r['presbytery']}|{r['id']}" if r["id"]
             else f"{r['presbytery']}|{r['dates']}|{'/'.join(sorted(r['provisions']))}")
        t = threads.setdefault(k, {"presbytery": r["presbytery"], "id": r["id"],
                                   "origin_year": r["origin_year"], "provisions": r["provisions"],
                                   "dates": r["dates"], "appearances": []})
        t["appearances"].append({"vol": r["vol"], "year": r["year"], "section": r["section"],
                                 "finding": r["finding"], "page_anchor": r["page_anchor"]})
        if not t["provisions"] and r["provisions"]:
            t["provisions"] = r["provisions"]
    for t in threads.values():
        t["appearances"].sort(key=lambda a: a["year"])
        t["final_disposition"] = t["appearances"][-1]["finding"]
    json.dump(list(threads.values()), open(os.path.join(IDX, "rpr_threads.json"), "w"), indent=1, ensure_ascii=False)
    print(f"\nthreads (presbytery,id): {len(threads)}; "
          f"final satisfactory={sum(1 for t in threads.values() if t['final_disposition']=='satisfactory')}, "
          f"unsatisfactory={sum(1 for t in threads.values() if t['final_disposition']=='unsatisfactory')}, "
          f"raised-only={sum(1 for t in threads.values() if t['final_disposition']=='raised')}")


if __name__ == "__main__":
    main()
