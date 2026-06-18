#!/usr/bin/env python3
"""
18_structure.py — PROTOTYPE high-level structural outline of a GA minutes volume.

Goal (user, 2026-06-17): capture the document HIERARCHY at the HIGH level first — the major
sections and subsections ("where am I in this volume / report") — not the low-level
exception/response nesting. Builds a queryable tree with page anchors, renders a navigable outline.

Skeleton (stable across 1973-2025, with per-era variation):
  Volume (GA N, year)
    PART I   Directory          (committees, agencies, roll)
    PART II  Journal            -> Sessions (First .. Nth) -> numbered actions  N-1 .. N-k
    PART III Appendices         -> Appendix A..Z  (each a committee report / document)
    PART IV  Corrections
    PART V   References & Index

PART dividers are anchored on CANONICAL titles so a committee report that internally reuses
"PART I/II/III" (e.g. ga05_1977 p201 "PART I: BIBLICAL STUDY") is not mistaken for a volume part.
"""
from __future__ import annotations
import glob, importlib.util, json, os, re, sys

ROOT = "/workspace"
PJ = os.path.join(ROOT, "build", "page_jsonl")
OUT = os.path.join(ROOT, "index", "structure")

# A committee-report SECTION heading: a roman numeral + Title-case heading on its own short line
# (optionally bold/#-wrapped). Detected broadly WITHIN a report's page span (not the closed
# format_md title set) so report-specific sections like "II. Advice on Overtures" are caught.
_SEC = re.compile(r"^\s*[#*_]*\s*([IVX]{1,6})\.\s+([A-Z][^*_#]{2,52}?)\s*[*_]*\s*$")


def _section(ln):
    m = _SEC.match(ln)
    if not m:
        return None
    title = re.sub(r"\s+", " ", m.group(2)).strip(" .—-:")
    return (m.group(1), title) if len(title) >= 3 else None


# An OVERTURE header: line-start "Overture N" then either a "." or ":" right after the number
# (a header label — e.g. "Overture 24. From Calvary", "Overture 1. LF Coast Presbytery",
# "Overture 7. Adopted by Warrior Presbytery"), OR whitespace + "from" ("Overture 8 From the
# Presbytery of the Evangel", born-digital "**OVERTURE 1** from ..."). The punctuation/"from"
# requirement skips prose mentions like "Overture 12 of North Georgia ... was referred".
_OVERTURE = re.compile(
    r"^[#*_\s]*OVERTURE\s+(\d+)\b(?:\s*,[\s,A-Z]*?[A-Z]\.?)?\**"
    r"(?:\s*[.:]\s*(?:from\s+)?|\s+from\s+)(.*?)\**\s*$", re.I)  # ,A,B... = lettered multi-part overture


def _bad_src(s):
    # reject overture "headers" whose source reveals they are NOT real overtures: back-of-book
    # index/TOC lines, page-reference stubs, signatures, and committee-response cross-references.
    s = (s or "").strip()
    if not s:
        return True
    if re.search(r"\.{3,}", s):                                   # dot leaders => index/TOC line
        return True
    if re.fullmatch(r"[\d.,;:&p()\s/-]+", s):                     # pure page refs ("32", "60, 401")
        return True
    if re.match(r"(?i)(adopted\b|attested\b|see\b|/s/|p\.?\s*\d)", s):   # signature / "See page" xref
        return True
    if re.search(r"(?i)\bpp?\.\s*\d", s):                          # trailing page ref => back-of-book index line
        return True
    if re.search(r"(?i)\b(be answered|was answered|answered in the|was committed)\b", s):  # committee response
        return True
    return False


