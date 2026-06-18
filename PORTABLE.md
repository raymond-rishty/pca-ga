# PCA General Assembly Minutes — Portable Corpus

A searchable corpus + structural index of all **52 volumes** of the Presbyterian Church in
America *Minutes of the General Assembly*, **1973–2025**, built for constitutional-interpretation
research (BCO, SJC/CCB cases, overtures, denominational history).

It is designed to be **portable**: everything that matters is **plain markdown** — readable,
presentable, greppable, and ingestible directly into another researcher's tools or LLM with
**no Python and none of the build scripts required**. A SQLite database is also included as an
optional full-text-query layer, generated from the same data.

| Artifact | What it is | How you use it |
|---|---|---|
| `markdown/ga*_*.md` (52 files) | The cleaned, OCR-corrected, structurally-formatted minutes — one file per volume | Read in any editor / grep / feed to an LLM |
| `index/INDEX.md` | Corpus front door: volume table + links to everything | Start here |
| `index/OVERTURES.md` | The overture catalogue (~2,000, with subject + final outcome), grouped by Assembly | Read / grep / ingest |
| `index/CASES.md` | The 647 SJC/CJB judicial cases (parties, disposition, BCO cited) | Read / grep / ingest |
| `index/outlines/ga*.md` | A structural table of contents per volume | Navigate a volume |
| `index/pca_minutes.db` | *(optional)* One SQLite DB holding every layer for full-text query | Query with any SQLite tool (below) |

The markdown catalogues are **generated from the database**, so the two stay in sync. The source
PDFs (`minutes/`, ~3 GB) and the per-page working text (`build/page_jsonl/`) are the **regenerable
inputs**, not part of the deliverable.

