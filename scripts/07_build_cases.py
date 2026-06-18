#!/usr/bin/env python3
"""
07_build_cases.py — roll up judicial decisions into a case-centric index, merging
the freshly-segmented cases (index/segments/*.json) with the already-segmented
sjc_decision / cjb_decision chunks (index/chunks.jsonl).

Outputs:
  index/cases.jsonl          one row per case (SJC or pre-SJC CJB)
  index/case_citations.jsonl precedent edges (from_case -> to_case)

Sources & merge:
  * Segment files carry the rich, per-case structured fields (title, parties,
    disposition, vote, has_dissent, bco_cited_as, precedent_refs, topics,
    synopsis, page span).
  * Decision chunks (section_type in sjc_decision/cjb_decision, plus
    sjc_dissent/sjc_concurrence as add-ons) carry chunk_id provenance, extra
    bco_citations and precedent_cites, and (often) printed-page spans.
  * Records are merged/deduped on the normalized case_number; failing that, on
    (vol + overlapping pdf-page range). When two records merge we keep the richer
    one (more pages / has disposition / came from a report segment) as the base
    and union the bco cites, topics, precedent refs and provenance.

Each as-cited BCO section is mapped to its current number with
bco_concordance.resolve(as_cited, year-of-citation).

v1 = deterministic rollup; LLM synopses for notable cases ride in the segment
files (case.synopsis) and are preserved here.
"""
from __future__ import annotations
import glob
import importlib
import json
import os
import re
import sys
import collections

sys.path.insert(0, "/workspace/scripts")
idx = importlib.import_module("05_index")
conc = importlib.import_module("bco_concordance")

ROOT = "/workspace"
CHUNKS = os.path.join(ROOT, "index", "chunks.jsonl")
SEGDIR = os.path.join(ROOT, "index", "segments")
OUT = os.path.join(ROOT, "index", "cases.jsonl")
EDGES = os.path.join(ROOT, "index", "case_citations.jsonl")

DECISION_TYPES = ("sjc_decision", "cjb_decision")
ADDON_TYPES = ("sjc_dissent", "sjc_concurrence")


# ---------------------------------------------------------------------------
# normalization helpers
# ---------------------------------------------------------------------------
def norm_caseno(s, ga_ordinal=None):
    """Normalize a case number to a canonical id.

    SJC docket-year scheme (GA19+, ~1990 on): 'YY-N' / 'YY-Na' -> '19YY-N' (the
    2-digit year is the docket year). A 4-digit year is kept, with the sequence
    number's leading zeros stripped: '2001-06' -> '2001-6', '2001-06a' kept-suffix.

    Era-style minute-item ids (GA1-17, e.g. '13-34' = a 13th-GA item) and free
    text ('Case 1', 'Complaint No. 2', '93-10b') are preserved verbatim. The
    2-digit expansion is guarded to years >= 85 so a low GA-ordinal prefix
    (e.g. '13-..') is never mis-read as a 1913 docket year.
    """
    if not s:
        return None
    s = str(s).strip()
    # 4-digit docket year: 2001-06[a] -> 2001-6[a]
    m = re.match(r"^(\d{4})-0*(\d{1,3})([a-z]?)$", s, re.I)
    if m:
        return f"{m.group(1)}-{m.group(2)}{m.group(3).lower()}"
    # 2-digit docket year: 90-8 / 92-9a -> 1990-8 / 1992-9a   (only for yy>=85)
    m = re.match(r"^(\d{2})-0*(\d{1,3})([a-z]?)$", s, re.I)
    if m:
        yy = int(m.group(1))
        # don't treat a small GA-ordinal-style prefix as a docket year
        if yy >= 85:
            year = 1900 + yy
            return f"{year}-{m.group(2)}{m.group(3).lower()}"
        # else: keep as an era item-number id, verbatim (zero-strip the seq)
        return f"{yy}-{m.group(2)}{m.group(3).lower()}"
    return s


def looks_like_caseno(cn):
    """Is this a real docket id we can index/dedup on (vs. 'Case 1', '1', None)?"""
    if not cn:
        return False
    return bool(re.match(r"^\d{4}-\d{1,3}[a-z]?$", cn))


