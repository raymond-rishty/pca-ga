# Judicial Case Extraction — Specification

How the PCA GA minutes are turned into one page per judicial case. This consolidates rules that
were added incrementally; they all serve a single model, stated first.

## 1. The model (what a case page is)

> A judicial-case page contains **exactly one adjudicated matter's verbatim record** — from the
> start of its own header through the end of its decision (judgment + all concurring/dissenting
> opinions) — and **nothing else**: no other case, no citation of another case, no docket/index
> listing, no report recommendations or journal text.

Every downstream rule is an answer to one of three questions: *what is a case header?*, *is this the
same case or a new one?*, *where does a case end?* — plus *where does the case belong* and *how is it
identified*.

Three sources, separated **by role**:
- **The minutes (document structure)** own *content* — boundaries, full body, opinions, sliced
  **verbatim**. Authoritative for what goes on the page; the only source of case text.
- **The Digest** (PCA Historical Center, *Digest of the Acts and Proceedings* — Part III for SJC
  cases) is the authoritative **roster**: the canonical list of which cases exist, each with its
  identity (number, parties, disposition + vote, dissent/concurrence flags via `D-Op`/`C-Op`,
  BCO/WCF provisions) **and a Minutes citation** (`M27GA … p.77`) that says *where to look*. It is an
  editor's summary, so it is the roster and the pointer — **never** the page text. *(Integration in
  progress; see §4a.)*
- **The `cases` table** is a noisy pre-Digest **fallback** for identity, used only where the Digest
  is silent and always validated against the decision text (its page ranges, `ga_ordinal`, and even
  `canonical_number` are unreliable — the source of the Stringer/Korean-Northwest/`31-3` errors).

Text is always **sliced verbatim** from the markdown. LLM agents only ever return *line ranges*;
code slices them. No case text is model-generated.

## 2. Volume classification (`index/case_volume_class.json`)

Three reporting eras, each with its own extractor:
- **SJC-decision** (GA19–52): contiguous per-case decisions → `25/26_*` (regex) or `28` (located).
- **CJB-split** (GA4–18): complaint summaries + separate §10-79 commission reports, matched by
  party names → `27` (located).
- **early-CJB** (GA1–3): GA1–2 have no judicial cases; GA3 one complaint.

## 3. SJC segmentation (`25_case_extract.py`) — the core

**Header recognition.** A line is a case header if it matches a recognizer and is not a citation:
- *Profiles* (keyword forms, all OCR space-tolerant via `_st`): P1 `[JUDICIAL] CASE [No.] NN`;
  P2 extended (`SJC NN`, `STANDING JUDICIAL COMMISSION CASE NN`, `JUDICIAL MATTER NN`, `CASE NUMBER
  NN`, `CASE Nos.`, optional disposition/`MAJORITY REPORT ON` lead); P3 disposition-led/bare bold
  number (`**COMPLAINT 2010-24**`, `**2010-18 …**`); P4 bare number line (marker-gated).
- *Not a header* (citations of a prior case inside reasoning): `_CITE` = `NUMBER: parties`;
  `_GAREF` = a line containing a `(MxxGA …)` back-reference.
- *Marker gate* (per-volume knob): a header counts only if a **decision marker** (`_MARK`: Summary
  of Facts / Statement of the Issue / Decision / Judgment / Reasoning / out of order / dismissed /
  roll-call vote / …) appears within 15 lines — rejects docket rows. Searched **per line** (the
  `^`-anchored markers) **and** whitespace-collapsed (markers wrapped across a line).

**One case vs. several (consolidation).** A header joins the previous block iff:
- it repeats a number already in the block (an opinion re-run), **or**
- siblings named on the *same* header line (`_SIB`: `CASE X AND CASE Y`, `2009-25 and 2009-26`), **or**
- it is a near (≤45 lines), **same-year** header **and** (a) no decision marker lies *between* the
  two headers **and** (b) the respondent presbytery (`_presby_near`, from `… VS. <Name> Presbytery`)
  is not *different*.

  Rationale: a genuine consolidation is bare headers sharing **one** decision (nothing decisional
  between them; citations like 2010-18…23 have no `vs.` so no presbytery to differ). Two separate
  decisions each conclude with their own judgment, or name a different presbytery.

**Boundaries.** A block starts at its header and ends at the **first of**: the next case header,
the report section-ender (`Respectfully submitted` / `Appendix X` / `Index`), or the **journal
resuming** (`<GA-ordinal>-NN Title`, e.g. `21-72 Recess` — case numbers are year-prefixed, never
`<ga>-NN`). This stops the last case swallowing the report's recommendations/journal tail.

**Drop non-cases.** After segmentation: drop docket/index *listing* blocks (≥3 numbers and
<150 chars/number) and **short markerless** blocks (<250 chars with no `_MARK`) — a docket line or
status note, never a real decision (which always carries a marker). Disposed-without-opinion matters
are recovered as stubs (§5).

## 4. Per-volume autotune (`autotune` → `index/sjc_strategy.json`)

The header format drifts across 34 volumes, so each volume's knobs `(broad, marker, bare)` are chosen
to maximize, against the whole-table number *universe*:

    score = real − 3·junk − 2·overmerge − 1·giant

