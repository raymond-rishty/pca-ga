#!/usr/bin/env python3
"""32_rpr_parse_scanned.py — parse the RPR per-presbytery report for the SCANNED era GA18-30.

The pre-2003 format differs from the born-digital one (handled by 31_rpr_parse.py) and DRIFTS
across 1990-2002, so section *letters* are unreliable — we key on descriptive TEXT instead:
  - a header containing "without exception"            -> skip
  - "exceptions of form" (only)                        -> skip (form, out of scope)
  - "exception(s) of substance"                        -> mode = raised
  - "...found/approved ... satisfactory"               -> mode = satisfactory
  - "...found/approved ... unsatisfactory"             -> mode = unsatisfactory
  - a bare "Response..."/"d." detail block inherits the presbytery's last sat/unsat mode
Exceptions of substance appear as either:
  - "Exception: <dates>: <text>. <BCO cite>"   (GA25-30, provision trails the text, no parens)
  - "N) <text> (BCO ...)"                        (GA18-24, numbered items under a combined section)
with "Response[:/ to Nth GA]" / "Rationale:" blocks following in the sat/unsat sections.

Writes per-volume index/rpr/<vol>.json (same schema as 31_rpr_parse.py), replacing the
under-extracted agent files. Usage: 32_rpr_parse_scanned.py [ROOT]   (ROOT defaults to /workspace)
"""
from __future__ import annotations
import json, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
MD = os.path.join(ROOT, "markdown")
IDX = os.path.join(ROOT, "index")
VOLS = [f"ga{o:02d}_{y}" for o, y in zip(range(18, 31),
        [1990, 1991, 1992, 1993, 1994, 1995, 1996, 1997, 1998, 1999, 2000, 2001, 2002])]

REGION = re.compile(r"Report concerning the Minutes of", re.I)
TOP = re.compile(r"^\s*\*{0,2}([IVX]+)\.\s")                      # next roman-numeral top section
PRESBY = re.compile(r"^[-\s]*\d+\.\s*That the Minutes of\s+(.*?)\s+Presbytery", re.I)
HEADER = re.compile(r"^[-\s]*\*{0,2}[a-e]\*{0,2}\s*[.)]\*{0,2}\s|without exception|exceptions? of (form|substance)|"
                    r"response", re.I)
EXC_A = re.compile(r"^[-\s]*\*{0,2}Exception:\*{0,2}\s*(.+)$", re.I)   # GA25-30
EXC_B = re.compile(r"^[-\s]*\*{0,2}(\d+)\)\s*(.+)$")                   # GA18-24 numbered items
# GA18-30 bare "Date: description" (the colon distinguishes a substance item from a form date list)
_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
EXC_C = re.compile(rf"^[-\s]*\*{{0,2}}((?:{_MON}\s+\d[\d,\s/&-]*\d{{4}}|General))\*{{0,2}}\s*:\s*(.*)$", re.I)
RESP = re.compile(r"^[-\s]*\*{0,2}(Response|Rationale)[^:]*:\*{0,2}\s*(.*)$", re.I)
PROV = re.compile(r"(BCO|RAO|WCF|WLC|WSC|RONR)\s*(?:§|#|Sec\.?|Section)?\s*\d[\d\-.:a-z()]*", re.I)
ANCHOR = re.compile(r'<a id="(ga\d+-p[0-9A-Za-z]+)">')
DATE = re.compile(r"^([A-Z][a-z]+ \d|[A-Z][a-z]+\.?\s*\d|\d{1,2}[/-]|General\b)", re.I)


def strip_md(s):
    s = re.sub(r"<a id=[^>]*>|</a>|<!--.*?-->", "", s or "")
    return re.sub(r"\s+", " ", re.sub(r"[*_`]+", "", s)).strip()


def provisions(text):
    out = []
    for m in PROV.finditer(text or ""):
        p = re.sub(r"\s+", " ", m.group(0)).strip()
        while p.endswith(")") and p.count("(") < p.count(")"):
            p = p[:-1]
        p = p.rstrip(".,;")
        if p not in out:
            out.append(p)
    return out


def mode_of(line):
    """Return raised/satisfactory/unsatisfactory/skip/None for a section-header line."""
    l = line.lower()
    if "unsatisfactory" in l:
        return "unsatisfactory"
    if "satisfactory" in l:
        return "satisfactory"
    if "without exception" in l:
        return "skip"
    if "exception of substance" in l or "exceptions of substance" in l:
        return "raised"
    if "exception of form" in l or "exceptions of form" in l:
        return "skip"
    return None


