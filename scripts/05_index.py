#!/usr/bin/env python3
"""
Phase 5, Stage 1 — Search layer.

Loads index/chunks.jsonl into a portable SQLite FTS5 database at
index/pca_minutes.db. One `.db`, no daemon.

Two complementary layers
-------------------------
  STRUCTURED OVERLAY (`sections` / `sections_fts`) — the SJC/CCB/judicial
  faceted layer: one row per *named* citable section, with facet columns
  (section_type, judicial_body, bco_chapters, sjc/cjb/ccb fields, …). Use this
  for faceted / structured / interpretive-history search.

  FULL-TEXT BASE LAYER (`pages` / `pages_fts`) — the safety net: one row per
  pdf_page from every build/page_jsonl/<vol>.pages.jsonl, so EVERY page with
  text is full-text searchable, including pages that fall between or outside
  named sections (appendices, rosters, statistics, floor minutes the section
  chunker never bracketed). Use this for guaranteed 100% coverage. The two
  layers are independent: the page layer never depends on the chunker.

Schema
------
  sections        : content table — one row per indexed section. Holds the
                    rendered section text (reconstructed from the per-page
                    SOURCE OF TRUTH build/page_jsonl/<vol>.pages.jsonl) plus
                    sibling/facet columns for faceted filtering and, crucially,
                    the columns needed to ALWAYS emit a resolvable citation
                    (ga_ordinal + page_range + a ga_item id).
  sections_fts    : FTS5 virtual table (tokenize="porter unicode61") over the
                    section text + title, external-content-linked to `sections`
                    via rowid. BM25 ranking, snippet()/highlight() supported.
  pages           : content table — one row per pdf_page that has text, from
                    every build/page_jsonl/<vol>.pages.jsonl (the SOURCE OF
                    TRUTH). Columns: page_id, vol, ga_ordinal, year, pdf_page,
                    printed_page, char_count, engine, text. The full-text base
                    layer — 100% page coverage, independent of the chunker.
  pages_fts       : FTS5 virtual table (tokenize="porter unicode61") over
                    pages.text, external-content-linked to `pages` via rowid.

Citability invariant (schema + query enforced)
-----------------------------------------------
A row that lacks BOTH ga_ordinal AND a non-empty page_range is NOT citable.
Such rows are still loaded (so FTS recall is complete) but flagged citable=0,
and the query helper refuses to return non-citable rows by default. Every
returned hit carries .citation = "GA <ord> (<year>), p.<range> [item <id>]".

Usage
-----
  build:   05_index.py build            (idempotent; skips if up-to-date)
           05_index.py build --force    (rebuild from scratch)
  query:   05_index.py query "BCO 34" --section-type sjc_decision --limit 10
  bco34:   05_index.py bco34            (FLAGSHIP: interpretive history of BCO 34)
  test:    05_index.py test             (20-query known-answer set + flagship)
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time

ROOT = "/workspace"
CHUNKS = os.path.join(ROOT, "index", "chunks.jsonl")
DB_PATH = os.path.join(ROOT, "index", "pca_minutes.db")
PAGE_JSONL_DIR = os.path.join(ROOT, "build", "page_jsonl")
CITATION_CORRECTIONS = os.path.join(ROOT, "index", "citation_corrections.jsonl")

# Facet columns that live as JSON arrays in chunks.jsonl. We store them both as
# a JSON text blob (for round-trip) and as a space-padded scalar string so the
# substring match `' 34 ' IN bco_chapters_s` works in plain SQL without json1.
LIST_FIELDS = [
    "ga_item_ids", "bco_chapters", "bco_citations", "rao_citations",
    "wcf_citations", "scripture_refs", "overtures", "cross_refs",
    "sjc_case_numbers", "cjb_case_numbers",
]

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE sections (
    rowid            INTEGER PRIMARY KEY,
    chunk_id         TEXT,
    parent_doc       TEXT,
    source_file      TEXT,
    source_sha256    TEXT,
    ga_ordinal       INTEGER,
    year             INTEGER,
    era              TEXT,
    section_type     TEXT,
    judicial_body    TEXT,      -- unified facet: 'CJB' (pre-SJC) | 'SJC' | NULL
    committee        TEXT,
    title            TEXT,
    appendix         TEXT,
    pdf_page_start   INTEGER,
    pdf_page_end     INTEGER,
    printed_page_start TEXT,
    printed_page_end   TEXT,
    page_range       TEXT,
    -- list facets: JSON blob + space-delimited scalar for cheap membership tests
    ga_item_ids      TEXT,
    ga_item_ids_s    TEXT,
    bco_chapters     TEXT,
    bco_chapters_s   TEXT,
    bco_citations    TEXT,
    bco_citations_s  TEXT,
    rao_citations    TEXT,
    wcf_citations    TEXT,
    scripture_refs   TEXT,
    overtures        TEXT,
    overtures_s      TEXT,
    cross_refs       TEXT,
    -- SJC / CCB structured fields
    sjc_case_numbers   TEXT,
    sjc_case_numbers_s TEXT,
    sjc_disposition    TEXT,
    sjc_has_dissent    INTEGER,
    sjc_has_concurrence INTEGER,
    ccb_verdicts       TEXT,
    ccb_verdicts_s     TEXT,
    -- pre-SJC CJB structured fields (judicial_body='CJB')
    cjb_case_numbers   TEXT,
    cjb_case_numbers_s TEXT,
    cjb_disposition    TEXT,
    cjb_parties        TEXT,
    -- QC / provenance
    char_count       INTEGER,
    qc_verdicts      TEXT,
    confidence       REAL,
    citable          INTEGER,   -- 1 iff ga_ordinal present AND page_range non-empty
    text             TEXT
);

CREATE INDEX idx_sections_type     ON sections(section_type);
CREATE INDEX idx_sections_ga       ON sections(ga_ordinal);
CREATE INDEX idx_sections_committee ON sections(committee);
CREATE INDEX idx_sections_citable  ON sections(citable);
CREATE INDEX idx_sections_jbody    ON sections(judicial_body);

CREATE VIRTUAL TABLE sections_fts USING fts5(
    text,
    title,
    content='sections',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- FULL-TEXT BASE LAYER: one row per pdf_page that has text (the safety net).
-- Guarantees 100% page coverage independent of the section chunker.
CREATE TABLE pages (
    page_id       INTEGER PRIMARY KEY,   -- == FTS rowid
    vol           TEXT,                  -- e.g. 'ga16_1988'
    ga_ordinal    INTEGER,
    year          INTEGER,
    pdf_page      INTEGER,               -- 1-based page in the source PDF
    printed_page  TEXT,                  -- printed/book page number (may be NULL)
    char_count    INTEGER,
    engine        TEXT,                  -- ocr engine / 'embedded'
    source_file   TEXT,                  -- bare PDF filename for citation
    text          TEXT
);

CREATE INDEX idx_pages_vol      ON pages(vol);
CREATE INDEX idx_pages_ga       ON pages(ga_ordinal);
CREATE UNIQUE INDEX idx_pages_volpage ON pages(vol, pdf_page);

CREATE VIRTUAL TABLE pages_fts USING fts5(
    text,
    content='pages',
    content_rowid='page_id',
    tokenize='porter unicode61'
);
"""


