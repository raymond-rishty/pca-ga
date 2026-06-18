#!/usr/bin/env python3
"""
11_merge_hunt.py — fold hunt results (index/hunt/found/*.json) into the case index.
Each found case carries its canonical identity from the official roster; we add it as a
real case record (decision) or a findable mention (mention_only/withdrawn), resolve its
BCO cites to current numbers, and dedup against cases already present. Run AFTER 07.

Pipeline:  07_build_cases.py  ->  11_merge_hunt.py  ->  09_reconcile_roster.py --enrich  ->  08_index_cases.py build

CLI:  11_merge_hunt.py            # merge found/*.json into cases.jsonl
"""
from __future__ import annotations
import glob, importlib, json, os, re, sys

sys.path.insert(0, "/workspace/scripts")
conc = importlib.import_module("bco_concordance")
rec09 = importlib.import_module("09_reconcile_roster")

ROOT = "/workspace"
CASES = ROOT + "/index/cases.jsonl"
FOUND = ROOT + "/index/hunt/found"
ROSTER = ROOT + "/index/sjc_official/roster.jsonl"

DISP = re.compile(r"(sustained in part|not sustained|administratively out of order|"
                  r"declared invalid|deemed abandoned|sustained|dismissed|withdrawn|denied|"
                  r"granted|rendered moot|out of order|abandoned|invalid)", re.I)


def roster_disposition(title):
    """The roster title often states the disposition after the citation bracket."""
    tail = title.split("]")[-1] if "]" in title else title
    m = DISP.search(tail) or DISP.search(title)
    return m.group(1).lower().replace(" ", "_") if m else None


def body_for(year):
    return "CJB" if (year or 9999) <= 1987 else "SJC"


# a real caption either has a "v."/"vs" party separator, or STARTS with a case-type word
CAP_VS = re.compile(r"\bv\.?\s|\bvs\.?\s", re.I)
CAP_START = re.compile(r"(?i)^(complaint|reference|appeal|petition|session|request|"
                       r"in re|memorial|judicial reference|application)\b")


def minutes_caption(vol, cn_raw):
    """Find the case's caption AS PRINTED in the minutes (authoritative title), by
    scanning the volume for a line that starts with the docket number and reads like a
    caption. Returns None if not found (caller falls back to the roster title)."""
    if not vol or not cn_raw:
        return None
    m = re.match(r"(\d{4})-(\d{1,3}[a-z]?)", cn_raw)
    nums = [cn_raw]
    if m:
        nums.append(f"{m.group(1)[2:]}-{m.group(2)}")        # 2002-15 -> 02-15
    pat = re.compile(r"^(?:\d{1,3}\.\s*)?(?:Case\s*(?:No\.?)?\s*)?(?:%s)[\.\):]?\s+(.+)$"
                     % "|".join(re.escape(n) for n in nums), re.I)
    best = None
    try:
        for l in open(f"{ROOT}/build/page_jsonl/{vol}.pages.jsonl"):
            r = json.loads(l)
            for line in r.get("text", "").split("\n"):
                mm = pat.match(line.strip())
                if mm and (CAP_VS.search(mm.group(1)) or CAP_START.match(mm.group(1).strip())):
                    cap = re.sub(r"\s+", " ", mm.group(1)).strip().rstrip(".")
                    cap = re.sub(r"\s*\[.*$", "", cap)        # drop trailing citation bracket
                    if not best or len(cap) > len(best):
                        best = cap[:200]
    except FileNotFoundError:
        return None
    return best


def build_ga_vol_map():
    """ga_ordinal -> canonical vol string (from the page_jsonl filenames)."""
    out = {}
    for fp in glob.glob(ROOT + "/build/page_jsonl/ga*_*.pages.jsonl"):
        b = os.path.basename(fp)
        m = re.match(r"(ga(\d+)_\d{4})", b)
        if m:
            out[int(m.group(2))] = m.group(1)
    return out


