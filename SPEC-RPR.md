# Review of Presbytery Records (RPR) — Specification

The fourth catalogue, alongside **Judicial Cases** (`SPEC-JUDICIAL-CASES.md`), **Overtures**
(`SPEC-OVERTURES.md`), and **Constitutional Inquiries** (`SPEC-INQUIRIES.md`). The General Assembly's
**Committee on Review of Presbytery Records (RPR/CRPR)** reviews every presbytery's minutes each year
and flags two kinds of defect: **exceptions of *form*** (clerical/procedural) and **exceptions of
*substance*** ("apparent violations of the Constitution"). This catalogue answers: *"Which presbyteries
have been cited for which constitutional defects, and was it ever resolved?"* — the constitutional-
compliance record of the church's middle courts. *(Status: design spec — not yet implemented.)*

## 1. The model (what an RPR record is)

> An **exception of substance** record is **one flagged constitutional defect in one presbytery's
> minutes** — the dated minute(s) at issue, the *BCO/RAO/WCF* provision(s) cited, and the verbatim
> description — together with its **multi-year lifecycle**: raised → the presbytery responds → a later
> GA finds the response **satisfactory** (closed) or **unsatisfactory** (continues), often over several
> cycles, until it is closed, escalated to a **BCO 40-5 citation** to the SJC, or left outstanding.

The atomic unit is the **exception threaded across years**, not a single year's row. (The user's
cardinal point: *"many exceptions span several years as they go back-and-forth between RPR/GA and the
presbytery."*) Exceptions of **form** are clerical and out of scope (optionally counted, not catalogued).

Distinct from the other layers: an RPR exception is **the GA reviewing a lower court's record** (BCO
40-1) — not a case (adversarial adjudication), an overture (a proposal), or an inquiry (a question about
meaning). It connects to the judicial layer only at the terminal step: persistent unsatisfactory
responses produce a **BCO 40-5 citation** that can become an SJC case.

## 2. Where RPR lives

- **The RPR committee report** — an appendix headed "REPORT OF THE COMMITTEE ON REVIEW OF PRESBYTERY
  RECORDS" (recent volumes: **Appendix Q**; the letter drifts by year). It has a roman-numeral skeleton:
  - **I/III** administrative lists (minutes received, late filers);
  - **IV. Citations** — presbyteries cited to the SJC under *BCO* 40-5 (the terminal escalation);
  - **VI. Report Concerning the Minutes of Each Presbytery** — the core, one numbered item per
    presbytery: `N. That the Minutes of <Presbytery> Presbytery: <vote>` with sub-parts
    - **a.** approved without exception;
    - **b.** approved with exception of **form** (dates);
    - **c.** approved with exception of **substance** — a numbered list, each
      `Exception: <date(s)> (BCO/RAO/WCF cite) – <verbatim description>`;
    - **d.** prior responses **found satisfactory** (each restates the exception + the presbytery's
      `Response:` and, when carried over, `Response [<year>]` / `Rationale [<year>]`);
    - **e.** prior responses **found unsatisfactory** (same shape; these persist into next year).
- **The journal** — the GA's adoption of the report (`NN-NN Review of Presbytery Records …`), where
  individual exceptions are sometimes debated/amended on the floor (authoritative over the appendix
  when they differ).

## 3. Eras (volume coverage)

- **Structured born-digital (GA31–52, 2003–2025)** — the clean target: Section VI with the explicit
  a/b/c/d/e structure above. Highest value, most tractable. (Volume of substance-exceptions grows
  sharply: tens early, 80–140/yr by GA45+.)
- **Early CRPR (GA18–30, 1990–2002)** — the committee exists (RPR report appears from **GA18, 1990**)
  but the format is looser and scanned; "exception of substance" is used less formulaically. Needs
  per-era format discovery, like the CJB case era.
- **Pre-GA18 (≤1989)** — no standing RPR committee in this form; out of scope.

## 4. The lifecycle & threading (the heart of the build)

Each exception has a **stable identity** that recurs verbatim every year it is alive. Two key regimes:

- **GA51–52 (2024–) — explicit ID.** Each exception carries a printed ID `YYYY-NN` (e.g. `2023-08` =
  "raised in the 2023/50th-GA report, that presbytery's 8th exception"), restated verbatim in later
  years' satisfactory/unsatisfactory sections alongside its original minute-date(s) and provision. The
  ID **encodes the first-sight year**, so the thread anchors itself. (Verified: GA52's
  `2023-08 — Apr 29/Aug 26 2022, BCO 15-2, "Administrative Commission…"` is exactly GA50 Arizona's
  section-c item 8.) These IDs are also the **ground-truth to audit** the tuple-matching below where
  they overlap (the analogue of the Digest validating case extraction).
- **GA31–50 (2003–2023) — no printed ID.** The identity is the restated tuple
  `(presbytery, original minute date(s), provision(s))` + description, repeated each year.