# --------------------------------------------------------------------------- #
# Text reconstruction from the per-page SOURCE OF TRUTH                        #
# --------------------------------------------------------------------------- #
_PAGE_CACHE = {}


def list_volumes():
    """Return sorted list of volume ids that have a page_jsonl file."""
    import glob
    out = []
    for p in glob.glob(os.path.join(PAGE_JSONL_DIR, "*.pages.jsonl")):
        out.append(os.path.basename(p)[: -len(".pages.jsonl")])
    return sorted(out)


def iter_volume_page_rows(vol):
    """Yield the full per-page JSONL row dicts for a volume (source of truth)."""
    path = os.path.join(PAGE_JSONL_DIR, f"{vol}.pages.jsonl")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_volume_pages(vol):
    """Return {pdf_page: text} for a volume, cached."""
    if vol in _PAGE_CACHE:
        return _PAGE_CACHE[vol]
    pages = {}
    for row in iter_volume_page_rows(vol):
        pages[int(row["pdf_page"])] = row.get("text", "") or ""
    _PAGE_CACHE[vol] = pages
    return pages


def render_text(chunk):
    """Reconstruct a chunk's text from its pdf_page span (source of truth)."""
    vol = chunk["parent_doc"]
    pages = load_volume_pages(vol)
    p0 = chunk.get("pdf_page_start")
    p1 = chunk.get("pdf_page_end")
    if p0 is None:
        return ""
    if p1 is None:
        p1 = p0
    parts = []
    for p in range(int(p0), int(p1) + 1):
        t = pages.get(p)
        if t:
            parts.append(t)
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Facet flattening                                                            #
# --------------------------------------------------------------------------- #
def scalarize(values):
    """Space-pad a list -> ' a b c ' so ` x ` IN col substring tests are exact."""
    vals = [str(v) for v in (values or []) if v is not None and str(v) != ""]
    if not vals:
        return ""
    return " " + " ".join(vals) + " "


def citation_for(row):
    """Build the always-resolvable citation string for a result row.

    Invariant: requires ga_ordinal + page_range. Adds the first ga_item id when
    present (mid/early scanned SJC cases frequently lack item ids — those still
    cite by GA+page, which is resolvable to the source PDF page)."""
    ga = row["ga_ordinal"]
    year = row["year"]
    pr = row["page_range"]
    pp_start = row["printed_page_start"]
    items = json.loads(row["ga_item_ids"]) if row["ga_item_ids"] else []
    cite = f"GA {ga} ({year}), pp.{pr}"
    if pp_start:
        cite += f" (printed p.{pp_start})"
    if items:
        cite += f" [item {items[0]}]"
    cite += f" — {row['source_file']}#pdfpage{row['pdf_page_start']}"
    return cite


def page_citation_for(row):
    """Resolvable citation for a `pages`-layer hit: GA + pdf page + printed page.

    The page layer is the full-text safety net, so it cites by PHYSICAL location
    (GA ordinal + PDF page, the source of truth) rather than by section item id.
    The printed/book page is added when known."""
    ga = row["ga_ordinal"]
    year = row["year"]
    pp = row["pdf_page"]
    printed = row["printed_page"]
    cite = f"GA {ga} ({year}), pdf p.{pp}"
    if printed not in (None, "", "None"):
        cite += f" (printed p.{printed})"
    cite += f" — {row['source_file']}#pdfpage{pp}"
    return cite


# --------------------------------------------------------------------------- #
# Build                                                                       #
# --------------------------------------------------------------------------- #
def chunks_mtime():
    return os.path.getmtime(CHUNKS)


def db_is_current(con):
    try:
        cur = con.execute("SELECT value FROM meta WHERE key='chunks_mtime'")
        r = cur.fetchone()
        if not r:
            return False
        return abs(float(r[0]) - chunks_mtime()) < 1e-6
    except sqlite3.Error:
        return False