def _norm_src(s):
    # collapse a source to its core name for de-duplication ("the Presbytery of Potomac (to CCB)"
    # and "Potomac Presbytery" -> "potomac"). CONSERVATIVE: only drop trailing parentheticals;
    # keep any quoted overture title so genuinely-distinct overtures sharing a number are NOT
    # merged (early GAs reused numbers; a committee listing's quoted title must stay distinguishing).
    s = re.sub(r"\(.*?\)", "", (s or "").lower())
    s = re.sub(r"\b(the|from|presbytery|of|session|church|adopted|at|its|meeting|stated)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


def _overture(ln):
    m = _OVERTURE.match(ln)
    if not m:
        return None
    src = re.sub(r"[*_]", "", re.sub(r"\s+", " ", m.group(2))).strip(" .:—-")
    if _bad_src(src):
        return None
    return (int(m.group(1)), src[:90])


# journal lettered SECTION ("A. COMMUNICATIONS ...", "B. OVERTURES ...") and referral GROUPING
# ("TO THE COMMITTEE OF COMMISSIONERS ON ...") — mirror of format_md's _LETTERSEC / _REFERRAL.
_LSEC = re.compile(r"^[#*_\s]*([A-Z])\.\s+([A-Z][A-Z0-9&',./()-]*(?:\s+[A-Z0-9&',./()-]+)+)\s*$")
_REF = re.compile(r"^[#*_\s]*TO THE COMMITTEE\b")

CANON = r"DIRECTORY|JOURNAL|APPENDICES|APPENDIX|CORRECTIONS|REFERENCES|INDEX|ROLL|STANDING RULES"
PART_RE = re.compile(r"^\s*#*\s*\**\s*PART\s+([IVXL]+)\b[*\s:.—-]*(\**[A-Za-z].*)?$")
APPX_RE = re.compile(r"^\s*#*\s*\**\s*(?:APPENDIX|Appendix)\s+([A-Z])\b[*\s:.—-]*(\**[A-Za-z].*)?$")
SESSION_RE = re.compile(r"^\s*#*\s*\**\s*((?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|"
                        r"Ninth|Tenth|Eleventh|Twelfth)\s+Session\b.*)$", re.I)
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}


def _clean(s):
    return re.sub(r"\s+", " ", re.sub(r"[*_#]", "", s)).strip(" .—-:")


def _is_toc_line(s):
    return bool(re.search(r"\.{4,}\s*\d*\s*$", s) or re.search(r"\s\d{1,4}\s*$", s.strip()))


CANON_TITLE = {1: "Directory", 2: "Journal", 3: "Appendices", 4: "Corrections",
               5: "References and Index"}
_NUM_NAME = {v: k for k, v in _ROMAN.items()}


