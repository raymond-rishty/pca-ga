# Position Papers / Study Committee Reports — Specification

The fifth catalogue, alongside **Judicial Cases** (`SPEC-JUDICIAL-CASES.md`), **Overtures**
(`SPEC-OVERTURES.md`), **Constitutional Inquiries** (`SPEC-INQUIRIES.md`), and **Review of
Presbytery Records** (`SPEC-RPR.md`). A **position paper** — equivalently a **study committee
report** or **report of an ad-interim committee** — is the document produced by a committee appointed
by one Assembly to study a question (divorce & remarriage, creation, the Federal Vision, women
serving in ministry, human sexuality, …) and report back to a later Assembly. This catalogue is, at
its grain, **a library of those documents** — the analogue of the PCA Historical Center's "Studies &
Reports" index — answering *"What papers has the PCA produced on this topic, where is the full text,
and what became of their recommendations?"* *(Status: design spec — not yet implemented. It reuses
the case/overture/inquiry machinery and the appendix-bounding of the RPR layer.)*

## 1. The model (what a study-report record is)

> A study-report record is **one report document** — the paper a study/ad-interim committee laid
> before an Assembly (its topic, committee, the GA it was reported to, and a pointer to its full
> verbatim text in the minutes) — together with **the outcome of its recommendations** (what the GA
> did with it: adopted as the position of the PCA / recommendations adopted / received without
> adoption / recommitted). The **document is the unit**; the outcome is metadata *about* it.

This is the deliberate grain choice, and it follows **pcahistory.org's "Studies & Reports" index**,
not the RPR lifecycle model. The thing being catalogued is the **paper itself** — the committee's
work product — because that is what a researcher wants: the document, its full text, and a short note
on whether it carries denominational authority. We do **not** reconstruct a year-by-year GA-action
timeline as the spine (that is the RPR layer's model, `SPEC-RPR.md` §4); the GA's disposition is
captured as an *outcome field on the document*, not as the organizing structure.

Where a topic produced **several distinct papers** over the years (Baptism: 1977 and 1987;
Homosexuality: multiple reports 1977–1999; Insider Movements: 2012 and 2014; a majority report **and**
a minority report at the same GA), each paper is **its own record**, and they are **grouped under the
shared topic** in the index — exactly as pcahistory groups multiple documents under one heading. An
interim/partial report and the final report are therefore *two records under one topic*, cross-linked
("superseded by" / "initial report; see final"), not collapsed into a single threaded row.

Like the inquiry layer (`SPEC-INQUIRIES.md` §1), each record has **two strata**:
- **The document (verbatim)** — the paper as it appears in the minutes. The full bodies are *long*
  (100–400 lines typically; foundational ones — Number of Offices, Divorce — run past 2,000), so the
  page **links to the full report region** in the volume markdown (the load-bearing artifact) and
  **slices verbatim the parts a reader wants inline**: the committee's mandate, its **Recommendations**,
  and — as the outcome note — the **GA's disposing sentence(s)**. Sliced text is never altered.
- **A digest headnote** — a short editorial **summary + topic tags + outcome**, at the level of
  pcahistory's index. Derived and **labeled** (quoted from pcahistory.org / the PCA Digest Vol. 4
  "Study Committee Reports" section when available, else an LLM summary over the sliced report — as
  overture titles in `SPEC-OVERTURES.md` §5 and inquiry headnotes in `SPEC-INQUIRIES.md` §1), and
  **stamped with provenance** (`headnote_source: pcahistory | digest | generated`).

Distinct from the other four layers:
- vs. **Overture** — an overture *proposes*; a study committee *investigates and produces a paper*.
  They touch at the document's edges: a committee is usually **created by** an overture/commissioner
  motion and its recommendations may be **enacted as** a BCO amendment → those edges **cross-link to
  the overture layer** (and its ratification chain, `SPEC-OVERTURES.md` §6) as provenance/outcome, not
  as the spine.
- vs. **Judicial Case / Inquiry** — a study is **deliberative and denominational** (the church
  studying a question), not an adjudication of parties (case) nor advice on what the existing
  Constitution *means* (inquiry).
- vs. **RPR** — both touch multiple years, but RPR's unit is an *exception threaded through GA
  actions*; this layer's unit is **the document**, with outcome as a field — a deliberately flatter,
  more library-like grain.

## 2. Where study reports live

