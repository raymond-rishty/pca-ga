#!/usr/bin/env python3
"""
10_hunt.py — locate roster cases that our index is MISSING, by full-text search of
the page layer (no model needed). For each missing official case we search for its
party surname co-occurring with its presbytery, ranked by year proximity to the
docket year. Also flags cases already in our index under a divergent number (relink).

Inputs : index/sjc_official/missing.jsonl, index/cases.jsonl, index/pca_minutes.db
Output : index/hunt/located.jsonl  (one row per missing case: located | relink | not_found)

CLI:  10_hunt.py            # run the locator over all misses, write located.jsonl
      10_hunt.py probe "Landrum" "Mississippi Valley" 1995   # debug one search
"""
from __future__ import annotations
import json, os, re, sqlite3, sys, difflib

ROOT = "/workspace"
DB = os.path.join(ROOT, "index", "pca_minutes.db")
MISSING = os.path.join(ROOT, "index", "sjc_official", "missing.jsonl")
CASES = os.path.join(ROOT, "index", "cases.jsonl")
OUTDIR = os.path.join(ROOT, "index", "hunt")
OUT = os.path.join(OUTDIR, "located.jsonl")

DROP = set(("te re dr mr mrs rev elder ruling teaching et al jr sr ii iii the of and "
            "session church churches presbyterian presbytery pca complaint complaints appeal "
            "appeals application reference references petition matter request memorial overture "
            "in from against vs versus v judicial case cases").split())
PREFIX = re.compile(r"^(appeal of|application of|in re|in the matter of|reference of|reference from|"
                    r"judicial reference of|complaint of|complaint against|request for reference from|"
                    r"petition of|the session of|session of|memorial of)\b\s*", re.I)


def name_tokens(side):
    side = PREFIX.sub("", side or "")
    out = []
    for t in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", side.lower()):
        if t in DROP or len(t) <= 2:
            continue
        out.append(t)
    return out


def split_parties(title):
    t = PREFIX.sub("", title or "")
    parts = re.split(r"\bv\.?s?\b|\bvs\b", t, maxsplit=1, flags=re.I)
    left = parts[0] if parts else t
    right = parts[1] if len(parts) > 1 else ""
    return name_tokens(left), name_tokens(right)


def fts_quote(term):
    return '"' + term.replace('"', '') + '"'


# roster decision-locator: "[ M26GA (1998): 222-227]. Sustained, in part 16-0"
LOC = re.compile(r"M\.?\s*(\d{1,2})\s*GA\s*\(\d{4}\)\s*:\s*(\d{1,3})(?:\s*-\s*(\d{1,3}))?", re.I)


def parse_locator(title):
    m = LOC.search(title or "")
    if not m:
        return None
    return {"ga": int(m.group(1)), "printed_page_start": int(m.group(2)),
            "printed_page_end": int(m.group(3)) if m.group(3) else int(m.group(2))}


def search(con, lead, court, docket_year, loc=None):
    """Return ranked candidate pages where a lead token co-occurs with a court token.
    If a roster locator names the decision GA, strongly prefer that volume."""
    if not lead:
        return []
    lead_q = "(" + " OR ".join(fts_quote(t) for t in lead[:4]) + ")"
    q = lead_q
    if court:
        q += " AND (" + " OR ".join(fts_quote(t) for t in court[:4]) + ")"
    try:
        rows = con.execute(
            "SELECT p.vol,p.year,p.pdf_page,p.text FROM pages_fts f "
            "JOIN pages p ON p.page_id=f.rowid WHERE pages_fts MATCH ? LIMIT 400", (q,)).fetchall()
    except sqlite3.OperationalError:
        return []
    loc_ga = loc["ga"] if loc else None
    cand = []
    for vol, year, pg, text in rows:
        tl = (text or "").lower()
        lead_hits = sum(1 for t in lead if t in tl)
        court_hits = sum(1 for t in court if t in tl)
        if lead_hits == 0:
            continue
        m = re.match(r"ga(\d+)_", vol or "")
        vol_ga = int(m.group(1)) if m else None
        # the decision is usually AT or AFTER the docket year (cases take years); only
        # mildly prefer proximity, and STRONGLY prefer the locator's GA volume.
        prox = abs((year or 0) - (docket_year or 0))
        score = lead_hits * 3 + court_hits * 2 - min(prox, 10) * 0.2
        if loc_ga is not None and vol_ga == loc_ga:
            score += 100
        cand.append({"vol": vol, "year": year, "pdf_page": pg, "score": round(score, 1),
                     "lead_hits": lead_hits, "court_hits": court_hits, "prox": prox, "_text": text})
    cand.sort(key=lambda c: -c["score"])
    return cand


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    con = sqlite3.connect(DB)
    miss = [json.loads(l) for l in open(MISSING)]
    ours = [json.loads(l) for l in open(CASES)]
    # existing cases by lead-token for relink detection
    ours_lead = []
    for c in ours:
        ll, _ = split_parties(c.get("title") or "")
        ours_lead.append((set(ll), c))

    located = relink = notfound = 0
    rows = []
    for m in miss:
        title = m.get("title") or ""
        dy = m.get("year")
        lead, court = split_parties(title)
        # relink: an existing case (any year within 3) sharing a lead token + close year
        rl = None
        for ll, c in ours_lead:
            if lead and (set(lead) & ll) and abs((c.get("year") or 0) - (dy or 0)) <= 3:
                rl = c.get("case_id"); break
        loc = parse_locator(title)
        cand = search(con, lead, court, dy, loc)
        best = cand[0] if cand else None
        # "located" needs party + presbytery on the page (court_hits>=1) OR strong party (lead>=2)
        strong = best and (best["court_hits"] >= 1 or best["lead_hits"] >= 2)
        status = "located" if strong else ("relink" if rl else "not_found")
        if status == "located":
            located += 1
        elif status == "relink":
            relink += 1
        else:
            notfound += 1
        rows.append({
            "case_number_raw": m.get("case_number_raw"), "match_key": m.get("match_key"),
            "title": title, "year": dy, "lead": lead, "court": court, "locator": loc,
            "status": status, "relink_case_id": rl,
            "best": ({k: best[k] for k in ("vol", "year", "pdf_page", "score", "lead_hits", "court_hits")}
                     if best else None),
            "candidates": [{k: c[k] for k in ("vol", "pdf_page", "year", "score")} for c in cand[:4]],
        })
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[hunt] {len(miss)} missing roster cases:")
    print(f"        LOCATED in corpus (party+presbytery on a page): {located}")
    print(f"        RELINK to an existing case (divergent number):  {relink}")
    print(f"        NOT FOUND by search:                            {notfound}")
    print(f"        -> {OUT}")


def probe():
    con = sqlite3.connect(DB)
    lead = name_tokens(sys.argv[2]); court = name_tokens(sys.argv[3])
    dy = int(sys.argv[4]) if len(sys.argv) > 4 else None
    for c in search(con, lead, court, dy)[:8]:
        print(f"  {c['vol']} p{c['pdf_page']} ({c['year']}) score={c['score']} lead={c['lead_hits']} court={c['court_hits']}")


if __name__ == "__main__":
    (probe if len(sys.argv) > 1 and sys.argv[1] == "probe" else main)()