def extract(vol):
    rows = [json.loads(l) for l in open(os.path.join(PJ, f"{vol}.pages.jsonl"))]
    ordn, year = (int(x) for x in re.match(r"ga(\d+)_(\d+)", vol).groups())
    pnum = re.compile(r"^\s*#*\s*\**\s*%d-(\d+)\b[*\s.:—-]*(.*)$" % ordn)

    # 1) volume PARTs. Collect candidate divider lines, then drop TOC pages (a page that lists
    # >=2 different PART numerals IS the table of contents, not a section divider).
    cand = []  # (pdf_page, printed, num, title)
    page_nums = {}
    for r in rows:
        for ln in r["text"].split("\n"):
            m = PART_RE.match(ln)
            if not m or m.group(1) not in _ROMAN:
                continue
            num = _ROMAN[m.group(1)]
            title = _clean(m.group(2) or "")
            if title and not re.match(r"(?i)(%s)\b" % CANON, title):
                continue                       # non-canonical title => report-internal PART, skip
            cand.append((r["pdf_page"], r.get("printed_page"), num, title))
            page_nums.setdefault(r["pdf_page"], set()).add(num)
    toc_pages = {pg for pg, nums in page_nums.items() if len(nums) >= 2}
    parts = {}
    for pg, pr, num, title in cand:
        if pg in toc_pages or num in parts:
            continue                            # skip the contents listing; keep first real divider
        parts[num] = {"type": "part", "label": f"PART {_NUM_NAME[num]}",
                      "title": title or CANON_TITLE.get(num, ""),
                      "pdf_page": pg, "printed_page": pr, "children": []}
    # synthesize PART II (Journal) if there is no explicit divider — anchor at the first Session
    if 2 not in parts:
        for r in rows:
            if any(SESSION_RE.match(l) and not _is_toc_line(l) for l in r["text"].split("\n")):
                parts[2] = {"type": "part", "label": "PART II", "title": "Journal",
                            "pdf_page": r["pdf_page"], "printed_page": r.get("printed_page"),
                            "children": []}
                break
    part_list = [parts[k] for k in sorted(parts)]
    # page span of each part (until the next part starts)
    bounds = [(p["pdf_page"], p) for p in part_list]
    for i, (pg, p) in enumerate(bounds):
        p["_end"] = bounds[i + 1][0] if i + 1 < len(bounds) else 10 ** 9

    def part_for(pg):
        cur = None
        for p in part_list:
            if p["pdf_page"] <= pg < p["_end"]:
                cur = p
        return cur

    # 2) Journal (PART II): sessions>actions AND lettered-sections>referral-groupings; appendices (III)
    journal = parts.get(2)
    appx = parts.get(3)
    cur_session = cur_lsec = None
    jmarkers = []                              # (page, node) for every journal structural marker
    for r in rows:
        pg, printed = r["pdf_page"], r.get("printed_page")
        host = part_for(pg)
        inj = journal is not None and host is journal
        if not inj:
            cur_session = cur_lsec = None
        for ln in r["text"].split("\n"):
            toc = _is_toc_line(ln)
            ms = SESSION_RE.match(ln)
            if inj and ms and not toc:
                cur_session = {"type": "session", "label": _clean(ms.group(1)),
                               "pdf_page": pg, "printed_page": printed, "children": []}
                journal["children"].append(cur_session); jmarkers.append((pg, cur_session))
                continue
            ml = _LSEC.match(ln)
            if inj and ml and not toc:
                cur_lsec = {"type": "jsection", "label": ml.group(1), "title": _clean(ml.group(2)),
                            "pdf_page": pg, "printed_page": printed, "children": []}
                journal["children"].append(cur_lsec); jmarkers.append((pg, cur_lsec))
                continue
            if inj and _REF.match(ln):
                grp = {"type": "grouping", "title": _clean(ln)[:70], "pdf_page": pg,
                       "printed_page": printed, "children": []}
                (cur_lsec or journal)["children"].append(grp); jmarkers.append((pg, grp))
                continue
            ma = APPX_RE.match(ln)
            if appx is not None and host is appx and ma and not toc:
                appx["children"].append({"type": "appendix", "label": f"Appendix {ma.group(1)}",
                                         "title": _clean(ma.group(2) or ""), "pdf_page": pg,
                                         "printed_page": printed})
                continue
            mp = pnum.match(ln)
            if inj and mp:
                node = {"type": "action", "label": f"{ordn}-{mp.group(1)}",
                        "title": _clean(mp.group(2))[:80], "pdf_page": pg, "printed_page": printed}
                (cur_session["children"] if cur_session else journal["children"]).append(node)
    # dedupe appendices by letter (keep first) and order by page
    if appx:
        seen = set()
        appx["children"] = sorted(
            [a for a in appx["children"] if not (a["label"] in seen or seen.add(a["label"]))],
            key=lambda a: a["pdf_page"])
        # 3) ONE LEVEL DEEPER: committee-report sections (I. Business Referred / II. Major Issues
        # Discussed / III. Recommendations; SJC I. Summary of the Facts / II. Statement of the
        # Issues / III. Judgment ...) nested under each appendix, within its page span.
        aps = appx["children"]
        for idx, a in enumerate(aps):
            lo = a["pdf_page"]
            hi = aps[idx + 1]["pdf_page"] if idx + 1 < len(aps) else appx["_end"]
            a["children"] = []
            for r in rows:
                if not (lo <= r["pdf_page"] < hi):
                    continue
                for ln in r["text"].split("\n"):
                    sec = _section(ln)
                    if sec:
                        a["children"].append({"type": "section", "label": sec[0], "title": sec[1],
                                              "pdf_page": r["pdf_page"], "printed_page": r.get("printed_page")})
    # 4) OVERTURES (the denomination's proposal history) — attach each under its enclosing referral
    # GROUPING (journal) or appendix (PART III), else the part; collect a flat volume catalogue.
    jmarkers.sort(key=lambda x: x[0])
    grp_ranges = []                            # (lo, hi, grouping-node)
    for idx, (pg0, node) in enumerate(jmarkers):
        if node["type"] != "grouping":
            continue
        hi = next((p for p, _ in jmarkers[idx + 1:]), journal["_end"] if journal else 10 ** 9)
        grp_ranges.append((pg0, hi, node))
    appx_ranges = []
    if appx:
        aps = appx["children"]
        for idx, a in enumerate(aps):
            hi = aps[idx + 1]["pdf_page"] if idx + 1 < len(aps) else appx.get("_end", 10 ** 9)
            appx_ranges.append((a["pdf_page"], hi, a))
    overtures = []
    last = None
    for r in rows:
        pg = r["pdf_page"]
        for ln in r["text"].split("\n"):
            ov = _overture(ln)
            if not ov:
                continue
            num, src = ov
            host = (next((g for lo, hi, g in grp_ranges if lo <= pg < hi), None)
                    or next((a for lo, hi, a in appx_ranges if lo <= pg < hi), None)
                    or part_for(pg))
            if last and last[0] == num and last[1] is host and pg - last[2] <= 1:
                continue                       # same overture continuing onto the next page
            last = (num, host, pg)
            node = {"type": "overture", "number": num, "source": src,
                    "pdf_page": pg, "printed_page": r.get("printed_page")}
            if host is not None:
                host.setdefault("children", []).append(node)
            ctx = host["title"][:50] if host and host.get("type") == "grouping" else \
                (host["label"] if host else None)
            overtures.append({"number": num, "source": src, "pdf_page": pg,
                              "printed_page": r.get("printed_page"), "in": ctx})
    for p in part_list:
        p.pop("_end", None)
    # de-duplicate the CATALOGUE: one entry per (number, normalized-source), aggregating the pages
    # it appears on (overtures section + committee report + index). Distinct presbyteries with the
    # same number stay separate. (The outline tree keeps every occurrence as its own node.)
    cat = {}
    for o in overtures:
        k = (o["number"], _norm_src(o["source"]))
        if k in cat:
            d = cat[k]
            d["pages"].append(o["pdf_page"])
            if len(o["source"]) > len(d["source"]):   # keep the fullest source spelling
                d["source"] = o["source"]
        else:
            o["pages"] = [o["pdf_page"]]
            cat[k] = o
    catalogue = list(cat.values())
    for o in catalogue:
        o["pages"] = sorted({p for p in o["pages"] if p is not None})
        o["pdf_page"] = o["pages"][0] if o["pages"] else o["pdf_page"]
    return {"volume": vol, "ga_ordinal": ordn, "year": year, "parts": part_list,
            "overtures": catalogue}


