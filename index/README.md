# `index/` — Phase 5 search layer

`pca_minutes.db` is a single, portable SQLite database (FTS5, no daemon) built
from `index/chunks.jsonl` + the per-page `build/page_jsonl/<vol>.pages.jsonl` by
`scripts/05_index.py`. It makes the 52-volume PCA General Assembly minutes corpus
scannable for constitutional interpretation, and **every result carries a
resolvable `GA number + page` citation** (the Phase 5 non-negotiable invariant).

## Two complementary layers

The DB has two independent search layers — use the right one for the job:

| Layer | Tables | Granularity | Use it for |
|-------|--------|-------------|------------|
| **Structured overlay** | `sections` / `sections_fts` | one row per *named* citable section | faceted / structured / interpretive-history search — filter by `section_type`, `judicial_body` (CJB/SJC), `bco_chapter`, SJC/CCB/CJB fields, etc. |
| **Full-text base layer** | `pages` / `pages_fts` | one row per *pdf_page* with text | **guaranteed 100% coverage** — the safety net. Searches EVERY page, including appendices, rosters, statistics and floor minutes that fall between/outside named sections. |

The structured layer is a curated overlay on top of the corpus; the page layer
is the floor that guarantees nothing with text is unsearchable. They are built
independently — the page layer never depends on the section chunker, so a page
the chunker missed is still fully searchable.

**Why the base layer exists.** The structured layer only indexes citable
sections, so before the page layer, **1,159 pages with real text (>300 chars)
were unsearchable corpus-wide** — worst in `ga16_1988` (≈309 of 561 text-pages:
the volume's appendix/report tail, pdf pages ~256–568, was almost entirely
unchunked) and `ga04_1976` (≈67). The `pages` layer indexes **32,251 pages**
(every page with text; 126 truly-blank pages skipped), bringing pages-with-text
left unsearchable to **0**. See "Verification" below.

### The judicial record spans the FULL 1973-2025 history

Constitutional-interpretation search is **not** limited to the post-SJC era. The
General Assembly's judicial body comes in two forms, unified under a single
`judicial_body` facet:

- **`CJB`** — pre-SJC **Committee on Judicial Business** (GAs 1-17, 1973-1989),
  back when the General Assembly itself acted as the court via the CJB and the
  ad hoc Judicial Commissions it constituted (BCO 15-3). Section types
  `cjb_report` (the committee report) and `cjb_decision` (a numbered case /
  complaint / appeal / reference). These early volumes are OCR-shattered scans,
  so recall is honestly rougher here than for the modern SJC (see below).
- **`SJC`** — the **Standing Judicial Commission** (GAs 14+, dominant 1990+).
  Section types `sjc_decision`, `sjc_dissent`, `sjc_concurrence`.

GAs 14-17 are a CJB/SJC **overlap**: both bodies appear. A single
`judicial_body`-filtered or unified `judicial_history()` query therefore returns
pre-SJC CJB units and modern SJC units **interleaved chronologically**, each
citable to GA+page.

Measured pre-SJC CJB recall vs `golden/labels/*_cjb.json` (cjb_*-typed units
only): ga05_1977 9/9 (100%), ga10_1982 8/8 (100%), ga13_1985 7/9 (78%; 100% with
the journal-item fallback). The ga13 misses are a judicial *reference* whose
respondent is a person (not a court) and an Appendix-S commission-minutes range
— both consistent with the rougher OCR of the early scanned volumes.

## Build / rebuild

```bash
/workspace/.venv/bin/python scripts/05_index.py build          # idempotent (skips if current)
/workspace/.venv/bin/python scripts/05_index.py build --force  # full rebuild
```

The build reconstructs each section's text from the per-page **source of
truth** `build/page_jsonl/<vol>.pages.jsonl` (so re-OCR of a page + rebuild
updates search), then BM25-indexes it.

## Schema

- **`sections`** — content table, one row per chunk. Columns: `chunk_id`,
  `parent_doc`, `source_file`, `ga_ordinal`, `year`, `era`, `section_type`,
  **`judicial_body`** (`CJB` | `SJC` | NULL — the unified judicial facet),
  `committee`, `title`, `appendix`, `pdf_page_start/end`,
  `printed_page_start/end`, `page_range`, plus faceted list columns
  (`bco_chapters`, `bco_citations`, `ga_item_ids`, `overtures`,
  `sjc_case_numbers`, `cjb_case_numbers`, `ccb_verdicts`, …) stored as JSON
  **and** as a space-delimited `*_s` scalar for cheap `LIKE '% 34 %'` membership
  tests. SJC fields: `sjc_disposition`, `sjc_has_dissent`,
  `sjc_has_concurrence`. Pre-SJC CJB fields: `cjb_case_numbers`,
  `cjb_disposition`, `cjb_parties`. CCB: `ccb_verdicts`. `citable=1` iff the row
  has `ga_ordinal` AND a non-empty `page_range`. Full `text` is stored here.
  Indexed on `section_type`, `ga_ordinal`, `committee`, `citable`,
  `judicial_body`.
