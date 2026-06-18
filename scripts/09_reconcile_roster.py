#!/usr/bin/env python3
"""
09_reconcile_roster.py — reconcile our corpus-extracted case index
(index/cases.jsonl) against the PCA Historical Center's authoritative SJC roster
(index/sjc_official/roster.jsonl). The roster is GROUND TRUTH: every case it lists
should be findable in our conversions.

Produces:
  - coverage stats: matched / missing-from-ours / extra-in-ours
  - index/sjc_official/missing.jsonl   official cases we did NOT extract (the hunt list)
  - (with --enrich) rewrites index/cases.jsonl: matched cases gain canonical_title +
    official_pdf_url + official_year; official cases we missed are added as stub rows
    (source="official_roster_only", needs_location=true) so a search still resolves the
    canonical identity and points to where to look.

CLI:  09_reconcile_roster.py            # report coverage only
      09_reconcile_roster.py --enrich   # also enrich/stub cases.jsonl
"""
from __future__ import annotations
import json, os, re, sys, collections, difflib

ROOT = "/workspace"
ROSTER = os.path.join(ROOT, "index", "sjc_official", "roster.jsonl")
CASES = os.path.join(ROOT, "index", "cases.jsonl")
MISSING = os.path.join(ROOT, "index", "sjc_official", "missing.jsonl")


def norm(raw):
    """Canonical match key: '1990-08'/'1990-8'->'1990-8'; keep a/b; combos->first."""
    if not raw:
        return None
    m = re.match(r"^(\d{4})-(\d{1,3})([ab]?)", str(raw))
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3)}"