def load_citation_corrections():
    """Curated citation-normalization overlay. The markdown stays VERBATIM to the
    source (typos and all); this overlay lets the INDEX carry the canonical BCO
    cite so a mis-typed citation is still findable. Returns
    {vol: [(pdf_page, chapter, full_cite)]}. Entries with no canonical_bco
    (source typo with no recoverable target) are skipped."""
    out = {}
    if not os.path.exists(CITATION_CORRECTIONS):
        return out
    with open(CITATION_CORRECTIONS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            can = r.get("canonical_bco")
            if not can:
                continue
            chapter = str(can).split("-")[0]
            out.setdefault(r["vol"], []).append((int(r["pdf_page"]), chapter, str(can)))
    return out


def apply_citation_corrections(c, corrections):
    """Add the canonical chapter + full cite to a chunk's BCO facets when a
    correction's page falls within the chunk's page range. Text is untouched.
    Returns the number of cites injected."""
    items = corrections.get(c.get("parent_doc"))
    if not items:
        return 0
    p0, p1 = c.get("pdf_page_start"), c.get("pdf_page_end")
    if not isinstance(p0, int) or not isinstance(p1, int):
        return 0
    chs = list(c.get("bco_chapters") or [])
    cits = list(c.get("bco_citations") or [])
    added = 0
    for pg, chapter, full in items:
        if p0 <= pg <= p1:
            if chapter not in chs:
                chs.append(chapter)
            if full not in cits:
                cits.append(full)
                added += 1
    c["bco_chapters"], c["bco_citations"] = chs, cits
    return added


def build(force=False):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH) and not force:
        con = sqlite3.connect(DB_PATH)
        if db_is_current(con):
            n = con.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
            con.close()
            print(f"[skip] {DB_PATH} already current ({n} sections). Use --force to rebuild.")
            return n
        con.close()

    tmp = DB_PATH + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)

    t0 = time.time()
    n_total = 0
    n_citable = 0
    n_noncitable = 0
    rowid = 0
    rows = []
    corrections = load_citation_corrections()
    n_corr = 0
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            n_corr += apply_citation_corrections(c, corrections)
            rowid += 1
            n_total += 1

            ga = c.get("ga_ordinal")
            pr = c.get("page_range")
            citable = 1 if (ga is not None and pr not in (None, "", [])) else 0
            if citable:
                n_citable += 1
            else:
                n_noncitable += 1

            sjc = c.get("sjc") or {}
            ccb = c.get("ccb") or {}
            cjb = c.get("cjb_case") or {}
            sjc_cases = sjc.get("case_numbers") or []
            ccb_verds = ccb.get("verdicts") or []
            cjb_cases = cjb.get("case_numbers") or []
            src = c.get("source_pdf") or {}

            text = render_text(c)

            rows.append((
                rowid,
                c.get("chunk_id"),
                c.get("parent_doc"),
                src.get("file"),
                src.get("sha256"),
                ga,
                c.get("year"),
                c.get("era"),
                c.get("section_type"),
                c.get("judicial_body"),
                c.get("committee"),
                c.get("title"),
                c.get("appendix"),
                c.get("pdf_page_start"),
                c.get("pdf_page_end"),
                (str(c["printed_page_start"]) if c.get("printed_page_start") is not None else None),
                (str(c["printed_page_end"]) if c.get("printed_page_end") is not None else None),
                pr,
                json.dumps(c.get("ga_item_ids") or []),
                scalarize(c.get("ga_item_ids")),
                json.dumps(c.get("bco_chapters") or []),
                scalarize(c.get("bco_chapters")),
                json.dumps(c.get("bco_citations") or []),
                scalarize(c.get("bco_citations")),
                json.dumps(c.get("rao_citations") or []),
                json.dumps(c.get("wcf_citations") or []),
                json.dumps(c.get("scripture_refs") or []),
                json.dumps(c.get("overtures") or []),
                scalarize(c.get("overtures")),
                json.dumps(c.get("cross_refs") or []),
                json.dumps(sjc_cases),
                scalarize(sjc_cases),
                sjc.get("disposition"),
                1 if sjc.get("has_dissent") else 0,
                1 if sjc.get("has_concurrence") else 0,
                json.dumps(ccb_verds),
                scalarize(ccb_verds),
                json.dumps(cjb_cases),
                scalarize(cjb_cases),
                cjb.get("disposition"),
                cjb.get("parties"),
                c.get("char_count"),
                json.dumps(c.get("qc_verdicts") or []),
                c.get("confidence"),
                citable,
                text,
            ))

    con.executemany(
        "INSERT INTO sections VALUES (%s)" % ",".join(["?"] * 46), rows
    )
    # Build the FTS index from the content table.
    con.execute(
        "INSERT INTO sections_fts(rowid, text, title) "
        "SELECT rowid, text, title FROM sections"
    )
    con.execute("INSERT INTO sections_fts(sections_fts) VALUES('optimize')")

    # FULL-TEXT BASE LAYER — one row per pdf_page with text (the safety net).
    n_pages, n_blank = build_pages_layer(con)

    con.execute("INSERT INTO meta(key,value) VALUES('chunks_mtime',?)",
                (str(chunks_mtime()),))
    con.execute("INSERT INTO meta(key,value) VALUES('built_at',?)",
                (time.strftime("%Y-%m-%dT%H:%M:%S"),))
    con.execute("INSERT INTO meta(key,value) VALUES('sections_total',?)",
                (str(n_total),))
    con.execute("INSERT INTO meta(key,value) VALUES('sections_citable',?)",
                (str(n_citable),))
    con.execute("INSERT INTO meta(key,value) VALUES('pages_total',?)",
                (str(n_pages),))
    con.execute("INSERT INTO meta(key,value) VALUES('pages_blank_skipped',?)",
                (str(n_blank),))
    con.commit()
    con.close()
    os.replace(tmp, DB_PATH)
    dt = time.time() - t0
    print(f"[build] {n_total} sections ({n_citable} citable, {n_noncitable} non-citable) "
          f"-> {DB_PATH} in {dt:.1f}s")
    print(f"[build] pages base layer: {n_pages} pages indexed "
          f"({n_blank} truly-blank pages skipped)")
    print(f"[build] citation-correction overlay: {n_corr} canonical cite(s) injected into facets")
    return n_total