- **`sections_fts`** — `CREATE VIRTUAL TABLE sections_fts USING fts5(text,
  title, content='sections', content_rowid='rowid', tokenize='porter
  unicode61')`. External-content linked to `sections` by `rowid`. Supports
  `bm25()`, `snippet()`, `highlight()`.
- **`pages`** — full-text **base layer** content table, one row per pdf_page
  that has text, loaded directly from the per-page **source of truth**
  `build/page_jsonl/<vol>.pages.jsonl`. Columns: `page_id` (== FTS rowid), `vol`
  (e.g. `ga16_1988`), `ga_ordinal`, `year`, `pdf_page`, `printed_page`,
  `char_count`, `engine`, `source_file`, `text`. Indexed on `vol`, `ga_ordinal`,
  and a `UNIQUE(vol, pdf_page)`. Truly-blank pages (no text) are skipped.
- **`pages_fts`** — `CREATE VIRTUAL TABLE pages_fts USING fts5(text,
  content='pages', content_rowid='page_id', tokenize='porter unicode61')`.
  External-content linked to `pages` by `page_id`. BM25 + `snippet()`.

### Citability invariant

A `sections` row without `ga_ordinal + page_range` is flagged `citable=0` and is
**never** returned by the query helper unless `require_citable=False` (CLI
`--all`). Every returned section hit gets a `citation` field:
`GA <ord> (<year>), pp.<range> (printed p.<n>) [item <id>] — <file>#pdfpage<n>`.

The **page layer** cites by *physical location* (its source of truth is the PDF
page, not a section item id): every `search_pages()` hit carries
`GA <ord> (<year>), pdf p.<n> (printed p.<m>) — <file>#pdfpage<n>`. Because each
page row inherits `ga_ordinal`/`year` straight from `page_jsonl`, every page hit
is citable by construction.

## Query — CLI

```bash
PY=/workspace/.venv/bin/python
S=scripts/05_index.py

# FLAGSHIP: interpretive history of BCO 34 — CJB (pre-SJC) + SJC + CCB,
# interleaved chronologically across the full 1973-2025 record
$PY $S bco34 --limit 15

# UNIFIED judicial history (all chapters, or one): CJB + SJC interleaved
$PY $S judicial --limit 50
$PY $S judicial --bco-chapter 34

# Whole pre-SJC judicial record (Committee on Judicial Business), chronological
$PY $S query --judicial-body CJB --order chrono

# Modern SJC record only
$PY $S query --judicial-body SJC --order chrono

# Faceted: every SJC decision touching BCO ch.34, chronological
$PY $S query --section-type sjc_decision --bco-chapter 34 --order chrono

# CCB units that found an overture in conflict (BM25 + snippet)
$PY $S query "overture conflict" --section-type ccb_overture_advice --ccb-verdict in_conflict

# Specific docket numbers (modern SJC, or pre-SJC CJB case)
$PY $S query --case 2004-8
$PY $S query --cjb-case "Case 5"

# Free-text BM25 across the whole corpus (structured overlay — citable sections only)
$PY $S query "westminster confession exception"

# FULL-TEXT BASE LAYER — guaranteed 100% page coverage (searches EVERY page,
# incl. appendices/rosters the section chunker never bracketed)
$PY $S pages-query "westminster confession exception"
$PY $S pages-query "judicial business" --vol ga16_1988   # the previously-unsearchable ga16 tail
$PY $S pages-query "presbytery" --ga 4 --order chrono

# Known-answer regression set (24 section queries + 4 page base-layer checks)
$PY $S test --verbose
```

`pages-query` flags: `--vol --ga --year --order {bm25,chrono} --limit`.

CLI flags: `--section-type --judicial-body {CJB,SJC} --committee --ga
--bco-chapter --disposition --ccb-verdict --case --cjb-case
--order {bm25,chrono} --limit --all`.

## Query — Python