- **The report document itself** — an **appendix** in recent volumes ("**APPENDIX O–W** — REPORT OF
  THE AD INTERIM COMMITTEE ON …"), or **in the journal body** in early scanned volumes (`## REPORT OF
  THE AD INTERIM COMMITTEE TO STUDY …`). The report carries the committee's mandate, body (often
  chaptered), a **Recommendations** section, and sometimes a **Minority Report**. This is the primary
  thing we catalogue and link.
- **The journal — disposing action** — the paragraph where the GA *acts* on the report (`NN-NN …`):
  **received**, **adopted** (in whole / as the position of the PCA / specific recommendations only),
  **recommitted/continued**, **postponed**, or **answered by reference**. We slice this as the
  document's **outcome** (authoritative over the appendix when they differ — the precedence rule in
  `SPEC-RPR.md` §2), not as a multi-year timeline.
- **The journal — appointing action** (optional provenance) — the motion/overture that *created* the
  committee. Captured as a single "commissioned by" back-link when easily found; not required for the
  record to stand (the document and its outcome are).

Heading forms observed across eras (for detection, §3): `REPORT OF THE AD INTERIM COMMITTEE [TO STUDY
| ON] <topic> [TO THE <ordinal> GENERAL ASSEMBLY]`, `AD INTERIM STUDY COMMITTEE ON <topic>`,
`(INITIAL | MAJORITY | MINORITY) REPORT OF …`, optionally prefixed by a bold `APPENDIX <letter>` and
rendered at drifting heading levels (`#`…`######`) — the same level-drift the other appendix layers
handle.

## 3. Eras (volume coverage)

- **Born-digital (GA31–52, 2003–2025)** — clean appendix structure, explicit `APPENDIX <letter>`
  headings, bold report titles, often "TO THE <ordinal> GENERAL ASSEMBLY". The high-value, tractable
  target (Federal Vision, Insider Movements, Racial Reconciliation, Women in Ministry, Domestic
  Violence, Human Sexuality).
- **Scanned (GA1–30, 1973–2002)** — reports appear both in the journal body and in appendices, at
  mixed heading levels, with looser titles ("Committee to Study …"). The foundational positions live
  here (Number of Offices, Abortion 1978, Alcohol 1980, Baptism 1977/1987, Divorce 1992,
  Church/State 1987–88, Freemasonry 1987–88, Homosexuality 1977–99). Per-era heading discovery, like
  the CJB case era (`SPEC-JUDICIAL-CASES.md` §2).

## 4. The roster authority (anchor on pcahistory.org "Studies & Reports")

The grain and the checklist both come from the **PCA Historical Center's "Studies & Reports" index** —
this is the roster for the layer, exactly as the Digest Part III is for cases and Part II for
inquiries, and (because we are matching its grain) it doubles as the **shape we are reproducing**:

- `https://www.pcahistory.org/pca/digest/studies/` and the "PCA Studies & Reports, 1973–2021" section
  of `https://www.pcahistory.org/pca/digest/index.html` — an **alphabetical-by-topic** catalogue of
  every PCA study/position paper, with PDF links and, *inconsistently*, an M-GA citation
  (e.g. "AIDS Task Force Report [*M17GA* (1989), 17-25, p.62]").
- **PCA Digest Vol. 4 (1999–2018)** has a dedicated **"Study Committee Reports"** section — the fuller
  compilation for that era.

Parse this into a **roster of documents** keyed by topic: `{topic, paper_title, aliases[],
reported_ga, m_ga_citation (where given), pdf_url}` — one row per paper (multiple under a topic where
pcahistory lists several). It drives:
- **Identity & grain** — the canonical set of papers, their titles, and topic groupings, authoritative
  over our heading-regex guesses (so our catalogue lines up paper-for-paper with pcahistory's).
- **Citation-anchored location** — the roster's M-GA citation is *where to look*: jump to that GA +
  page and link/slice the document, rather than relying on format-drifting heading regexes.
- **Completeness** — every rostered paper maps to one record (full text located + outcome noted) or is
  reported as a precise "not located (roster: M-GA p.N)" gap. Because pcahistory's citations are
  sparse, the heading sweep (§5.1) backfills the M-GA citations the roster omits, and any paper found
  by heading but absent from the roster is surfaced (not silently dropped).

The minutes stay the verbatim content source (the document's full text and outcome are sliced from
them); pcahistory/the Digest never supply page text — they are the roster + headnote source.

**Fingerprint-location from the pcahistory copy.** Before falling back to a link, a gap document's
pcahistory text is mined to *find it in the minutes*: (a) distinctive multi-word phrases from the
document body are normalized and searched across the corpus to identify the volume (and a hit line),
and (b) the **citation header pcahistory prints on each document** (`15th GA 1987, Appendix Q, p.429`;
`21-64, p.174`) gives the authoritative volume + printed page, which resolves fingerprint ties and is
cross-checked against the located anchor. A short locate-and-slice pass then pins the exact start/end.
This promoted most roster gaps from links to **verbatim minutes records** (the §1 grain); only
documents that still can't be confidently pinned keep the link fallback below.

**Gap fallback (pcahistory-hosted copies).** Some rostered documents are *not* in the digitized
minutes corpus — RPCES-era papers, floor resolutions printed elsewhere, or sub-sections never split
out. For these, the catalogue links to the document's **PCA Historical Center copy** (the PDF/HTML
on pcahistory.org, verified to resolve), recorded in `studies_pcahistory.json` and merged as records
tagged `source: pcahistory` with an `external_url` and **no minutes anchor**. These pages are
explicitly labeled "hosted at the PCA Historical Center (not in the GA minutes corpus)" so the
provenance distinction from sliced-verbatim-minutes records is never lost. This is a deliberate,
labeled relaxation of the minutes-only rule to achieve roster completeness; a topic with neither a
located minutes document nor a working pcahistory copy stays an honest "not located" gap.

## 5. Extraction approach (locate the document, then note its outcome)

1. **Detect & region the document** — find report headings (§2/§3 forms) via an `_STUDY` recognizer
   added to `18_structure.py`, guarded against citations of a prior report (reuse the `_CITE`/`_GAREF`
   guards from `25_case_extract.py` so "as noted in the FV Report" is not a header). Bound each report
   to its appendix using the same `APPENDIX <X>` / page-anchor bounding as the case and RPR layers
   (`SPEC-JUDICIAL-CASES.md` §3, `SPEC-RPR.md` §5) so the adjacent committee report doesn't bleed in.
   The region's span (first line → last line, with page anchors) is the **full-text link target**.
2. **Slice the inline parts** — the committee mandate and the **Recommendations** block, verbatim. LLM
   agents return line ranges, code slices — no fabricated text (the rule in every layer); the long
   body stays linked, not inlined.
3. **Locate & slice the outcome** — scan the journal for the disposing paragraph (`NN-NN … (received |
   adopted | recommitted | postponed) …`) acting on this report and slice its verbatim sentence(s);
   classify (§6). Optionally capture the appointing motion as a "commissioned by" back-link. The
   messier scanned volumes use the locate-then-slice agent pass (as CJB cases / SJC stragglers did,
   `SPEC-JUDICIAL-CASES.md` §5).
4. **Group, don't thread** — attach each document to its **topic** (roster topic + alias match) and
   cross-link sibling papers under that topic (initial ↔ final, majority ↔ minority, 1977 ↔ 1987).
   This is grouping for navigation, not the year-by-year timeline reconstruction of RPR.
5. **Born-digital GA31–52 first**, then extend to scanned GA1–30 with per-era heading profiles.

## 6. Identity, metadata & outcome

Per record (one document): `{topic (canonical), paper_title, aliases[], committee_name, reported_ga,
full_text (page-anchored link to the report region), mandate (verbatim), recommendations (verbatim),
outcome (verbatim GA action + classification), commissioned_by (overture/motion back-link, optional),
resulting_amendments[] (cross-link to the overture ratification chain, where recs became BCO changes),
related_papers[] (sibling docs under the topic), provisions[] (BCO/WCF/RAO parsed from the recs),
is_minority_report (bool)}`. Plus the **digest-headnote** fields (derived, labeled, §1):
`{summary, topic_tags, key_words, headnote_source}`.

**Outcome classification** (a field on the document, the secondary fact after the paper itself) — the
research question is *does this paper carry denominational authority, or is it a report the GA merely
received?* Capture the GA's action verbatim and label it:
- **Adopted as the position of the PCA** (the strongest — an official position paper);
- **Recommendations adopted** (specific numbered recs, possibly amended on the floor — record *which*);
- **Received / commended for study** (received *without* adopting its conclusions — explicitly *not* a
  binding position);
- **Recommitted / continued** (sent back; a later paper under the same topic supersedes it);
- **Postponed**; **Answered by reference / declined**; **No final action located** (honest label —
  never upgraded to "adopted", the RPR rule, `SPEC-RPR.md` §7).

## 7. Storage & index (capture once, project freely)

The real deliverable is the **structured record set** of §6 — one well-formed record per paper, each
carrying its topic, year/GA, committee, outcome, provisions, and full-text pointer. Once that exists,
**every index is a cheap derived view, not a separate artifact to design**: sort or group the same
records by whatever dimension a reader wants. So the data model is primary; the indexes below are just
the projections we ship.

Storage: one page per document in `studies/<topic-slug>[-<year>].md` (mirroring `cases/*`,
`inquiries/*`, `rpr/*`), backed by a `studies` DB table holding the §6 fields (the queryable layer the
markdown views are generated from, as `overtures` backs `OVERTURES.md`).

Projections (all generated from the one record set — add or reorder freely):
- **by topic** — `index/STUDIES.md`, alphabetical, each topic heading listing its paper(s) (the
  default, matching pcahistory's "Studies & Reports");
- **chronological** — by GA/year;
- **by provision** — `STUDIES-BY-PROVISION.md`, for papers that recommended BCO changes (the analogue
  of `RPR-BY-PROVISION.md`);
- and, trivially, by committee or by outcome if useful — same rows, different `ORDER BY`/`GROUP BY`.

Each row in any view: paper title · committee · **reported** (GA, deep-linked) · **outcome**
(adopted-as-position / recs-adopted / received-only / recommitted / not-located) · **full text**
(link) · link to the page.

Each **page** leads with the document: the **headnote** (editorial summary + topic tags + outcome,
marked with `headnote_source`), a prominent **link to the full report** in the volume markdown, the
**verbatim mandate and Recommendations** sliced and page-anchored, the **outcome** (verbatim GA
disposing sentence + classification), and footer cross-links — **commissioned by** (overture),
**resulting amendment(s)**, and **related papers** under the same topic.

Add study reports to `18_structure.py` as their own node type (like overtures and inquiries) so they
appear both in the queryable structural index and as headings in the rendered markdown — the "two
representations" rule (`SPEC-OVERTURES.md` §4). New render script `36_study_pages.py` (next free
number after `35_search_index.py`), folded into the `studies` DB table by `19_export.py`, the search
app by `35_search_index.py`, and the `llms.txt` / README catalogue list.

## 8. Invariants (acceptance)

1. The catalogue's grain is **the document**: one record per paper, grouped (not collapsed) under its
   topic; an initial and a final report on the same topic are **two records cross-linked**, and a
   majority/minority pair is **two records**, never merged.
2. Every record **links to the full report text** in the minutes (page-anchored) and carries an
   **outcome** classified from the verbatim GA action; "received only" and "adopted as position" are
   never conflated, and "no final action located" is the honest label — never assume adoption.
3. Sliced text (mandate, recommendations, outcome sentence) is **verbatim** minutes, unaltered; the
   long body is **linked, not transcribed**; provisions parsed, not invented. The **headnote** may be
   derived but is **always labeled** (`headnote_source`) and visually separated (§1).
4. **0 orphans, 0 broken links**; full-text links resolve; commissioned-by / resulting-amendment
   cross-links resolve into the overture layer.
5. Every roster (pcahistory / Digest Vol. 4) paper maps to a record, or is reported as a precise
   "not located (roster: M-GA p.N)" gap; papers found by heading but absent from the roster are
   surfaced — the catalogue reconciles to the roster (§4).

## 9. Honest limitations (anticipated, from the case/overture/RPR experience)

- **Topic grouping is semantic** (topic + alias + committee-name match); a few papers will land under
  the wrong topic or fail to link to their sibling (interim ↔ final) — needs a reconciliation audit
  against the pcahistory roster and honest "ungrouped" flags.
- **The roster is sparse on citations** — pcahistory gives an M-GA page for only some entries, so the
  heading sweep (§5.1) must backfill the rest; expect a labeled residue of "located by heading, not in
  roster" and "in roster, not located" (the "no silent caps" rule).
- **Scanned GA1–30** are the messiest (OCR + journal-body placement + loose titles); lower recall
  there, labeled — same as the CJB/early-RPR eras.
- **Outcome is subtle**: "received" vs. "adopted" vs. "adopted as amended" vs. "the position of the
  PCA" are easy to conflate and are exactly the distinction that matters; floor amendments to the
  recommendations (authoritative over the printed appendix) must be caught from the journal, and a
  generated outcome label is verified against the verbatim disposing sentence shown on the page.
- **The digest headnote is derived**, so a generated summary can be imprecise (the overture-title /
  inquiry-headnote caveat); it is always labeled, separated from the document, and checkable against
  the recommendations shown directly below it.
- **Scope edge**: routine *standing*-committee and agency annual reports (MNA, MTW, RBI, the
  Cooperative Ministries Committee, etc.) are **out of scope** — this catalogue is the *ad-interim /
  study* committees that produce position papers, per the pcahistory "Studies & Reports" roster, not
  the permanent committees' yearly operational reports.

## Sources

- **PCA Historical Center — "Studies & Reports"** (`pcahistory.org/pca/digest/studies/` and the
  index page's "PCA Studies & Reports, 1973–2021" section) and **PCA Digest Vol. 4 (1999–2018),
  "Study Committee Reports"** — the roster, the grain we reproduce, and the headnote source (§1, §4);
  never the page text.
- The PCA *Minutes of the General Assembly* (the `markdown/` corpus) — the verbatim content source:
  the ad-interim/study committee report appendices (and early journal-body reports) + the journal's
  disposing (and, optionally, appointing) paragraphs.