def base_key(cid):
    """Suffix-insensitive fallback key (1992-9a -> 1992-9)."""
    m = re.match(r"^(\d{4})-(\d+)", cid or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


# The minutes label cases by an internal sequence ("Case #3"), NOT the canonical
# "1986-03" the Historical Center assigns — but the sequence IS the canonical NN.
# So a case's candidate canonical keys derive from (volume year + that sequence),
# from a 2-digit-year number (90-8), or from an already-canonical number.
def our_keys(c):
    """Exactly ONE canonical key per case (a docket number resolves itself; only a
    non-docket label like 'Case 3' is synthesized from the volume year)."""
    yr = c.get("year")
    cn = str(c.get("case_number") or "")
    m4 = re.match(r"^(\d{4})-(\d{1,3})([ab]?)$", cn)             # 1986-03 / 2018-12
    if m4:
        return {f"{m4.group(1)}-{int(m4.group(2))}{m4.group(3)}"}
    m2 = re.match(r"^(\d{2})-(\d{1,3})$", cn)                    # 90-8
    if m2:
        yy = int(m2.group(1)); y = 1900 + yy if yy >= 50 else 2000 + yy
        return {f"{y}-{int(m2.group(2))}"}
    m = re.search(r"(?:case\s*#?\s*)?(\d{1,3})\s*$", cn, re.I)   # "Case 3" / "3"
    if m and yr:
        return {f"{yr}-{int(m.group(1))}"}
    return set()


STOP = set(("v vs versus presbytery of the a session complaint appeal appellant "
            "complainant respondent re te ruling teaching elder et al jr sr ii iii "
            "church pca reference judicial case from in matter application and amp "
            "dr mr mrs rev").split())


def toks(*parts):
    s = " ".join(p for p in parts if p).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return {w for w in s.split() if w not in STOP and len(w) > 2}


def case_toks(c):
    p = c.get("parties") or {}
    return toks(c.get("title"), c.get("canonical_title"),
               *(str(v) for v in p.values()) if isinstance(p, dict) else [])


def load(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def load_from_segments():
    """Test/standalone mode: synthesize proto-cases straight from index/segments/*.json."""
    import glob
    out = []
    for fp in glob.glob(os.path.join(ROOT, "index", "segments", "*.json")):
        try:
            d = json.load(open(fp))
        except Exception:
            continue
        vol = d.get("vol", "")
        ym = re.search(r"_(\d{4})", vol)
        year = int(ym.group(1)) if ym else None
        for c in d.get("cases", []):
            c = dict(c)
            c.setdefault("year", year)
            out.append(c)
    return out


def split_title(title):
    """Split 'Knight v. Palmetto Presbytery' -> (lead/complainant toks, court toks)."""
    parts = re.split(r"\bv\.?s?\b|\bvs\b", title or "", maxsplit=1, flags=re.I)
    left = parts[0] if parts else (title or "")
    right = parts[1] if len(parts) > 1 else ""
    return toks(left), toks(right)


def case_party_toks(c):
    """(complainant toks, court toks) for one of OUR cases — from the parties dict
    when it has distinct fields, else by splitting the title."""
    p = c.get("parties")
    if isinstance(p, dict) and not p.get("raw"):
        lead = toks(*[str(v) for k, v in p.items() if "compl" in k.lower() or "appell" in k.lower()])
        court = toks(*[str(v) for k, v in p.items() if "resp" in k.lower() or "court" in k.lower()])
        if lead or court:
            return lead, court
    return split_title(c.get("title") or "")


# distinct-presbytery qualifier: "Philadelphia" vs "Philadelphia Metro West" must NOT be
# conflated. Kept deliberately narrow to {metro,metropolitan} — broader sets (valley,
# directions) cause false conflicts on abbreviations ("MS Valley"~"Mississippi Valley",
# "NW Georgia"~"Northwest Georgia"), which over-reject legitimate matches.
COURT_QUAL = {"metro", "metropolitan"}


def fuzzy_share(a, b):
    """True if either token-set is empty (no info to contradict), they share a token,
    or any cross pair is OCR-close (Levenshtein-ish ratio)."""
    if not a or not b:
        return True
    if a & b:
        return True
    return fuzzy_pair(a, b)


def fuzzy_pair(a, b):
    """True if some cross pair of tokens is OCR-close (e.g. McCready~McCreedy,
    Bjork~Bjorck). Both sets must be non-empty (unlike fuzzy_share)."""
    return any(len(x) > 3 and len(y) > 3 and difflib.SequenceMatcher(None, x, y).ratio() >= 0.86
               for x in a for y in b)


def court_conflict(a, b):
    """Two named courts are different presbyteries if their token diff carries a
    geographic qualifier one side lacks (Philadelphia vs Philadelphia Metro West)."""
    if not a or not b:
        return False
    return bool(((a - b) | (b - a)) & COURT_QUAL)


def main():
    enrich = "--enrich" in sys.argv
    roster = load(ROSTER)
    cases = load_from_segments() if "--from-segments" in sys.argv else load(CASES)
    ros_by = {}
    for r in roster:
        k = norm(r.get("case_number") or r.get("case_number_raw"))
        if k:
            ros_by[k] = r

    # index our cases by every candidate canonical key, and keep a per-year list for
    # party-name fallback matching
    ours_key_idx = {}
    ours_by_year = collections.defaultdict(list)
    for c in cases:
        for k in our_keys(c):
            ours_key_idx.setdefault(k, c)
        if c.get("year"):
            ours_by_year[c["year"]].append(c)

    matched, missing = [], []
    used = set()

    # pass 1 — KEY matches (year+seq / canonical / 2-digit docket), but CONFIRMED by
    # party: a number alone is not enough — the parties must not contradict (guards
    # against synthesized-sequence != official-docket, e.g. our 1988-3 != roster 1988-03)
    name_pool = []
    for k, r in ros_by.items():
        hit = ours_key_idx.get(k)
        if hit and id(hit) not in used:
            # a hunt-merged case already carries the authoritative roster number (set by
            # 11 from the seed that found it) — trust that link without re-checking parties,
            # since its primary title is now the minutes caption, which may differ from the roster
            if hit.get("canonical_number") and norm(hit.get("canonical_number")) == k:
                matched.append((k, r, hit, "hunt")); used.add(id(hit))
                continue
            r_lead, r_court = split_title(r.get("title"))
            c_lead, c_court = case_party_toks(hit)
            if fuzzy_share(r_lead, c_lead) and not court_conflict(r_court, c_court):
                matched.append((k, r, hit, "key")); used.add(id(hit))
                continue
        name_pool.append((k, r))

    # pass 2 — party-name fallback: require COMPLAINANT-surname overlap (fuzzy, not just
    # the shared presbytery), no court conflict, total >=2 tokens, +/-1 year, 1:1
    for k, r in name_pool:
        ry = r.get("year")
        r_lead, r_court = split_title(r.get("title"))
        best, bscore = None, 0
        for yy in (ry, (ry or 0) - 1, (ry or 0) + 1):
            for c in ours_by_year.get(yy, []):
                if id(c) in used:
                    continue
                c_lead, c_court = case_party_toks(c)
                if not r_lead or not c_lead:
                    continue
                exact = len(r_lead & c_lead)
                fz = fuzzy_pair(r_lead, c_lead)          # McCready~McCreedy, Bjork~Bjorck
                if not exact and not fz:
                    continue
                if court_conflict(r_court, c_court):
                    continue
                tot = exact * 2 + (1 if (fz and not exact) else 0) + len(r_court & c_court)
                if tot > bscore:
                    best, bscore = c, tot
        if best and bscore >= 2:
            matched.append((k, r, best, f"name({bscore})")); used.add(id(best))
        else:
            missing.append((k, r, None, None))

    extra = [c for c in cases if id(c) not in used and our_keys(c)]

    n_ros, n_ours = len(ros_by), len(cases)
    by_how = collections.Counter(how for *_, how in matched)
    print(f"[reconcile] official roster: {n_ros} SJC cases (uniq numbers) | our index: {n_ours} cases")
    print(f"            MATCHED (official found in ours): {len(matched)}/{n_ros} "
          f"= {100*len(matched)//max(n_ros,1)}%   (by {dict(by_how)})")
    print(f"            MISSING (official NOT in ours):   {len(missing)}")
    print(f"            EXTRA   (ours not in official; pre-1975 CJB / unmatched): {len(extra)}")

    # missing by decade for triage
    bydec = collections.Counter()
    for k, r, _, _ in missing:
        bydec[r.get("decade_page", "?")] += 1
    if missing:
        print("            missing by decade: " + ", ".join(f"{d}:{n}" for d, n in sorted(bydec.items())))
        with open(MISSING, "w") as f:
            for k, r, _, _ in sorted(missing, key=lambda x: x[0]):
                f.write(json.dumps({**r, "match_key": k}, ensure_ascii=False) + "\n")
        print(f"            -> hunt list written: {MISSING}")
        print("            sample misses:")
        for k, r, _, _ in sorted(missing, key=lambda x: x[0])[:12]:
            print(f"              {r.get('case_number_raw'):12} {r.get('title','')[:60]}")

    if enrich and cases:
        for k, r, hit, _ in matched:
            hit["canonical_number"] = r.get("case_number_raw")
            hit["canonical_title"] = r.get("title")
            hit["official_pdf_url"] = r.get("pdf_url")
            hit["official_year"] = r.get("year")
            hit["in_official_roster"] = True
        stubs = 0
        for k, r, _, _ in (missing if "--stubs" in sys.argv else []):
            cases.append({
                "case_id": k, "case_number": k, "case_number_raw": r.get("case_number_raw"),
                "title": r.get("title"), "canonical_title": r.get("title"),
                "body": "SJC", "year": r.get("year"),
                "official_pdf_url": r.get("pdf_url"), "in_official_roster": True,
                "source": "official_roster_only", "needs_location": True,
                "synopsis": None, "bco_cited_as": [], "bco_cited_current": [],
                "topics": [], "precedent_case_ids": [], "cited_by": [],
            })
            stubs += 1
        with open(CASES, "w") as f:
            for c in cases:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"            ENRICHED {len(matched)} matched cases; added {stubs} roster stubs -> {CASES}")
        print("            (re-run scripts/08_index_cases.py build to refresh the lookup table)")


if __name__ == "__main__":
    main()