> **In this Git repository** the SQLite database (`pca_minutes.db`, ~260 MB) and `build/page_jsonl/`
> are **not committed** (over GitHub's 100 MB file limit). Get the prebuilt DB from the data
> download linked in the [README](README.md), or regenerate everything from `scripts/`.

---

## The database: one file, everything queryable

`index/pca_minutes.db` is a standard SQLite 3 file with FTS5. Open it with **anything**:

```bash
sqlite3 index/pca_minutes.db                 # CLI
```
```python
import sqlite3, pandas as pd                  # Python / pandas
df = pd.read_sql("SELECT * FROM overtures", sqlite3.connect("index/pca_minutes.db"))
```
- **DB Browser for SQLite** (GUI, free) — open the file, browse/query visually.
- **Datasette** — `datasette index/pca_minutes.db` gives an instant browsable+queryable web UI + JSON API.
- **sql.js / absurd-sql** — query it client-side in a browser, no server.

### Tables

| Table | Rows | Grain | Key columns |
|---|---|---|---|
| `pages` + `pages_fts` | 32,168 | one row per scanned/extracted page | `vol, ga_ordinal, year, pdf_page, printed_page, text` |
| `sections` + `sections_fts` | 4,479 | citable section chunks | `chunk_id, parent_doc, ga_ordinal, ...` |
| `cases` + `cases_fts` | 647 | SJC/CCB judicial cases | `case_id, case_number, case_number_norm, ...` |
| `structure` | 10,707 | the document outline, flattened tree | `node_id, parent_id, vol, type, label, title, pdf_page, seq` |
| `overtures` | 2,028 | the proposal catalogue (deduped; ~97% titled; ~82% with a disposition; 84 amendments ratified / 21 not ratified, with evidence) | `ga_ordinal, year, number, source, title, disposition, final_disposition, ratification_note, pdf_page, pages, context` |
| `sjc_roster` | 480 | official SJC case roster (ground truth) | `canonical_number, title, pdf_url, raw` |
| `bco_changes` / `bco_renumberings` / `citation_corrections` | 50 / 7 / 5 | BCO concordance layer | `raw` (JSON) |
| `meta` | — | build provenance | `key, value` |

`*_fts` tables are **contentless FTS5** over their base table — match on the FTS table, then join
back on rowid for the metadata columns (see recipes). `structure` is the per-volume outline
flattened with `parent_id` (NULL at the PART level) and `seq` (document order), so you can both
walk the hierarchy and ask "what section is page N in".

---

## Query recipes (pure SQL)

```sql
-- Full-text search the page text, with volume + page
SELECT p.vol, p.pdf_page, snippet(pages_fts,0,'[',']','…',12) AS hit
FROM pages_fts f JOIN pages p ON p.page_id = f.rowid
WHERE pages_fts MATCH 'paedocommunion' LIMIT 20;

-- "Has the PCA considered this before?" — search overtures by SUBJECT, across all GAs
SELECT ga_ordinal, year, number, title, source, pages
FROM overtures WHERE title LIKE '%paedocommunion%' OR title LIKE '%abortion%' ORDER BY ga_ordinal;

-- every overture from a given presbytery
SELECT ga_ordinal, number, title, pages FROM overtures WHERE source LIKE '%Calvary%' ORDER BY ga_ordinal;

-- final outcomes: which BCO amendments were approved AND ratified by the presbyteries?
SELECT year, number, title, final_disposition FROM overtures
WHERE final_disposition LIKE 'Approved & ratified%' ORDER BY year;
--   disposition = the year-N Assembly action; final_disposition folds in the year-N+1 ratification
--   (constitutional BCO amendments are only final once 2/3 of presbyteries ratify, per BCO 26).

-- Which enclosing section does GA15 page 38 fall under?
SELECT type, label, title FROM structure
WHERE vol='ga15_1987' AND pdf_page <= 38
  AND type IN ('part','session','jsection','appendix','section')
ORDER BY pdf_page DESC LIMIT 1;

-- Walk a volume's top-level outline
SELECT label, title FROM structure
WHERE vol='ga15_1987' AND parent_id IS NULL ORDER BY seq;

-- Find a judicial case by full-text, with its docket number
SELECT c.case_number, c.case_number_norm
FROM cases_fts f JOIN cases c ON c.rowid = f.rowid
WHERE cases_fts MATCH 'jurisdiction' LIMIT 10;
```

### Cross-reference DB ↔ markdown
A row's `vol` (e.g. `ga15_1987`) is exactly the markdown filename: `markdown/ga15_1987.md`.
`pdf_page` is the page within that volume's PDF; `printed_page` (when present) is the page number
printed on the page. So a search hit points straight to both the PDF page and the markdown file.

---

## Markdown layout

One file per volume, named `ga<NN>_<YEAR>.md` (`ga01_1973.md` … `ga52_2025.md`). Structure is
encoded with markdown headings reflecting the documents' own hierarchy:

- `##` PART I–V (Journal, Appendices, etc.)
- `###` lettered sections (`B. OVERTURES TO THE FIFTEENTH GENERAL ASSEMBLY`) and committee reports
- `####` numbered subsections / referrals (`TO THE COMMITTEE ON …`)
- `#####` individual overtures (`Overture 37: from the Presbytery of Illiana`)
- Resolution clauses (Whereas / Therefore, be it resolved) are separate paragraphs.

The text has been OCR-corrected (de-shattered spacing, domain-vocabulary canonicalization for
terms like *Book of Church Order*, *Presbytery of X*, presbytery names and party surnames) while
preserving the original wording verbatim — formatting is presentation-only.

---

## Provenance / regeneration

Build order (in `scripts/`, needs Python 3 + the venv): `01_extract` → `16_domain_despace` →
`15_strip_headers` → `01_extract render` → `05_index build` → `07_build_cases` →
`09_reconcile_roster` → `08_index_cases` → `18_structure build` → `21_overture_titles` (subjects) →
`22_dispositions` (overture dispositions + cross-GA ratification) → **`19_export`** (folds the JSON
index layers into the DB) → **`20_markdown_index`** (renders the markdown catalogues). Run 19 then
20 last. `build/page_jsonl/` is the per-page source of truth.

Enrichment layers (each generated by an LLM workflow, persisted as JSONL the build folds in):
overture **subjects** (`overture_titles.jsonl`), **dispositions** (`dispositions.json` + `digest_dispositions.jsonl`
from the [Digest of Assembly Actions](https://www.pcahistory.org/pca/digest/), prepped by `23_digest_actions.py`),
and the **ratification** chain. Ratification is asserted ONLY from the authoritative BCO changes-list
(`bco_changes.jsonl`, scraped from pcahistory.org) — a constitutional BCO amendment approved at GA N
is "ratified" only if its section appears adopted at GA N+1/N+2; otherwise an LLM verification pass
(`ratification-verify`) reads the ratifying GA's PRIMARY minutes — guided by the Digest's citations
as a finding aid — and records the actual outcome (ratified / failed / not‑addressed) with a verbatim
**evidence quote** in `overtures.ratification_note` (audit trail: `ratification_verified.jsonl`).
Items still unconfirmed stay "sent to presbyteries; ratification not located". (The Digest's own
"adopted" labels are kept in `digest_adoptions.jsonl` but NOT used to assert ratification — they
proved unreliable, e.g. BCO 12‑5 was labeled "adopted" but the minutes show it was defeated 31–23.)