def _label(c):
    loc = f"p.{c.get('printed_page') or c['pdf_page']}"
    t = c["type"]
    if t == "part":
        return f"**{c['label']}** {c['title']}  _({loc})_"
    if t == "session":
        return f"{c['label']}  _({loc})_  — {len(c.get('children', []))} actions"
    if t == "jsection":
        return f"{c['label']}. {c['title']}  _({loc})_"
    if t == "grouping":
        return f"{c['title']}  _({loc})_"
    if t == "appendix":
        return f"{c['label']}: {c['title'][:60]}  _({loc})_"
    if t == "section":
        return f"{c['label']}. {c['title'][:55]}  _({loc})_"
    if t == "overture":
        return f"**Overture {c['number']}** — {c['source'][:55]}  _({loc})_"
    if t == "action":
        return f"{c['label']} {c['title'][:50]}"
    return str(c)


def _render_node(c, depth, out):
    out.append("  " * depth + "- " + _label(c))
    if c["type"] == "session":               # show the action count, don't list each action
        return
    for ch in c.get("children", []):
        _render_node(ch, depth + 1, out)


def render(tree):
    out = [f"# GA {tree['ga_ordinal']} ({tree['year']}) — structural outline"]
    for p in tree["parts"]:
        _render_node(p, 0, out)
    return "\n".join(out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "show":
        print(render(extract(sys.argv[2])))
    elif cmd == "build":
        os.makedirs(OUT, exist_ok=True)
        vols = sys.argv[2:] or [os.path.basename(p).split(".")[0]
                                for p in sorted(glob.glob(PJ + "/*.pages.jsonl"))]
        for v in vols:
            t = extract(v)
            json.dump(t, open(os.path.join(OUT, f"{v}.json"), "w"), indent=1)
            print(f"{v}: {len(t['parts'])} parts, {len(t['overtures'])} overtures")
    elif cmd == "overtures":
        # catalogue across all volumes, optional substring filter on source/year
        q = sys.argv[2].lower() if len(sys.argv) > 2 else ""
        for p in sorted(glob.glob(OUT + "/ga*.json"), key=lambda x: int(re.search(r"ga(\d+)", x).group(1))):
            t = json.load(open(p))
            for o in t["overtures"]:
                line = f"GA{t['ga_ordinal']} ({t['year']}) Overture {o['number']}: {o['source']}  [p.{o['printed_page'] or o['pdf_page']}, {o['in']}]"
                if not q or q in line.lower():
                    print(line)