SEQ_RE = re.compile(r"^\s*(?:(?:case|complaint|item|reference|no|#)\.?\s*)*#?\s*(\d{1,3})\s*$", re.I)


def synth_caseno(cn_raw, year):
    """The minutes label CJB / early-SJC cases by within-GA sequence ('Case 3'); that
    sequence IS the canonical docket suffix, so 'Case 3' in a 1986 volume -> '1986-3'.
    This matches the PCA Historical Center roster (1986-03) AND gives each case a
    distinct docket key, preventing the numberless page-overlap fallback from
    collapsing several adjacent cases of one report into a single record."""
    if not year:
        return None
    m = SEQ_RE.match(str(cn_raw or ""))
    return f"{int(year)}-{int(m.group(1))}" if m else None


def first_caseno_chunk(chunk):
    for fld in ("sjc", "cjb_case"):
        cns = (chunk.get(fld) or {}).get("case_numbers") or []
        if cns:
            return norm_caseno(cns[0], chunk.get("ga_ordinal"))
    return None


def ga_from_vol(vol):
    m = re.match(r"ga(\d+)_", vol or "")
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# per-volume metadata + printed-page offset (for precedent matching)
# ---------------------------------------------------------------------------
def build_vol_meta(chunks):
    """vol -> {source_pdf, ga_ordinal, year, offset} where offset is the modal
    (pdf_page_start - printed_page_start) so we can derive a printed-page span
    for cases that lack one."""
    pdf = {}
    ga = {}
    yr = {}
    offs = collections.defaultdict(collections.Counter)
    for c in chunks:
        v = c.get("parent_doc")
        if not v:
            continue
        sp = (c.get("source_pdf") or {}).get("file")
        if sp:
            pdf[v] = sp
        if c.get("ga_ordinal") is not None:
            ga[v] = c["ga_ordinal"]
        if c.get("year") is not None:
            yr[v] = c["year"]
        ps, pr = c.get("pdf_page_start"), c.get("printed_page_start")
        try:
            offs[v][int(ps) - int(pr)] += 1
        except (TypeError, ValueError):
            pass
    meta = {}
    for v in set(list(pdf) + list(ga) + list(yr) + list(offs)):
        off = offs[v].most_common(1)[0][0] if offs[v] else None
        meta[v] = {
            "source_pdf": pdf.get(v),
            "ga_ordinal": ga.get(v),
            "year": yr.get(v),
            "offset": off,
        }
    return meta


def _to_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# description extraction (chunk text)
# ---------------------------------------------------------------------------
def description(chunk):
    txt = idx.render_text(chunk) or ""
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    start = 0
    for i, l in enumerate(lines):
        if re.search(r"summary of the facts|statement of the (facts|case)", l, re.I):
            start = i + 1
            break
    snip = " ".join(lines[start:start + 6])
    return re.sub(r"\s+", " ", snip)[:400]


# ---------------------------------------------------------------------------
# record builders — produce a uniform "case record" dict from each source
# ---------------------------------------------------------------------------
def rec_from_segment_case(cs, vol, body, meta):
    """Build a case record from one segment case entry."""
    vm = meta.get(vol, {})
    cn_raw = cs.get("case_number")
    ga = vm.get("ga_ordinal") or ga_from_vol(vol)
    cn = norm_caseno(cn_raw, ga)
    if not looks_like_caseno(cn):                      # 'Case 3' + 1986 -> '1986-3'
        cn = synth_caseno(cn_raw, vm.get("year")) or cn
    parties = cs.get("parties") or {}
    p0 = _to_int(cs.get("pdf_page_start"))
    p1 = _to_int(cs.get("pdf_page_end")) or p0
    pr0 = _to_int(cs.get("printed_page_start"))
    pr1 = _to_int(cs.get("printed_page_end")) or pr0
    # derive printed span from offset if missing
    off = vm.get("offset")
    if pr0 is None and p0 is not None and off is not None:
        pr0 = p0 - off
        pr1 = (p1 - off) if p1 is not None else pr0
    bco_as = list(cs.get("bco_cited_as") or [])
    n_pages = (p1 - p0 + 1) if (p0 is not None and p1 is not None) else 0
    return {
        "case_number": cn,
        "case_number_raw": cn_raw,
        "title": cs.get("title"),
        "parties": parties or None,
        "body": body or vm.get("body"),
        "ga_ordinal": ga,
        "year": vm.get("year"),
        "vol": vol,
        "source_pdf": vm.get("source_pdf"),
        "pdf_page_start": p0,
        "pdf_page_end": p1,
        "printed_page_start": pr0,
        "printed_page_end": pr1,
        "disposition": cs.get("disposition"),
        "vote": cs.get("vote"),
        "has_dissent": bool(cs.get("has_dissent")),
        "bco_as": bco_as,
        "topics": list(cs.get("topics") or []),
        "synopsis": cs.get("synopsis"),
        "precedent_refs_raw": list(cs.get("precedent_refs") or []),
        "description": None,           # filled lazily for the winner only
        # synthetic chunk so render_text can pull description from the segment's
        # own page span (a segment is the richest record but isn't a chunk)
        "_desc_chunk": ({"parent_doc": vol,
                         "pdf_page_start": p0,
                         "pdf_page_end": p1} if p0 is not None else None),
        "chunk_ids": [],
        "window_ids": [cs.get("_window_id")] if cs.get("_window_id") else [],
        "from_segment": True,
        "n_pages": n_pages,
        "_score": 0,
    }