```python
import importlib.util
spec = importlib.util.spec_from_file_location("idx", "/workspace/scripts/05_index.py")
idx = importlib.util.module_from_spec(spec); spec.loader.exec_module(idx)

con = idx.connect()                                   # sqlite3.Connection
hits = idx.search(con, '"standing judicial commission"',
                  section_type="sjc_decision", bco_chapter=34, limit=10)
for h in hits:
    print(h["citation"], "::", h["snippet"])

# Unified judicial facet: the FULL pre-SJC + modern record
for h in idx.search(con, judicial_body="CJB", order="chrono", limit=200):
    print(h["judicial_body"], h["citation"])

# Unified interpretive-history helpers (CJB + SJC + CCB, chronological)
for h in idx.judicial_history(con, bco_chapter=34, limit=50):
    print(h["judicial_body"], h["section_type"], h["citation"])
for h in idx.bco34_history(con, limit=15):   # == judicial_history(bco_chapter=34)
    print(h["citation"])
```

`search()` returns dicts with the facet columns (incl. `judicial_body`,
`cjb_case_numbers`, `cjb_disposition`), a `snippet` (when a `match` is given),
and an always-present resolvable `citation`. `judicial_history()` returns the
interleaved **CJB (pre-SJC) + SJC + CCB** timeline ordered by
`(ga_ordinal, pdf_page)`; `bco34_history()` is the BCO-34 flagship over it.

```python
# FULL-TEXT BASE LAYER — guaranteed 100% page coverage (the safety net)
for h in idx.search_pages(con, "judicial business", vol="ga16_1988", limit=10):
    print(h["citation"], "::", h["snippet"])
# also: idx.search_pages(con, match, ga_ordinal=..., year=..., order="chrono")

# Verify nothing with text is unsearchable (must report uncovered_count == 0)
rep = idx.pages_coverage_report(con, min_chars=300)
print(rep["total_pages_indexed"], rep["uncovered_count"])
```

`search_pages()` returns dicts with `vol, ga_ordinal, year, pdf_page,
printed_page, char_count, engine, source_file`, a `snippet` (when `match` given),
and a resolvable physical `citation`.

## Raw SQL example

```sql
-- the FULL judicial record (CJB pre-SJC + SJC), chronological, one facet scan
SELECT ga_ordinal, year, judicial_body, section_type, page_range,
       COALESCE(sjc_disposition, cjb_disposition) AS disposition, source_file
FROM sections
WHERE judicial_body IS NOT NULL AND citable=1
ORDER BY ga_ordinal, pdf_page_start;

-- every SJC decision touching BCO 34, chronological, with a BM25-free facet scan
SELECT ga_ordinal, year, page_range, sjc_disposition, sjc_case_numbers, source_file
FROM sections
WHERE section_type='sjc_decision' AND bco_chapters_s LIKE '% 34 %' AND citable=1
ORDER BY ga_ordinal, pdf_page_start;

-- BM25 full-text with snippet
SELECT s.ga_ordinal, s.page_range,
       snippet(sections_fts,0,'[',']',' … ',12) AS snip,
       bm25(sections_fts) AS rank
FROM sections s JOIN sections_fts f ON f.rowid=s.rowid
WHERE sections_fts MATCH 'conflict AND constitution' AND s.citable=1
ORDER BY rank LIMIT 10;
```

## Verification — full-text coverage

`05_index.py test` runs the 24-query structured known-answer set **plus** 4 page
base-layer checks. The headline check, `coverage_no_text_page_unsearchable`,
counts pages in `build/page_jsonl/` with `char_count>300` that are **absent**
from the `pages` table:

- **before** the page layer: **1,159** such pages were unsearchable corpus-wide.
- **after**: **0** (32,251 pages indexed; 126 truly-blank pages skipped).

```bash
$PY $S test --verbose   # see KNOWN-ANSWER SET 24/24 + PAGES BASE LAYER 4/4
```

### Known limitation — `ga16_1988` structured-chunk gap (page layer resolves it)

`ga16_1988` is the worst structured-coverage case: the section chunker bracketed
the front matter + numbered journal items (16-1…16-110, pdf pages ~21–255) and a
single Appendix-J `cjb_report` (pdf p.389–398) + two `sjc_decision` units, but
left the rest of the appendix/report tail (pdf pages ~256–388 and ~399–568,
≈309 text-pages) **unchunked**. Cause: those tail pages are bulk appendix bodies
(agency/committee reports, statistics, rosters) with no journal-item token to
anchor a chunk, and the appendix matcher only caught Appendix J — it did not
bracket the surrounding appendix ranges. This is a *structured-chunk* gap in
`04_structure_tag.py`, **not** a text problem: the page base layer indexes all
of those pages, so they are fully full-text searchable and citable today
(verified: `pages-query "judicial business" --vol ga16_1988` returns hits at
pdf p.397/544, both inside the old gap). Re-running stage 04 to close the
*structured* gap is tracked separately and is **not** done here.

## Stage 0 escape hatch

Always available, no DB needed:
`rg 'SJC 2018-' markdown/` / `rg 'BCO 34-1' markdown/`.