def build_pages_layer(con):
    """Populate `pages` + `pages_fts` from every build/page_jsonl/<vol>.pages.jsonl.

    One row per pdf_page that has text. A page is indexed iff its text is
    non-empty after stripping (truly-blank pages — char_count 0 / no text — are
    skipped; they have nothing to match). This is the full-text safety net that
    guarantees 100% coverage of pages with text, independent of the chunker.

    Idempotent: called only against the freshly-created build DB (within build()).
    Returns (n_pages_indexed, n_blank_skipped).
    """
    # Map vol -> bare PDF filename (for citations). Prefer the value the
    # sections layer already recorded; fall back to the original PDF on disk.
    src_by_vol = {}
    for vol, sf in con.execute(
            "SELECT DISTINCT parent_doc, source_file FROM sections "
            "WHERE source_file IS NOT NULL"):
        if vol and sf:
            src_by_vol.setdefault(vol, sf)

    page_id = 0
    n_pages = 0
    n_blank = 0
    batch = []
    for vol in list_volumes():
        src = src_by_vol.get(vol) or _pdf_filename_fallback(vol)
        for row in iter_volume_page_rows(vol):
            text = row.get("text") or ""
            if not text.strip():
                n_blank += 1
                continue
            page_id += 1
            n_pages += 1
            printed = row.get("printed_page")
            batch.append((
                page_id,
                row.get("vol") or vol,
                row.get("ga_ordinal"),
                row.get("year"),
                int(row["pdf_page"]),
                (str(printed) if printed is not None else None),
                row.get("char_count"),
                row.get("engine"),
                src,
                text,
            ))
            if len(batch) >= 2000:
                con.executemany("INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?,?)",
                                batch)
                batch = []
    if batch:
        con.executemany("INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?,?)", batch)

    con.execute(
        "INSERT INTO pages_fts(rowid, text) SELECT page_id, text FROM pages")
    con.execute("INSERT INTO pages_fts(pages_fts) VALUES('optimize')")
    return n_pages, n_blank


def _pdf_filename_fallback(vol):
    """Best-effort bare PDF filename for a vol when sections recorded none.

    Derives from the year suffix (e.g. ga16_1988 -> *_1988.pdf) under
    /workspace/minutes; returns '<vol>.pdf' if no match."""
    import glob
    m = re.search(r"_(\d{4})$", vol)
    if m:
        hits = glob.glob(os.path.join(ROOT, "minutes", f"*_{m.group(1)}.pdf"))
        if hits:
            return os.path.basename(hits[0])
    return f"{vol}.pdf"


# --------------------------------------------------------------------------- #
# Query helper                                                                #
# --------------------------------------------------------------------------- #
SELECT_COLS = (
    "s.rowid, s.chunk_id, s.ga_ordinal, s.year, s.era, s.section_type, "
    "s.judicial_body, s.committee, s.title, s.appendix, s.page_range, "
    "s.pdf_page_start, s.printed_page_start, s.ga_item_ids, s.bco_chapters, "
    "s.sjc_case_numbers, s.sjc_disposition, s.ccb_verdicts, "
    "s.cjb_case_numbers, s.cjb_disposition, s.cjb_parties, "
    "s.source_file, s.confidence, s.citable"
)


def _rowdict(cur, r):
    return {d[0].split(".")[-1] if "." in d[0] else d[0]: r[i]
            for i, d in enumerate(cur.description)}


def connect(db_path=DB_PATH):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def search(con, match=None, *, section_type=None, judicial_body=None,
           committee=None, ga_ordinal=None, bco_chapter=None, sjc_disposition=None,
           ccb_verdict=None, sjc_case=None, cjb_case=None, overture=None,
           require_citable=True, order="bm25", limit=20):
    """BM25-ranked search returning hits with snippet() and resolvable citation.

    `match` is an FTS5 MATCH expression (None = pure facet filter, ordered by
    ga_ordinal, pdf_page_start). All other args are facet filters. When
    require_citable (default), only rows with ga_ordinal+page_range are returned.

    `judicial_body` ('CJB' | 'SJC') is the UNIFIED judicial facet: it spans the
    full 1973-2025 judicial history regardless of section_type, so a single
    query can pull pre-SJC Committee-on-Judicial-Business units and modern
    Standing-Judicial-Commission units together.
    """
    where = []
    params = []
    joins = ""
    snippet_expr = "NULL"
    if match:
        joins = "JOIN sections_fts f ON f.rowid = s.rowid"
        where.append("sections_fts MATCH ?")
        params.append(match)
        snippet_expr = "snippet(sections_fts, 0, '[', ']', ' … ', 12)"
    if section_type:
        where.append("s.section_type = ?")
        params.append(section_type)
    if judicial_body:
        where.append("s.judicial_body = ?")
        params.append(judicial_body)
    if committee:
        where.append("s.committee = ?")
        params.append(committee)
    if ga_ordinal is not None:
        where.append("s.ga_ordinal = ?")
        params.append(ga_ordinal)
    if bco_chapter is not None:
        where.append("s.bco_chapters_s LIKE ?")
        params.append(f"% {bco_chapter} %")
    if sjc_disposition:
        where.append("s.sjc_disposition = ?")
        params.append(sjc_disposition)
    if ccb_verdict:
        where.append("s.ccb_verdicts_s LIKE ?")
        params.append(f"% {ccb_verdict} %")
    if sjc_case:
        where.append("s.sjc_case_numbers_s LIKE ?")
        params.append(f"% {sjc_case} %")
    if cjb_case:
        where.append("s.cjb_case_numbers_s LIKE ?")
        params.append(f"% {cjb_case} %")
    if overture:
        where.append("s.overtures_s LIKE ?")
        params.append(f"% {overture} %")
    if require_citable:
        where.append("s.citable = 1")

    if order == "bm25" and match:
        orderby = "bm25(sections_fts)"
    elif order == "chrono":
        orderby = "s.ga_ordinal, s.pdf_page_start"
    else:
        orderby = "s.ga_ordinal, s.pdf_page_start"

    sql = (
        f"SELECT {SELECT_COLS}, {snippet_expr} AS snippet "
        f"FROM sections s {joins} "
        + ("WHERE " + " AND ".join(where) if where else "")
        + f" ORDER BY {orderby} LIMIT ?"
    )
    params.append(limit)
    cur = con.execute(sql, params)
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["citation"] = citation_for(r)
        out.append(d)
    return out