def rec_from_chunk(c, meta):
    vm = meta.get(c.get("parent_doc"), {})
    body = c.get("judicial_body") or (
        "SJC" if str(c.get("section_type", "")).startswith("sjc") else "CJB")
    sub = c.get("sjc") if c.get("section_type") == "sjc_decision" else (c.get("cjb_case") or {})
    sub = sub or {}
    cn = first_caseno_chunk(c)
    if not looks_like_caseno(cn):                      # 'Case 3' + year -> '1986-3'
        cn = synth_caseno((sub.get("case_numbers") or [None])[0], vm.get("year")) or cn
    parties = None
    if (c.get("cjb_case") or {}).get("parties"):
        parties = {"raw": c["cjb_case"]["parties"]}
    p0 = _to_int(c.get("pdf_page_start"))
    p1 = _to_int(c.get("pdf_page_end")) or p0
    pr0 = _to_int(c.get("printed_page_start"))
    pr1 = _to_int(c.get("printed_page_end")) or pr0
    off = vm.get("offset")
    if pr0 is None and p0 is not None and off is not None:
        pr0 = p0 - off
        pr1 = (p1 - off) if p1 is not None else pr0
    n_pages = (p1 - p0 + 1) if (p0 is not None and p1 is not None) else 0
    return {
        "case_number": cn,
        "case_number_raw": (sub.get("case_numbers") or [None])[0],
        "title": c.get("title"),
        "parties": parties,
        "body": body,
        "ga_ordinal": c.get("ga_ordinal"),
        "year": c.get("year"),
        "vol": c.get("parent_doc"),
        "source_pdf": (c.get("source_pdf") or {}).get("file") or vm.get("source_pdf"),
        "pdf_page_start": p0,
        "pdf_page_end": p1,
        "printed_page_start": pr0,
        "printed_page_end": pr1,
        "disposition": sub.get("disposition"),
        "vote": sub.get("vote"),
        "has_dissent": bool(sub.get("has_dissent")),
        "bco_as": list(c.get("bco_citations") or []),
        "topics": [],
        "synopsis": None,
        "precedent_refs_raw": list(sub.get("precedent_cites") or []),
        "description": None,
        "_desc_chunk": c,
        "chunk_ids": [c.get("chunk_id")] if c.get("chunk_id") else [],
        "window_ids": [],
        "from_segment": False,
        "n_pages": n_pages,
        "_score": 0,
    }


def richness(r):
    """Higher = richer / preferred as the merge base."""
    s = 0
    s += r["n_pages"]
    if r["disposition"]:
        s += 50
    if r["from_segment"]:
        s += 200
    if r.get("synopsis"):
        s += 50
    if r.get("topics"):
        s += 20
    if r.get("parties"):
        s += 10
    return s