`real` = block numbers that are real cases anywhere; `junk` = numbers found nowhere; `overmerge` =
numbers crammed past ~6 into a block; `giant` = a single-number block ≫ the volume median (only a
mild penalty — a long block is usually a long opinion, not a swallow). A volume **promotes** to live
pages when clean (`junk==0`, `overmerge≤2`) and complete (`recall≥0.7`, or a large clean extraction
≥15 real over ≥8 blocks — recall is denominator-noisy because the table mis-files cases).

## 4a. The Digest as roster (planned — supersedes the table for identity & completeness)

Parse the Digest (Part III) into a **roster table** keyed by case number:
`{number, parties, M-GA + page, disposition + vote, dissent (D-Op/C-Op), BCO/WCF provisions}`. It
then drives three things the noisy `cases` table did poorly:
- **Identity** — titles, disposition, and dissent come from the roster (authoritative), replacing the
  table lookup in the renderers (and removing the title-vs-content guard's reason to exist, since the
  roster's parties are correct by construction).
- **Citation-anchored extraction** — the roster's `M-GA p.N` is *where to look*: drive the
  locate-then-slice pass (§5) directly from it (jump to that GA + page, slice verbatim) instead of
  re-discovering headers. This is far more reliable than format-drifting header regexes.
- **Completeness** — the roster is the definitive checklist. Every rostered case must map to exactly
  one verbatim page; a gap is a real, actionable "not located" with a precise pointer (not a table
  phantom). Reconcile extracted-vs-roster and report the diff. This replaces `recall`-vs-table (§4),
  which is noisy, with `coverage`-vs-Digest, which is authoritative.

The minutes stay the content source; the Digest never supplies page text (it's an editor's summary).

## 5. CJB, stragglers, stubs (verbatim from located ranges)

- **CJB** (`27`, from `cjb_cases.json`) and **SJC stragglers** (`28`, from `sjc_located.json`):
  LLM agents located each case's spans (complaint + §10-79 adjudication, or a full SJC decision);
  code slices verbatim and merges into `case_pages_map.json`.
- **Cross-volume dedup**: one case number can appear in several volumes (real decision + later
  citation). Keep, per number, the page that is **not a fragment**, then whose **volume-year is
  closest to the docket year** (a decision is same/few-years-after; a citation is many years later),
  then the longest. Delete the losers; result is exactly one page per number, zero orphans.
- **Stubs** (`29` → `stub_pages.json`): a matter disposed without a published opinion (out of order
  / withdrawn / abandoned / moot / not acceded to; incl. docket abbrevs `OO`/`WD`) gets a small page
  quoting the **verbatim disposing sentence**. The search spans the table-GA volume **and the next
  two** (cases are often disposed a GA or two later than filed).

## 6. Index (`20_markdown_index.py`) — structure-first

`CASES.md` is built **from the extracted pages**, per Assembly, not from the table:
- decided cases (CJB located + SJC structure) and stubs are listed and linked;
- a leftover table row is labeled by what it actually is: **decided at GA N** / **disposed at GA N**
  (the case was only *listed* here — deferred to a later GA or cited from an earlier one — and links
  to where it was resolved; number recovered from the title if the number field is blank);
  **reference / no separate decision**; **not yet re-extracted** (whole volume pending);
  **no judicial cases in this volume** (GA1–2).

## 7. Invariants (acceptance)

1. Every case number maps to **exactly one** page.
2. **0 orphans** (no page unreferenced by the index) and **0 broken links**.
3. Every listed decision links to a verbatim page; every other row is honestly labeled (no false
   "not yet").
4. Page text is verbatim minutes; identity (title/disposition/dissent) comes from the Digest roster
   (§4a) where available, else the validated table/caption.
5. *(With §4a)* every Digest-rostered case maps to a verbatim page, or is reported as a precise
   "not located (Digest: M-GA p.N)" gap — the extracted roster reconciles to the Digest.

## 8. Honest limitations

- Several thresholds are **tuned, not derived**: GAP=45, listing `<150 c/number`, fragment `<250 c`,
  giant `>6×median`, dedup year window. They hold on the corpus but are empirical.
- Header/citation forms are **open-ended**; new phrasings can still slip a citation through or miss a
  header. The layered guards (profiles, `_CITE`, `_GAREF`, marker, presbytery, listing/fragment
  drops, boundary enders) cover every form seen so far; the durable backstop is the invariants in §7
  plus the regex↔agent reconciliation audit.
- `recall` vs the table is noisy (mis-filed `ga_ordinal`), so it gates promotion loosely and is not
  trusted as a completeness proof.
- Parties-before-header volumes (e.g. ga21 `WILLIAM A. CONRAD … / JUDICIAL CASE NO. 92-6`) attach the
  caption to the previous block's tail — cosmetic, cases still separate.
- Many of the above are **artifacts of having no authoritative roster** — they were worked around
  reactively against the noisy `cases` table. The Digest (§4a) is the durable fix: it replaces
  `recall`-vs-table with `coverage`-vs-Digest and supplies correct identity, so the title/citation/
  numbering guards become belt-and-suspenders rather than load-bearing.

## Sources

- PCA Historical Center, *Digest of the Acts and Proceedings of the General Assembly* —
  Part I (Actions), Part II (Interpretations of the Constitution → `SPEC-INQUIRIES.md`),
  Part III (Judicial Cases, SJC). The roster/identity/where-to-look authority (§1, §4a).
- The PCA *Minutes of the General Assembly* (the `markdown/` corpus) — the verbatim content source.