PAGE_SELECT_COLS = (
    "p.page_id, p.vol, p.ga_ordinal, p.year, p.pdf_page, p.printed_page, "
    "p.char_count, p.engine, p.source_file"
)


def search_pages(con, match=None, *, vol=None, ga_ordinal=None, year=None,
                 order="bm25", limit=20):
    """FULL-TEXT BASE-LAYER search over the per-page `pages` table.

    This is the guaranteed-coverage safety net: it searches EVERY page that has
    text, including pages outside named sections that the structured `sections`
    layer never covered. Use `search()` for faceted/structured queries; use this
    for full corpus recall.

    `match` is an FTS5 MATCH expression (None = pure facet/scan, ordered by
    ga_ordinal, pdf_page). Optional filters: `vol` (e.g. 'ga16_1988'),
    `ga_ordinal`, `year`. Returns dicts with a `snippet` (when `match` is given)
    and a resolvable `citation` (GA ordinal + pdf page + printed page)."""
    where = []
    params = []
    joins = ""
    snippet_expr = "NULL"
    if match:
        joins = "JOIN pages_fts f ON f.rowid = p.page_id"
        where.append("pages_fts MATCH ?")
        params.append(match)
        snippet_expr = "snippet(pages_fts, 0, '[', ']', ' … ', 14)"
    if vol:
        where.append("p.vol = ?")
        params.append(vol)
    if ga_ordinal is not None:
        where.append("p.ga_ordinal = ?")
        params.append(ga_ordinal)
    if year is not None:
        where.append("p.year = ?")
        params.append(year)

    if order == "bm25" and match:
        orderby = "bm25(pages_fts)"
    else:
        orderby = "p.ga_ordinal, p.pdf_page"

    sql = (
        f"SELECT {PAGE_SELECT_COLS}, {snippet_expr} AS snippet "
        f"FROM pages p {joins} "
        + ("WHERE " + " AND ".join(where) if where else "")
        + f" ORDER BY {orderby} LIMIT ?"
    )
    params.append(limit)
    cur = con.execute(sql, params)
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["citation"] = page_citation_for(r)
        out.append(d)
    return out


def judicial_history(con, bco_chapter=None, limit=200):
    """UNIFIED judicial interpretive-history query spanning the FULL 1973-2025
    record. Returns pre-SJC CJB units (judicial_body='CJB': cjb_report,
    cjb_decision — the General Assembly acting as the court, GAs 1-17) AND modern
    SJC units (judicial_body='SJC': sjc_decision/dissent/concurrence) plus the
    CCB constitutional-advice units, all interleaved CHRONOLOGICALLY (ga_ordinal,
    pdf page) and each citable to GA+page[+item]. This is the key path that makes
    constitutional-interpretation search span the whole history, not just
    post-SJC: a CJB complaint adjudicated by the 5th GA (1977) and an SJC decision
    of the 49th GA (2022) appear in one chronological list.

    When bco_chapter is given, restricts to units whose bco_chapters contains it
    (dual-indexed, so chapter 34 catches 34, 34-1, 34-3, ...).
    """
    where = ["s.citable = 1",
             "(s.judicial_body IS NOT NULL "
             " OR s.section_type IN ('ccb_overture_advice','ccb_minute_review') "
             " OR (s.section_type = 'committee_report' "
             "     AND s.committee IN ('constitutional_business','judicial_business')))"]
    params = []
    if bco_chapter is not None:
        where.append("s.bco_chapters_s LIKE ?")
        params.append(f"% {bco_chapter} %")
    sql = ("SELECT %s, NULL AS snippet FROM sections s WHERE "
           % SELECT_COLS) + " AND ".join(where) + \
        " ORDER BY s.ga_ordinal, s.pdf_page_start LIMIT ?"
    params.append(limit)
    cur = con.execute(sql, params)
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d["citation"] = citation_for(r)
        out.append(d)
    return out


def bco34_history(con, limit=15):
    """FLAGSHIP: chronological interpretive history of BCO 34 across ALL GAs,
    pre-SJC CJB and modern SJC + CCB interleaved, each citable to GA+page+item.
    Thin wrapper over the unified judicial_history() path with bco_chapter=34."""
    return judicial_history(con, bco_chapter=34, limit=limit)