def merge_into(base, other):
    """Fold `other` into `base` (base is the richer record). Unions list fields,
    backfills scalars, widens page spans."""
    # union list-ish fields
    base["bco_as"] = list(dict.fromkeys(base["bco_as"] + other["bco_as"]))
    base["topics"] = list(dict.fromkeys(base["topics"] + other["topics"]))
    base["precedent_refs_raw"] = list(dict.fromkeys(
        base["precedent_refs_raw"] + other["precedent_refs_raw"]))
    base["chunk_ids"] = list(dict.fromkeys(base["chunk_ids"] + other["chunk_ids"]))
    base["window_ids"] = list(dict.fromkeys(base["window_ids"] + other["window_ids"]))
    base["has_dissent"] = base["has_dissent"] or other["has_dissent"]
    base["from_segment"] = base["from_segment"] or other["from_segment"]
    # backfill scalars the base is missing
    for f in ("title", "parties", "disposition", "vote", "synopsis",
              "case_number", "case_number_raw", "ga_ordinal", "year",
              "source_pdf", "body"):
        if not base.get(f) and other.get(f):
            base[f] = other[f]
    if not base.get("_desc_chunk") and other.get("_desc_chunk"):
        base["_desc_chunk"] = other["_desc_chunk"]
    # Page span: keep the richer base's own span (it's the primary printing of
    # the opinion). Only adopt the other's span when the base has none, or widen
    # within a contiguous span when the two records overlap/abut (same printing
    # split across chunks) — never union two far-apart printings into one giant
    # range. Both spans are still discoverable via provenance.chunk_ids.
    for lo, hi in (("pdf_page_start", "pdf_page_end"),
                   ("printed_page_start", "printed_page_end")):
        b0, b1, o0, o1 = base.get(lo), base.get(hi), other.get(lo), other.get(hi)
        if b0 is None and o0 is not None:
            base[lo], base[hi] = o0, (o1 if o1 is not None else o0)
        elif None not in (b0, b1, o0, o1):
            # contiguous if they overlap or are within 1 page of each other
            if o0 <= b1 + 1 and b0 <= o1 + 1:
                base[lo], base[hi] = min(b0, o0), max(b1, o1)
    base["n_pages"] = (base["pdf_page_end"] - base["pdf_page_start"] + 1) \
        if (base.get("pdf_page_start") is not None and base.get("pdf_page_end") is not None) else base["n_pages"]
    return base


# ---------------------------------------------------------------------------
# precedent-reference resolution
# ---------------------------------------------------------------------------
CASE_TOKEN = re.compile(r"\b(\d{4}-\d{1,3}[a-z]?|\d{2}-\d{1,3}[a-z]?)\b")
# "M10GA ... p.103" / "M14GA, 1986, pp. 103-105" / "Min. 15th G.A. p.480"
MGA = re.compile(r"\bM\s*(\d{1,2})\s*GA\b", re.I)
MIN_ORD = re.compile(r"\bMin\.?\s+(\d{1,2})(?:st|nd|rd|th)\s*G\.?\s*A\.?", re.I)
PAGE = re.compile(r"\bp(?:p|ages?|age|g)?\.?\s*(\d{2,4})", re.I)


def in_range(x, lo, hi):
    return lo is not None and hi is not None and lo <= x <= hi