def parse_volume(stem):
    ga, year = int(stem[2:4]), int(stem.split("_")[1])
    lines = open(os.path.join(MD, stem + ".md"), encoding="utf-8").read().split("\n")
    cands = [i for i, l in enumerate(lines)
             if REGION.search(l) and "...." not in l and not re.search(r"p\.\s*\d+\s*$", l)]
    if not cands:
        return []
    def pc(c, w=900):
        return sum(1 for j in range(c + 1, min(c + w, len(lines))) if PRESBY.match(lines[j]))
    start = max(cands, key=pc)
    if pc(start) == 0:
        return []
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if TOP.match(lines[i]) and "Presbytery" not in lines[i] and "Minutes" not in lines[i]:
            end = i
            break

    anchor_at, cur_a = {}, None
    for i in range(len(lines)):
        m = ANCHOR.search(lines[i])
        if m:
            cur_a = m.group(1)
        anchor_at[i] = cur_a

    recs = []
    presby = None
    mode = None          # raised / satisfactory / unsatisfactory / skip
    last_sat = None      # last sat/unsat mode in this presbytery (for bare Response detail blocks)
    cur = None

    def close(c, endln):
        if not c:
            return
        c["line_end"] = endln
        desc = strip_md(" ".join(c.pop("_desc")))
        if not c["provisions"]:
            c["provisions"] = provisions(desc)
        c["description"] = desc
        c["responses"] = [strip_md(x) for x in c.pop("_resp")]
        if len(desc) < 10 and not c["responses"]:      # bare date / stray line, not a real exception
            return
        recs.append(c)

    def new(dates, text, i):
        return {"vol": stem, "ga_ordinal": ga, "year": year, "presbytery": presby,
                "section": {"raised": "c", "satisfactory": "d", "unsatisfactory": "e"}.get(mode, "?"),
                "finding": mode, "id": None, "origin_year": None, "seq": None,
                "dates": strip_md(dates), "provisions": provisions(text),
                "page_anchor": anchor_at.get(i), "line_start": i + 1,
                "_desc": [strip_md(text)], "_resp": []}

    i = start
    while i < end:
        ln = lines[i]
        mp = PRESBY.match(ln)
        if mp:
            close(cur, i); cur = None
            presby = strip_md(mp.group(1)); mode = None; last_sat = None
            i += 1; continue
        # section header (keyworded: without exception / of form / of substance / satisfactory / unsat)
        m = mode_of(ln)
        if m is not None:
            close(cur, i); cur = None
            if m in ("satisfactory", "unsatisfactory"):
                last_sat = m
            mode = m
            i += 1; continue
        # carried/response section header: a prior-year exception block — "...responses to the Nth GA...",
        # "...no response to the Nth GA ... submitted to ...". These are NEVER newly raised. (The letter
        # may lack a dot, e.g. "d That as no response...", so detect by content. Exclude real Response: lines.)
        # anchor to the line start: real carried-response headers begin with the phrase ("Responses to
        # the 18th GA…", "d That as no response to the 21st…"), whereas ordinary response prose buries
        # "response to the" mid-sentence ("…taken in response to the concerns of the 21st General
        # Assembly…") — the old un-anchored form matched the latter and truncated the response.
        if (not RESP.match(ln)) and re.search(
                r"^\W*(?:[a-eA-E]\W+)?(?:that\s+(?:as\s+)?)?(?:no )?responses? to the\b.{0,80}"
                r"(\d+\s*(st|nd|rd|th)?\s*(general assembly|ga)\b|submitted|previous assembl)", ln, re.I):
            close(cur, i); cur = None
            mode = last_sat or "unsatisfactory"
            i += 1; continue
        if mode in ("raised", "satisfactory", "unsatisfactory"):
            ma = EXC_A.match(ln)
            if ma:
                close(cur, i); cur = None
                body = ma.group(1)
                # "dates: description"  (split on the first colon if the head looks like dates)
                if ":" in body and DATE.match(body):
                    dates, desc = body.split(":", 1)
                else:
                    dates, desc = "", body
                cur = new(dates, desc.strip(), i)
                i += 1; continue
            mb = EXC_B.match(ln)
            if mb and len(mb.group(2)) > 12:        # numbered substance item (skip tiny "1)")
                close(cur, i); cur = None
                cur = new("", mb.group(2), i)
                i += 1; continue
            mc = EXC_C.match(ln)                     # bare "Date: description" substance item
            if mc:
                close(cur, i); cur = None
                cur = new(mc.group(1), mc.group(2), i)
                i += 1; continue
            mr = RESP.match(ln)
            if mr and cur is not None:
                cur["_resp"].append(strip_md(mr.group(2)))
                i += 1; continue
            if cur is not None and strip_md(ln):
                (cur["_resp"] if cur["_resp"] else cur["_desc"]).append(strip_md(ln))
        i += 1
    close(cur, end)
    return recs


def main():
    rprdirs = [os.path.join(IDX, "rpr"), "/workspace/dist/pca-ga/index/rpr"]
    for d in rprdirs:
        os.makedirs(d, exist_ok=True)
    grand = 0
    for stem in VOLS:
        r = parse_volume(stem)
        for d in rprdirs:
            json.dump(r, open(os.path.join(d, stem + ".json"), "w"), indent=1, ensure_ascii=False)
        grand += len(r)
        print(f"{stem}: {len(r)} appearances (raised={sum(1 for x in r if x['finding']=='raised')}, "
              f"sat={sum(1 for x in r if x['finding']=='satisfactory')}, "
              f"unsat={sum(1 for x in r if x['finding']=='unsatisfactory')}); "
              f"presbyteries={len({x['presbytery'] for x in r})}")
    print(f"\nGA18-30 scanned: {grand} exception appearances")


if __name__ == "__main__":
    main()