def main():
    roster = {}
    if os.path.exists(ROSTER):
        roster = {rec09.norm(r.get("case_number") or r.get("case_number_raw")): r
                  for r in (json.loads(l) for l in open(ROSTER))}
    cases = [json.loads(l) for l in open(CASES)]
    gavol = build_ga_vol_map()

    def norm_vol(v):
        """'ga30_2002' kept; Haiku's 'GA30'/'30'/'GA 30' -> 'ga30_2002'."""
        if not v:
            return None
        if re.match(r"ga\d+_\d{4}$", v):
            return v
        m = re.search(r"(\d{1,2})", v)
        return gavol.get(int(m.group(1))) if m else None

    have = {}                                  # canonical key -> existing case obj
    for c in cases:
        for k in rec09.our_keys(c):
            have.setdefault(k, c)

    found = []
    for fp in glob.glob(FOUND + "/*.json"):
        try:
            found.append(json.load(open(fp)))
        except Exception:
            pass

    added = skipped = mentions = demoted = 0
    for f in found:
        cn = f.get("case_number")
        key = rec09.norm(cn)
        if not key:
            continue
        ros = roster.get(key, {})
        if key in have:
            ex = have[key]
            # does the case already at this docket key actually match the roster? (same
            # test the reconciler uses, so 11 and 09 agree on what counts as a match)
            r_lead, r_court = rec09.split_title(ros.get("title") or "")
            e_lead, e_court = rec09.case_party_toks(ex)
            if (rec09.fuzzy_share(r_lead, e_lead) and (r_lead & e_lead or not r_lead)
                    and not rec09.court_conflict(r_court, e_court)):
                skipped += 1                   # existing record is the right case -> keep it
                continue
            # collision: existing case is mis-numbered (divergent synth). The roster +
            # located decision is authoritative -> demote the existing record to numberless.
            ex["case_id"] = f"{ex.get('vol') or (ex.get('source_pdf') or '').replace('.pdf','')}:p{ex.get('pdf_page_start')}"
            ex["case_number"] = None
            ex["renumbered_from"] = key
            demoted += 1
        vol = norm_vol(f.get("vol"))
        year = None
        m = re.match(r"ga\d+_(\d{4})", vol or "")
        if m:
            year = int(m.group(1))
        ga = None
        mg = re.match(r"ga(\d+)_", vol or "")
        if mg:
            ga = int(mg.group(1))
        bco_as = [re.sub(r"^bco\s*", "", b, flags=re.I).strip() for b in (f.get("bco_cited_as") or [])]
        bco_cur, chap_cur = [], set()
        for b in bco_as:
            cur, _ = conc.resolve(b, year) if year else (b, [])
            bco_cur.append(cur); chap_cur.add(cur.split("-")[0])
        status = f.get("status")
        rec = {
            "case_id": key, "case_number": key,
            "case_number_raw": cn,
            "canonical_number": ros.get("case_number_raw"),
            "canonical_title": ros.get("title"),       # roster title -> searchable alias
            "official_pdf_url": ros.get("pdf_url"),
            # minutes caption wins as the primary title; fall back to the roster title
            "title": minutes_caption(vol, cn) or ros.get("title") or vol,
            "body": body_for(year), "ga_ordinal": ga, "year": year,
            "source_pdf": (vol or "") + ".pdf",
            "pdf_page_start": f.get("pdf_page_start"), "pdf_page_end": f.get("pdf_page_end"),
            "disposition": roster_disposition(ros.get("title") or "") or f.get("disposition"),
            "vote": f.get("vote"), "has_dissent": bool(f.get("has_dissent")),
            "bco_cited_as": bco_as, "bco_cited_current": bco_cur,
            "bco_chapters_ascited": sorted({b.split("-")[0] for b in bco_as}),
            "bco_chapters_current": sorted(chap_cur),
            "topics": f.get("topics") or [], "synopsis": f.get("synopsis"),
            "precedent_refs_raw": [], "precedent_case_ids": [], "cited_by": [],
            "in_official_roster": True, "source": "hunt:" + (status or "?"),
            "aux_source": True,            # auxiliary (hunt-recovered), NOT a golden segment/chunk
            "needs_location": status != "decision",
            "provenance": {"hunt_vol": f.get("vol")},
        }
        cases.append(rec)
        have[key] = rec
        added += 1
        if status != "decision":
            mentions += 1

    with open(CASES, "w") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"[merge-hunt] found={len(found)}  added={added} (mention/withdrawn={mentions})  "
          f"skipped-correct={skipped}  demoted-misnumbered={demoted}")
    print(f"             cases.jsonl now {len(cases)} rows")


if __name__ == "__main__":
    main()