def resolve_precedents(cases):
    """Resolve each case's precedent_refs_raw into precedent_case_ids and build
    edges. Two matchers: (i) docket-number token; (ii) M{NN}GA + page falling in
    a case's printed-OR-pdf page span. Unresolved refs stay in precedent_refs_raw.
    """
    by_num = {}
    for c in cases:
        if looks_like_caseno(c["case_number"]):
            by_num[c["case_number"]] = c["case_id"]
    # index cases by ga_ordinal for the page-anchored matcher
    by_ga = collections.defaultdict(list)
    for c in cases:
        if c.get("ga_ordinal") is not None:
            by_ga[c["ga_ordinal"]].append(c)

    edges = []
    for c in cases:
        ids = set()
        for raw in c["precedent_refs_raw"]:
            # (i) docket-number token
            for m in CASE_TOKEN.findall(raw):
                cid = norm_caseno(m, c.get("ga_ordinal"))
                if cid in by_num and by_num[cid] != c["case_id"]:
                    ids.add(by_num[cid])
            # (ii) M{NN}GA p.X  (printed page anchored)
            mga = MGA.search(raw) or MIN_ORD.search(raw)
            if mga:
                ga = int(mga.group(1))
                pages = [int(p) for p in PAGE.findall(raw)]
                for cand in by_ga.get(ga, []):
                    if cand["case_id"] == c["case_id"]:
                        continue
                    for pg in pages:
                        if in_range(pg, cand.get("printed_page_start"), cand.get("printed_page_end")) \
                           or in_range(pg, cand.get("pdf_page_start"), cand.get("pdf_page_end")):
                            ids.add(cand["case_id"])
                            break
        c["precedent_case_ids"] = sorted(ids)
        for t in ids:
            edges.append({"from": c["case_id"], "to": t})

    cb = collections.defaultdict(set)
    for e in edges:
        cb[e["to"]].add(e["from"])
    for c in cases:
        c["cited_by"] = sorted(cb.get(c["case_id"], []))
    return edges


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    chunks = [json.loads(l) for l in open(CHUNKS) if l.strip()]
    corr = idx.load_citation_corrections()
    for c in chunks:
        idx.apply_citation_corrections(c, corr)
    meta = build_vol_meta(chunks)

    records = []

    # --- source 1: segment files ---
    seg_body = {}
    for path in sorted(glob.glob(os.path.join(SEGDIR, "*.json"))):
        d = json.load(open(path))
        vol = d.get("vol")
        body = d.get("body")
        wid = d.get("window_id")
        for cs in d.get("cases") or []:
            cs = dict(cs)
            cs["_window_id"] = wid
            records.append(rec_from_segment_case(cs, vol, body, meta))

    # --- source 2: decision chunks (+ dissent/concurrence add-ons) ---
    decisions = [c for c in chunks if c.get("section_type") in DECISION_TYPES]
    addons = [c for c in chunks if c.get("section_type") in ADDON_TYPES]
    for c in decisions:
        records.append(rec_from_chunk(c, meta))

    # --- dedup/merge ---
    # pass 1: bucket by normalized real case_number
    by_num = collections.defaultdict(list)
    no_num = []
    for r in records:
        if looks_like_caseno(r["case_number"]):
            by_num[r["case_number"]].append(r)
        else:
            no_num.append(r)

    merged = []
    for cn, group in by_num.items():
        # An SJC docket 'YYYY-N' is decided within ~3 years of its docket year.
        # A decision chunk from a much later GA carrying this docket number is a
        # precedent QUOTATION inside a later opinion (its OCR'd title is
        # "Case YYYY-N: <quoted text>"), not the primary record — it would
        # pollute the page span / text. Keep only the closest year-cluster; the
        # quotations still feed the citation graph via the citing case's refs.
        docket_year = int(cn[:4])

        def year_gap(r):
            return abs((r.get("year") or docket_year) - docket_year)

        min_gap = min(year_gap(r) for r in group)
        primary = [r for r in group if year_gap(r) <= max(min_gap, 0) + 1]
        primary.sort(key=richness, reverse=True)
        base = primary[0]
        for other in primary[1:]:
            merge_into(base, other)
        merged.append(base)

    # pass 2: numberless records -> merge by (vol + overlapping pdf-page range)
    # keep them separate from the numbered ones (they have no docket id to match)
    no_num.sort(key=richness, reverse=True)
    placed = []
    for r in no_num:
        hit = None
        for p in placed:
            if p["vol"] != r["vol"]:
                continue
            if r.get("pdf_page_start") is None or p.get("pdf_page_start") is None:
                continue
            # overlap test
            if r["pdf_page_start"] <= p["pdf_page_end"] and p["pdf_page_start"] <= r["pdf_page_end"]:
                hit = p
                break
        if hit:
            merge_into(hit, r)
        else:
            placed.append(r)
    merged.extend(placed)

    # --- assign case_id, resolve BCO, finalize description ---
    cases = []
    for r in merged:
        cn = r["case_number"]
        if looks_like_caseno(cn):
            cid = cn
        else:
            cid = f"{r['vol']}:p{r.get('pdf_page_start')}"
        yr = r.get("year")
        bco_cited_as, bco_cited_current = [], []
        ch_as, ch_cur = set(), set()
        seen = set()
        for cite in r["bco_as"]:
            if not cite or cite in seen:
                continue
            seen.add(cite)
            bco_cited_as.append(cite)
            ch_as.add(str(cite).split("-")[0])
            cur = cite
            if yr:
                try:
                    cur, _ = conc.resolve(cite, yr)
                except Exception:
                    cur = cite
            if cur not in bco_cited_current:
                bco_cited_current.append(cur)
            ch_cur.add(str(cur).split("-")[0])
        desc = None
        if r.get("_desc_chunk"):
            desc = description(r["_desc_chunk"])
        cases.append({
            "case_id": cid,
            "case_number": cn if looks_like_caseno(cn) else (cn or None),
            "title": r.get("title"),
            "parties": r.get("parties"),
            "body": r.get("body"),
            "ga_ordinal": r.get("ga_ordinal"),
            "year": yr,
            "pdf_page_start": r.get("pdf_page_start"),
            "pdf_page_end": r.get("pdf_page_end"),
            "printed_page_start": r.get("printed_page_start"),
            "printed_page_end": r.get("printed_page_end"),
            "source_pdf": r.get("source_pdf"),
            "disposition": r.get("disposition"),
            "vote": r.get("vote"),
            "has_dissent": bool(r.get("has_dissent")),
            "bco_cited_as": bco_cited_as,
            "bco_cited_current": bco_cited_current,
            "bco_chapters_ascited": sorted(ch_as, key=lambda x: (len(x), x)),
            "bco_chapters_current": sorted(ch_cur, key=lambda x: (len(x), x)),
            "topics": r.get("topics") or [],
            "synopsis": r.get("synopsis"),
            "description": desc,
            "precedent_refs_raw": r.get("precedent_refs_raw") or [],
            "precedent_case_ids": [],
            "cited_by": [],
            "provenance": {
                "chunk_ids": r.get("chunk_ids") or [],
                "window_ids": r.get("window_ids") or [],
            },
        })

    # dedup case_ids that collide on the numberless fallback key (rare)
    seen_ids = {}
    for c in cases:
        cid = c["case_id"]
        if cid in seen_ids:
            n = 2
            while f"{cid}#{n}" in seen_ids:
                n += 1
            cid = f"{cid}#{n}"
            c["case_id"] = cid
        seen_ids[cid] = c

    # --- precedent edges ---
    edges = resolve_precedents(cases)

    cases.sort(key=lambda c: (c.get("ga_ordinal") or 0, str(c.get("case_id"))))
    with open(OUT, "w") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(EDGES, "w") as f:
        for e in edges:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    n_sjc = sum(1 for c in cases if c["body"] == "SJC")
    n_cjb = sum(1 for c in cases if c["body"] == "CJB")
    print(f"[cases] {len(cases)} cases -> {OUT}")
    print(f"        body: SJC={n_sjc} CJB={n_cjb}")
    print(f"        with case_number: {sum(1 for c in cases if c['case_number'])}; "
          f"with disposition: {sum(1 for c in cases if c['disposition'])}; "
          f"with bco_cited_current: {sum(1 for c in cases if c['bco_cited_current'])}")
    print(f"        precedent edges: {len(edges)} -> {EDGES}; "
          f"cases cited_by>=1: {sum(1 for c in cases if c['cited_by'])}")

    # --- auxiliary source: hunt-recovered roster cases (NOT golden) ---
    # The golden sources above are the segmentation output + stage-04 decision chunks.
    # index/hunt/found/*.json holds cases recovered by the roster hunt (Haiku) plus a few
    # manually confirmed from the minutes. They are a keeper, so a single `07` run folds
    # them back in (via 11_merge_hunt) and reproduces the full index on rebuild. Tagged
    # aux_source=true so they stay distinguishable from golden. Skip with --golden-only.
    found_dir = os.path.join("/workspace", "index", "hunt", "found")
    if "--golden-only" not in sys.argv and glob.glob(found_dir + "/*.json"):
        print(f"        [aux] folding {len(glob.glob(found_dir + '/*.json'))} hunt-recovered "
              f"cases (auxiliary, not golden) via 11_merge_hunt ...")
        importlib.import_module("11_merge_hunt").main()


if __name__ == "__main__":
    main()