def fmt_hit(h, with_snippet=True):
    body = f"{h['judicial_body']}/" if h["judicial_body"] else ""
    line = (f"  GA{h['ga_ordinal']:>2} ({h['year']}) "
            f"{body}{h['section_type']:<20} p.{h['page_range']:<9} "
            f"{(h['title'] or '')[:50]}")
    extra = []
    cn = json.loads(h["sjc_case_numbers"]) if h["sjc_case_numbers"] else []
    if cn:
        extra.append("case " + ",".join(cn))
    if h["sjc_disposition"]:
        extra.append(h["sjc_disposition"])
    # pre-SJC CJB structured fields
    ccn = json.loads(h["cjb_case_numbers"]) if h["cjb_case_numbers"] else []
    if ccn:
        extra.append("cjb " + ",".join(ccn))
    if h["cjb_disposition"]:
        extra.append(h["cjb_disposition"])
    cv = json.loads(h["ccb_verdicts"]) if h["ccb_verdicts"] else []
    if cv:
        extra.append("ccb:" + ",".join(cv))
    if extra:
        line += "  [" + " ".join(extra) + "]"
    out = [line, "      cite: " + h["citation"]]
    if with_snippet and h.get("snippet"):
        sn = re.sub(r"\s+", " ", h["snippet"]).strip()
        out.append("      …" + sn[:160])
    return "\n".join(out)


def fmt_page_hit(h, with_snippet=True):
    line = (f"  GA{h['ga_ordinal']:>2} ({h['year']}) "
            f"pdf p.{h['pdf_page']:<4} "
            f"printed p.{str(h['printed_page'] or '-'):<6} "
            f"[{h['vol']}] {h['char_count']}ch {h['engine'] or ''}")
    out = [line, "      cite: " + h["citation"]]
    if with_snippet and h.get("snippet"):
        sn = re.sub(r"\s+", " ", h["snippet"]).strip()
        out.append("      …" + sn[:180])
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# 20-query known-answer set                                                    #
# --------------------------------------------------------------------------- #
def known_answer_set(con):
    """Return list of (name, callable->rows, expectation_fn->bool, note)."""
    tests = []

    def add(name, fn, expect, note=""):
        tests.append((name, fn, expect, note))

    # 1. All SJC decisions touching BCO 34, chronological.
    add("sjc_decisions_bco34_chrono",
        lambda: search(con, section_type="sjc_decision", bco_chapter=34,
                       order="chrono", limit=200),
        lambda rows: len(rows) >= 10,
        "SJC decisions citing BCO ch.34, ordered (ga_ordinal,page)")

    # 2. CCB units that found an overture in conflict.
    add("ccb_in_conflict",
        lambda: search(con, ccb_verdict="in_conflict", order="chrono", limit=200),
        lambda rows: len(rows) >= 5,
        "CCB units with verdict in_conflict")

    # 3. CCB in_conflict mentioning BCO 34 specifically.
    add("ccb_in_conflict_bco34",
        lambda: search(con, ccb_verdict="in_conflict", bco_chapter=34, limit=200),
        lambda rows: len(rows) >= 1,
        "CCB in_conflict touching BCO 34")

    # 4. SJC decisions ruled sustained.
    add("sjc_sustained",
        lambda: search(con, section_type="sjc_decision",
                       sjc_disposition="sustained", limit=200),
        lambda rows: len(rows) >= 5,
        "SJC decisions disposition=sustained")

    # 5. SJC decisions denied.
    add("sjc_denied",
        lambda: search(con, section_type="sjc_decision",
                       sjc_disposition="denied", limit=200),
        lambda rows: len(rows) >= 5,
        "SJC decisions disposition=denied")

    # 6. SJC decisions dismissed.
    add("sjc_dismissed",
        lambda: search(con, sjc_disposition="dismissed", limit=200),
        lambda rows: len(rows) >= 3,
        "SJC units disposition=dismissed")

    # 7. Specific case number 90-9 (appears in ga21).
    add("case_90-9",
        lambda: search(con, sjc_case="90-9", limit=50),
        lambda rows: len(rows) >= 1,
        "SJC case docket 90-9")

    # 8. Specific case number 92-1.
    add("case_92-1",
        lambda: search(con, sjc_case="92-1", limit=50),
        lambda rows: len(rows) >= 1,
        "SJC case docket 92-1")

    # 9. FTS phrase "judicial commission".
    add("fts_judicial_commission",
        lambda: search(con, match='"judicial commission"', limit=50),
        lambda rows: len(rows) >= 5,
        'FTS MATCH "judicial commission"')

    # 10. FTS "Standing Judicial Commission".
    add("fts_standing_judicial",
        lambda: search(con, match='"standing judicial commission"', limit=50),
        lambda rows: len(rows) >= 5,
        'FTS MATCH "standing judicial commission"')

    # 11. FTS "Constitutional Business".
    add("fts_constitutional_business",
        lambda: search(con, match='"constitutional business"', limit=50),
        lambda rows: len(rows) >= 5,
        'FTS MATCH "constitutional business"')

    # 12. FTS "in conflict with the Constitution".
    add("fts_in_conflict_constitution",
        lambda: search(con, match='conflict AND constitution', limit=50),
        lambda rows: len(rows) >= 5,
        'FTS MATCH conflict AND constitution')

    # 13. BCO 34 + dissent present.
    add("sjc_dissent_bco34",
        lambda: search(con, section_type="sjc_dissent", bco_chapter=34, limit=50),
        lambda rows: len(rows) >= 1,
        "SJC dissents touching BCO 34")

    # 14. SJC concurrences (any).
    add("sjc_concurrence",
        lambda: search(con, section_type="sjc_concurrence", limit=200),
        lambda rows: len(rows) >= 5,
        "SJC concurrences")

    # 15. CCB overture advice units overall.
    add("ccb_overture_advice",
        lambda: search(con, section_type="ccb_overture_advice", limit=200),
        lambda rows: len(rows) >= 10,
        "CCB overture advice units")

    # 16. FTS porter stemming: "appeal" should also catch "appeals/appealed".
    add("fts_appeal_stem",
        lambda: search(con, match="appeal", section_type="sjc_decision", limit=200),
        lambda rows: len(rows) >= 10,
        "FTS appeal (porter-stemmed) within SJC decisions")

    # 17. FTS "complaint" within SJC decisions.
    add("fts_complaint",
        lambda: search(con, match="complaint", section_type="sjc_decision", limit=200),
        lambda rows: len(rows) >= 10,
        "FTS complaint within SJC decisions")

    # 18. BCO 34 across SJC+CCB in a single GA (ga modern, e.g. 49).
    add("ga_specific_facet",
        lambda: search(con, ga_ordinal=49, limit=500),
        lambda rows: len(rows) >= 10,
        "All sections from GA 49 (facet, no text query)")

    # 19. Overture membership facet (overture id 1, early GA had it).
    add("overture_facet",
        lambda: search(con, match="overture", section_type="ccb_overture_advice", limit=200),
        lambda rows: len(rows) >= 5,
        "CCB overture-advice units mentioning 'overture'")

    # 20. Flagship interleave count.
    add("flagship_bco34_interleave",
        lambda: bco34_history(con, limit=500),
        lambda rows: len(rows) >= 15 and len({r["section_type"] for r in rows}) >= 2,
        "BCO34 interpretive history interleaves >=2 unit types, >=15 rows")

    # 21. Unified judicial_body facet: pre-SJC CJB units exist and are citable.
    add("judicial_body_cjb",
        lambda: search(con, judicial_body="CJB", order="chrono", limit=500),
        lambda rows: len(rows) >= 30
        and all(r["section_type"] in ("cjb_report", "cjb_decision") for r in rows),
        "judicial_body=CJB returns pre-SJC CJB units")

    # 22. Unified judicial_body facet: modern SJC units.
    add("judicial_body_sjc",
        lambda: search(con, judicial_body="SJC", order="chrono", limit=2000),
        lambda rows: len(rows) >= 100
        and all(r["section_type"].startswith("sjc_") for r in rows),
        "judicial_body=SJC returns modern SJC units")

    # 23. UNIFIED judicial history spans the FULL record: BOTH CJB (pre-SJC, early
    #     GAs) and SJC (modern, late GAs) appear, interleaved chronologically.
    add("judicial_history_full_span",
        lambda: judicial_history(con, limit=2000),
        lambda rows: ({r["judicial_body"] for r in rows} >= {"CJB", "SJC"}
                      and min(r["ga_ordinal"] for r in rows
                              if r["judicial_body"] == "CJB") <= 13
                      and max(r["ga_ordinal"] for r in rows
                              if r["judicial_body"] == "SJC") >= 45
                      and all(rows[i]["ga_ordinal"] <= rows[i + 1]["ga_ordinal"]
                              for i in range(len(rows) - 1))),
        "unified judicial history interleaves CJB(early)+SJC(late), chronological")

    # 24. CJB decisions carry resolvable citations (GA+page) under the invariant.
    add("cjb_decisions_citable",
        lambda: search(con, section_type="cjb_decision", limit=500),
        lambda rows: len(rows) >= 20 and all(r["citable"] == 1 and r["citation"]
                                             for r in rows),
        "cjb_decision units all citable to GA+page")

    return tests


