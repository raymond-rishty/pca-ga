#!/usr/bin/env python3
"""
08_index_cases.py — add a case-lookup layer to index/pca_minutes.db.

Reads index/cases.jsonl (produced by 07_build_cases.py) and builds:
  * table  `cases`      one row per case + facet columns for cheap membership
                        tests (space-delimited `*_s` scalars for LIKE).
  * table  `cases_fts`  FTS5 over title, parties, description, synopsis, topics
                        so name/topic queries hit.

A find(con, query) resolver returns matching case row(s), trying in order:
  1. exact / normalized docket case-number               ("90-8" -> 1990-8)
  2. BCO section OR chapter against EITHER the as-cited OR the current facets
     (so "24-5" AND "24-6" both resolve to Bowen)
  3. FTS over title / parties / topics / description / synopsis
     (so "Bowen" and "limited atonement" resolve)

CLI:
  08_index_cases.py build
  08_index_cases.py find "<query>"
"""
from __future__ import annotations
import importlib
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, "/workspace/scripts")
build_cases = importlib.import_module("07_build_cases")
norm_caseno = build_cases.norm_caseno
looks_like_caseno = build_cases.looks_like_caseno

ROOT = "/workspace"
CASES = os.path.join(ROOT, "index", "cases.jsonl")
DB_PATH = os.path.join(ROOT, "index", "pca_minutes.db")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def scalarize(values):
    """Space-pad a list -> ' a b c ' so ` x ` IN col substring tests are exact."""
    vals = [str(v) for v in (values or []) if v is not None and str(v) != ""]
    if not vals:
        return ""
    return " " + " ".join(vals) + " "


def party_text(parties):
    """Flatten the parties object into a single searchable string."""
    if not parties:
        return ""
    if "raw" in parties:
        return parties.get("raw") or ""
    return " ".join(str(v) for v in parties.values() if v)


_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-\.]+")


def party_tokens(parties):
    """Surname-ish tokens for cheap party-name membership (lowercased)."""
    txt = party_text(parties)
    toks = [t.lower().strip(".'-") for t in _TOKEN.findall(txt)]
    # drop connective noise
    stop = {"v", "vs", "the", "of", "and", "et", "al", "presbytery", "church",
            "session", "in", "no", "complaint", "appeal", "re"}
    return [t for t in toks if t and t not in stop and len(t) > 1]