Each annual report either **raises** an exception (section c, year N) or **disposes** a prior response
(sections d/e, year N+k, which restate the original `Exception: <date> (cite) – <desc>` + `Response
[/year]`). The timeline is reconstructed by **grouping all appearances on the identity** (explicit ID
where printed, else the tuple + description similarity) and ordering by GA year:

    raised (GA N, c) → response found unsatisfactory (GA N+1, e) → … → satisfactory (closed)
                                                                  → … → BCO 40-5 citation (IV)
                                                                  → … → outstanding (no later mention)

The record's **final disposition** is the *last* GA action on it: **satisfactory** (closed),
**unsatisfactory / still outstanding** (open), **cited (BCO 40-5)** (escalated, links to a possible
SJC case), or **lapsed** (no further mention — labeled honestly, not assumed resolved). Because the
date(s) are the date(s) of the *defective presbytery minute*, they do **not** change across GA years,
which is what makes the thread joinable.

**Build direction (anchor-on-latest, sweep-all).** The richest appearance of a live exception is its
*latest* one — it carries the full response history, the final finding, and (GA51–52) the explicit ID
that names its origin year. So we **anchor each thread on its latest appearance and walk backward** to
first sight (cheap and reliable, especially via the explicit IDs). But backward-from-latest alone would
**miss any exception raised and closed before the latest window** (it never reappears), so we still
**sweep every year's section (c)** for first sightings and fold them into the same identity groups.
Backward-anchoring reconstructs everything still-active or recently-closed; the all-year sweep catches
the early-resolved ones.

## 5. Extraction approach (reuse the committee-report machinery)

1. **Region** — bound to the RPR appendix (the "REVIEW OF PRESBYTERY RECORDS" report) + the journal
   adoption paragraph, using the same appendix/`APPENDIX <X>` bounding as the other layers.
2. **Segment by presbytery** — split Section VI on `N. That the Minutes of <Presbytery> Presbytery:`;
   within each, split sub-parts a–e by their bold lead letters.
3. **Parse each part** — section c → `[{dates, provisions[], description}]`; sections d/e →
   `[{exception:{dates,provisions,description}, response, response_year, rationale, finding}]`.
   Provisions parsed as in the case/inquiry layers (`BCO \d+-\d+`, `RAO …`, `WCF …`, plus `RONR`,
   `Standing Rules`). Text **sliced verbatim**; LLM agents return line ranges / structured fields, code
   slices — no fabricated text (same rule as every other layer).
4. **Normalize presbytery names** — a canonical roster (Korean Eastern, Metropolitan New York, etc.),
   handling splits/renames across 35 years (the analogue of the case-roster work).
5. **Thread across years** (§4) — assemble each exception's timeline and final disposition.
6. **Born-digital first** (GA31–52), then extend to the scanned GA18–30 with per-era profiles.

## 6. Index (structure-first, like CASES.md / INQUIRIES.md)

`RPR.md`, the catalogue of **exceptions of substance**, with per-exception pages:
- grouped by **presbytery** (primary view) and cross-referenced by **provision** (so "which
  presbyteries were cited under *BCO* 13-9, and how did it go?" resolves) and by **GA year**;
- each row: presbytery · provision(s) · short description · **first raised** (GA, deep-linked) · **final
  disposition** (satisfactory / unsatisfactory-outstanding / cited 40-5 / lapsed) · link to the page;
- the page shows the **full verbatim timeline**: the exception as raised, each year's response and the
  GA's finding, deep-linked to every source page (`#ga<ord>-pN`), ending in the final disposition.

## 7. Invariants (acceptance)

1. Every catalogued exception threads to **exactly one** timeline; restatements across years collapse
   into that one record (not N duplicate rows).
2. The **final disposition** is the *last* GA action on the exception; "lapsed"/"outstanding" is the
   honest label when no closure is recorded — never assume resolution.
3. All text is **verbatim** minutes; provisions/dates/presbytery parsed, not invented.
4. Every row deep-links to its source page(s); 0 broken links; citations (BCO 40-5, IV) cross-link to
   the judicial-case layer where an SJC case resulted.
5. Exceptions of **form** are excluded from the catalogue (optionally tallied), per the "of substance"
   scope.

## 8. Honest limitations (anticipated)

- **Cross-year threading is semantic** — date+provision+description matching will mis-join or miss some
  (re-worded restatements, multi-date exceptions, presbytery renames); needs a reconciliation audit and
  honest "could not thread" flags, like the case roster reconciliation.
- **Scale** — thousands of exception-instances across 35 years; the *threaded* count is far smaller but
  the parsing is heavy (born-digital first keeps it tractable and high-quality).
- **Scanned GA18–30** are the messiest (OCR + looser format); expect lower recall there, labeled.
- **Presbytery identity** drifts (splits, renames, dissolutions) over 35 years — a curated roster is
  required and will be imperfect at the edges.
- **Form vs substance** is the committee's own classification; we follow the report's labeling rather
  than re-judging it.

## Sources

- The PCA *Minutes of the General Assembly* (`markdown/` corpus) — the verbatim content source: the
  RPR committee report appendix + the journal adoption, GA18 (1990) onward.