def run_tests(con, verbose=False):
    tests = known_answer_set(con)
    npass = 0
    results = []
    for name, fn, expect, note in tests:
        try:
            rows = fn()
            ok = bool(expect(rows))
            # Citability invariant: every returned row must be citable & have a citation.
            cite_ok = all(r.get("citable") == 1 and r.get("citation") for r in rows)
            ok = ok and cite_ok
        except Exception as e:  # noqa
            rows, ok = [], False
            note = note + f"  ERROR: {e}"
        if ok:
            npass += 1
        results.append((name, ok, len(rows), note))
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:<32} n={len(rows):<4} {note}")
    return npass, len(tests), results


# --------------------------------------------------------------------------- #
# Pages base-layer coverage verification                                       #
# --------------------------------------------------------------------------- #
def pages_coverage_report(con, min_chars=300):
    """Verify the pages base layer covers every page that has real text.

    Counts pages in build/page_jsonl/<vol>.pages.jsonl with char_count>min_chars
    that are ABSENT from the `pages` table (must be 0). Returns a dict with the
    corpus total, per-vol uncovered tail, and the list of any still-missing
    (vol, pdf_page, char_count) so we can be honest about residual gaps."""
    indexed = set()
    for vol, pp in con.execute("SELECT vol, pdf_page FROM pages"):
        indexed.add((vol, int(pp)))

    uncovered = []
    per_vol = {}
    text_pages = 0
    for vol in list_volumes():
        for row in iter_volume_page_rows(vol):
            cc = row.get("char_count") or 0
            if cc > min_chars:
                text_pages += 1
                key = (vol, int(row["pdf_page"]))
                if key not in indexed:
                    uncovered.append((vol, int(row["pdf_page"]), cc))
                    per_vol[vol] = per_vol.get(vol, 0) + 1
    return {
        "total_pages_indexed": len(indexed),
        "text_pages_over_threshold": text_pages,
        "uncovered_count": len(uncovered),
        "uncovered": uncovered,
        "per_vol": per_vol,
        "min_chars": min_chars,
    }