def connect(db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
DDL = """
DROP TABLE IF EXISTS cases_fts;
DROP TABLE IF EXISTS cases;

CREATE TABLE cases (
    rowid               INTEGER PRIMARY KEY,
    case_id             TEXT,
    case_number         TEXT,
    case_number_norm    TEXT,    -- normalized docket id (for exact lookup)
    canonical_number      TEXT,  -- authoritative roster docket number (when matched)
    canonical_number_norm TEXT,  -- normalized; takes priority in docket lookup
    title               TEXT,
    parties             TEXT,    -- flattened searchable string
    party_tokens        TEXT,    -- space-delimited lowercased surname tokens
    party_tokens_s      TEXT,    -- ' ' wrapped for exact LIKE membership
    body                TEXT,    -- 'SJC' | 'CJB'
    ga_ordinal          INTEGER,
    year                INTEGER,
    source_pdf          TEXT,
    pdf_page_start      INTEGER,
    pdf_page_end        INTEGER,
    printed_page_start  INTEGER,
    printed_page_end    INTEGER,
    disposition         TEXT,
    vote                TEXT,
    has_dissent         INTEGER,
    -- BCO facets: JSON blob + ' ' wrapped scalar for membership LIKE tests
    bco_cited_as          TEXT,
    bco_cited_as_s        TEXT,
    bco_cited_current     TEXT,
    bco_cited_current_s   TEXT,
    bco_chapters_ascited  TEXT,
    bco_chapters_ascited_s TEXT,
    bco_chapters_current  TEXT,
    bco_chapters_current_s TEXT,
    -- topics
    topics              TEXT,
    topics_s            TEXT,
    synopsis            TEXT,
    description         TEXT,
    -- citation graph
    precedent_case_ids  TEXT,
    cited_by            TEXT,
    precedent_refs_raw  TEXT,
    provenance          TEXT
);

CREATE VIRTUAL TABLE cases_fts USING fts5(
    title,
    parties,
    description,
    synopsis,
    topics,
    content='cases',
    content_rowid='rowid',
    tokenize='porter unicode61'
);
"""


def build(db_path=DB_PATH):
    if not os.path.exists(CASES):
        print(f"[error] {CASES} not found — run 07_build_cases.py first.", file=sys.stderr)
        sys.exit(1)
    cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
    con = connect(db_path)
    con.executescript(DDL)
    rows = []
    fts_rows = []
    for i, c in enumerate(cases, start=1):
        ptxt = party_text(c.get("parties"))
        ptok = party_tokens(c.get("parties"))
        topics = c.get("topics") or []
        rows.append((
            i,
            c.get("case_id"),
            c.get("case_number"),
            norm_caseno(c.get("case_number"), c.get("ga_ordinal")) if c.get("case_number") else None,
            c.get("canonical_number"),
            norm_caseno(c.get("canonical_number"), c.get("ga_ordinal")) if c.get("canonical_number") else None,
            c.get("title"),
            ptxt,
            " ".join(ptok),
            scalarize(ptok),
            c.get("body"),
            c.get("ga_ordinal"),
            c.get("year"),
            c.get("source_pdf"),
            c.get("pdf_page_start"),
            c.get("pdf_page_end"),
            c.get("printed_page_start"),
            c.get("printed_page_end"),
            c.get("disposition"),
            c.get("vote"),
            1 if c.get("has_dissent") else 0,
            json.dumps(c.get("bco_cited_as") or [], ensure_ascii=False),
            scalarize(c.get("bco_cited_as")),
            json.dumps(c.get("bco_cited_current") or [], ensure_ascii=False),
            scalarize(c.get("bco_cited_current")),
            json.dumps(c.get("bco_chapters_ascited") or [], ensure_ascii=False),
            scalarize(c.get("bco_chapters_ascited")),
            json.dumps(c.get("bco_chapters_current") or [], ensure_ascii=False),
            scalarize(c.get("bco_chapters_current")),
            json.dumps(topics, ensure_ascii=False),
            scalarize(topics),
            c.get("synopsis"),
            c.get("description"),
            json.dumps(c.get("precedent_case_ids") or [], ensure_ascii=False),
            json.dumps(c.get("cited_by") or [], ensure_ascii=False),
            json.dumps(c.get("precedent_refs_raw") or [], ensure_ascii=False),
            json.dumps(c.get("provenance") or {}, ensure_ascii=False),
        ))
        # fold the canonical (roster) title into the FTS title so the official spelling
        # also hits (e.g. roster "McCreedy" finds our minutes-spelled "McCready")
        ct = c.get("canonical_title")
        fts_title = (c.get("title") or "") + ((" " + ct) if ct and ct != c.get("title") else "")
        fts_rows.append((i, fts_title, ptxt,
                         c.get("description") or "", c.get("synopsis") or "",
                         " ".join(topics)))
    ncols = len(rows[0]) if rows else 35
    con.executemany(
        "INSERT INTO cases VALUES (" + ",".join("?" * ncols) + ")", rows)
    con.executemany(
        "INSERT INTO cases_fts(rowid,title,parties,description,synopsis,topics) "
        "VALUES (?,?,?,?,?,?)", fts_rows)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    n_sjc = con.execute("SELECT COUNT(*) FROM cases WHERE body='SJC'").fetchone()[0]
    n_cjb = con.execute("SELECT COUNT(*) FROM cases WHERE body='CJB'").fetchone()[0]
    n_num = con.execute("SELECT COUNT(*) FROM cases WHERE case_number IS NOT NULL").fetchone()[0]
    print(f"[index] {n} cases -> {db_path} (table `cases` + `cases_fts`)")
    print(f"        SJC={n_sjc} CJB={n_cjb}; with case_number={n_num}")
    con.close()


# ---------------------------------------------------------------------------
# find resolver
# ---------------------------------------------------------------------------
def _rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


# a bare BCO section ("24-5") or chapter ("24"); guard against docket ids
BCO_SECTION = re.compile(r"^\d{1,2}-\d{1,2}([.\-]\w+)*$")
BCO_CHAPTER = re.compile(r"^\d{1,2}$")
DOCKET = re.compile(r"^\d{4}-\d{1,3}[a-z]?$|^\d{2}-\d{1,3}[a-z]?$")


def find(con, query):
    """Resolve a free-text query to matching case row(s). Returns a list of dicts
    annotated with a `_match` reason. Tries docket-number, then BCO
    section/chapter (as-cited OR current), then FTS — stopping at the first
    tier that yields hits."""
    q = (query or "").strip()
    if not q:
        return []

    # Strip a leading "BCO"/"B.C.O." label so "BCO 24-5" enters the BCO-section
    # tier exactly like the bare "24-5" form does. (Docket ids never carry this
    # prefix, so tier 1 is unaffected.)
    q = re.sub(r"^b\.?\s*c\.?\s*o\.?\s+", "", q, flags=re.IGNORECASE).strip() or q

    # ---- tier 1: docket case-number (exact / normalized) ----
    if DOCKET.match(q):
        norm = norm_caseno(q)
        # the authoritative roster (canonical) number wins over our synthesized one, so a
        # query for the official docket resolves to the right case even when our number diverged
        hits = _rows(con, "SELECT * FROM cases WHERE canonical_number_norm=?", (norm,))
        for h in hits:
            h["_match"] = f"canonical_number={norm}"
        if not hits:
            hits = _rows(con,
                         "SELECT * FROM cases WHERE case_number_norm=? OR case_number=? OR case_id=?",
                         (norm, q, norm))
            for h in hits:
                h["_match"] = f"case_number={norm}"
        if hits:
            return hits

    # ---- tier 2: BCO section or chapter, as-cited OR current ----
    if BCO_SECTION.match(q) or BCO_CHAPTER.match(q):
        token = q
        like = f"% {token} %"
        if BCO_SECTION.match(q):
            hits = _rows(con,
                         "SELECT * FROM cases WHERE bco_cited_as_s LIKE ? "
                         "OR bco_cited_current_s LIKE ? ORDER BY ga_ordinal, case_id",
                         (like, like))
            reason = f"bco_section {token} (as-cited or current)"
        else:  # chapter
            hits = _rows(con,
                         "SELECT * FROM cases WHERE bco_chapters_ascited_s LIKE ? "
                         "OR bco_chapters_current_s LIKE ? ORDER BY ga_ordinal, case_id",
                         (like, like))
            reason = f"bco_chapter {token} (as-cited or current)"
        if hits:
            for h in hits:
                h["_match"] = reason
            return hits

    # ---- tier 3: FTS over title / parties / topics / description / synopsis ----
    fts_q = _fts_query(q)
    try:
        hits = _rows(con,
                     "SELECT c.*, bm25(cases_fts) AS _rank FROM cases_fts "
                     "JOIN cases c ON c.rowid=cases_fts.rowid "
                     "WHERE cases_fts MATCH ? ORDER BY _rank",
                     (fts_q,))
    except sqlite3.OperationalError:
        hits = []
    for h in hits:
        h["_match"] = f"fts:{fts_q}"
    return hits


def _fts_query(q):
    """Turn a natural query into an FTS5 MATCH expr: quote bare terms, AND them.
    A multi-word phrase like 'limited atonement' is searched both as a phrase and
    as ANDed terms (phrase ranked first by bm25)."""
    terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", q)
    if not terms:
        return '""'
    if len(terms) > 1:
        phrase = '"' + " ".join(terms) + '"'
        anded = " AND ".join(f'"{t}"' for t in terms)
        return f"({phrase}) OR ({anded})"
    return f'"{terms[0]}"'


def _fmt(h):
    cn = h.get("case_number") or h.get("case_id")
    parts = [f"[{cn}] {h.get('title') or ''}".rstrip()]
    meta = []
    if h.get("body"):
        meta.append(h["body"])
    if h.get("ga_ordinal"):
        meta.append(f"GA{h['ga_ordinal']}/{h.get('year')}")
    if h.get("disposition"):
        meta.append(h["disposition"])
    if meta:
        parts.append("   " + " · ".join(meta))
    if h.get("_match"):
        parts.append(f"   match: {h['_match']}")
    bco_cur = json.loads(h.get("bco_cited_current") or "[]")
    if bco_cur:
        parts.append("   BCO (current): " + ", ".join(bco_cur[:12]) +
                     (" …" if len(bco_cur) > 12 else ""))
    topics = json.loads(h.get("topics") or "[]")
    if topics:
        parts.append("   topics: " + ", ".join(topics[:8]) +
                     (" …" if len(topics) > 8 else ""))
    return "\n".join(parts)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "build":
        build()
    elif cmd == "find":
        if len(sys.argv) < 3:
            print("usage: 08_index_cases.py find \"<query>\"", file=sys.stderr)
            sys.exit(2)
        con = connect()
        hits = find(con, " ".join(sys.argv[2:]))
        if not hits:
            print("(no match)")
            return
        print(f"{len(hits)} match(es):\n")
        for h in hits[:25]:
            print(_fmt(h))
            print()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