def run_pages_tests(con, verbose=False):
    """Page base-layer regression checks (separate from the section-citability
    invariant in run_tests, since page hits cite by physical location)."""
    checks = []

    def add(name, ok, note):
        checks.append((name, bool(ok), note))

    # 1. Coverage: zero pages with char_count>300 are missing from `pages`.
    cov = pages_coverage_report(con, min_chars=300)
    add("coverage_no_text_page_unsearchable", cov["uncovered_count"] == 0,
        f"{cov['uncovered_count']} text-pages (>300ch) absent from `pages` "
        f"(was 1159 pre-layer); {cov['total_pages_indexed']} pages indexed")

    # 2. The ga16_1988 anomaly is RESOLVED at the page layer: its appendix tail
    #    (pages the section chunker missed) is now fully searchable.
    n16 = con.execute(
        "SELECT COUNT(*) FROM pages WHERE vol='ga16_1988'").fetchone()[0]
    add("ga16_1988_pages_present", n16 >= 560,
        f"ga16_1988 has {n16} pages in the base layer")

    # 3. A page in the previously-uncovered ga16 appendix tail is matchable.
    hits = search_pages(con, match="committee", vol="ga16_1988", limit=5)
    add("ga16_1988_appendix_searchable", len(hits) >= 1
        and all(h.get("citation") for h in hits),
        f"ga16_1988 'committee' page hits: {len(hits)}, all cited")

    # 4. Every page hit carries a resolvable citation.
    hits = search_pages(con, match="presbytery", limit=20)
    add("page_hits_citable", len(hits) >= 1
        and all(h.get("citation") and h.get("ga_ordinal") is not None
                for h in hits),
        f"'presbytery' page hits all carry GA+page citation ({len(hits)})")

    npass = sum(1 for _, ok, _ in checks if ok)
    if verbose:
        for name, ok, note in checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:<36} {note}")
    return npass, len(checks), checks


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Phase 5 FTS5 search layer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--force", action="store_true")

    q = sub.add_parser("query")
    q.add_argument("match", nargs="?", default=None)
    q.add_argument("--section-type")
    q.add_argument("--judicial-body", choices=["CJB", "SJC"],
                   help="unified judicial facet (CJB=pre-SJC, SJC=modern)")
    q.add_argument("--committee")
    q.add_argument("--ga", type=int)
    q.add_argument("--bco-chapter", type=int)
    q.add_argument("--disposition")
    q.add_argument("--ccb-verdict")
    q.add_argument("--case")
    q.add_argument("--cjb-case")
    q.add_argument("--order", default="bm25", choices=["bm25", "chrono"])
    q.add_argument("--limit", type=int, default=15)
    q.add_argument("--all", action="store_true", help="include non-citable rows")

    pq = sub.add_parser(
        "pages-query",
        help="FULL-TEXT base layer: search EVERY page (100%% coverage safety net)")
    pq.add_argument("match", nargs="?", default=None,
                    help="FTS5 MATCH expression (omit for a facet scan)")
    pq.add_argument("--vol", help="restrict to a volume, e.g. ga16_1988")
    pq.add_argument("--ga", type=int, help="restrict to a GA ordinal")
    pq.add_argument("--year", type=int)
    pq.add_argument("--order", default="bm25", choices=["bm25", "chrono"])
    pq.add_argument("--limit", type=int, default=15)

    sub.add_parser("bco34").add_argument("--limit", type=int, default=15)

    jh = sub.add_parser("judicial",
                        help="unified CJB+SJC interpretive history, chronological")
    jh.add_argument("--bco-chapter", type=int)
    jh.add_argument("--limit", type=int, default=50)

    t = sub.add_parser("test")
    t.add_argument("--verbose", action="store_true")

    args = ap.parse_args()

    if args.cmd == "build":
        build(force=args.force)
        return

    if not os.path.exists(DB_PATH):
        print(f"[error] {DB_PATH} not found — run `build` first.", file=sys.stderr)
        sys.exit(2)
    con = connect()

    if args.cmd == "query":
        hits = search(con, args.match, section_type=args.section_type,
                      judicial_body=args.judicial_body,
                      committee=args.committee, ga_ordinal=args.ga,
                      bco_chapter=args.bco_chapter,
                      sjc_disposition=args.disposition,
                      ccb_verdict=args.ccb_verdict, sjc_case=args.case,
                      cjb_case=args.cjb_case,
                      order=args.order, limit=args.limit,
                      require_citable=not args.all)
        print(f"{len(hits)} hit(s):")
        for h in hits:
            print(fmt_hit(h))

    elif args.cmd == "pages-query":
        hits = search_pages(con, args.match, vol=args.vol, ga_ordinal=args.ga,
                            year=args.year, order=args.order, limit=args.limit)
        print("=== pages base layer (full-text safety net, 100% page coverage) ===")
        print(f"{len(hits)} hit(s):")
        for h in hits:
            print(fmt_page_hit(h))

    elif args.cmd == "judicial":
        hits = judicial_history(con, bco_chapter=args.bco_chapter, limit=args.limit)
        scope = f"BCO {args.bco_chapter}" if args.bco_chapter else "all chapters"
        print(f"=== Unified judicial interpretive history ({scope}); "
              f"CJB (pre-SJC) + SJC interleaved chronologically ===")
        print(f"{len(hits)} result(s):")
        for h in hits:
            print(fmt_hit(h, with_snippet=False))

    elif args.cmd == "bco34":
        hits = bco34_history(con, limit=args.limit)
        print(f"=== Interpretive history of BCO 34 "
              f"(CJB pre-SJC + SJC + CCB interleaved, chronological) ===")
        print(f"{len(hits)} result(s):")
        for h in hits:
            print(fmt_hit(h, with_snippet=False))

    elif args.cmd == "test":
        npass, ntot, results = run_tests(con, verbose=True)
        print(f"\nKNOWN-ANSWER SET: {npass}/{ntot} passed "
              f"({100*npass/ntot:.0f}%)")
        flag = [r for r in results if r[0] == "flagship_bco34_interleave"]
        print(f"FLAGSHIP query ok: {bool(flag and flag[0][1])}")
        print("\nPAGES BASE-LAYER CHECKS:")
        pp, pt, _ = run_pages_tests(con, verbose=True)
        print(f"PAGES BASE LAYER: {pp}/{pt} passed ({100*pp/pt:.0f}%)")


if __name__ == "__main__":
    main()
