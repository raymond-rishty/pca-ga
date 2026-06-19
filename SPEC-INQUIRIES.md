# Constitutional Inquiry Extraction — Specification

The third catalogue alongside **Judicial Cases** (`SPEC-JUDICIAL-CASES.md`) and **Overtures**. A Constitutional
Inquiry is a question of *constitutional interpretation* (Westminster Standards / *Book of Church
Order* / *Rules of Assembly Operations*) referred to the **Committee on Constitutional Business
(CCB)**, which answers with **non-binding advice**. This spec describes how to extract and catalogue
them; it follows the same patterns the case and overture layers already use. *(Status: design spec —
not yet implemented. The case layer is built per SPEC-JUDICIAL-CASES.md; inquiries reuse its machinery.)*

## 1. The model (what a Constitutional Inquiry is)

> A Constitutional Inquiry record is **one question of constitutional interpretation, its source,
> the CCB's advice, and the provisions at issue** — assembled from the two places it appears: where
> it was *posed/referred* and where the CCB *answered* it (often a different Assembly).

It is deliberately distinct from the other two judicial-ish layers:
- vs. **Judicial Case** — an inquiry is **abstract and advisory** (a question about what the
  Constitution *means*), not an adjudication of parties; the CCB's answer is **advice, not binding**
  (established when the 18th GA split the old Committee on Judicial Business into the CCB for
  inquiries and the SJC for cases: "responses to such inquiries … would have no binding on the
  Church as a whole … merely advice to the inquirer").
- vs. **Overture** — an overture *proposes* an action/amendment; an inquiry *asks what the existing
  Constitution requires*. (They interact: an overture can be *referred to the CCB as a constitutional
  inquiry* for advice — that referral is an inquiry.)
- vs. **RPR "Response"** — the Review-of-Presbytery-Records exception/response pairs (`**Response
  [2023]:** …`) are NOT inquiries; same word "response," different structure. Exclude them.

Authorities, as in SPEC-JUDICIAL-CASES.md: **document structure** owns where the text is; the question and the
advice are **sliced verbatim** from the minutes; metadata (provisions, source) is read from the text.

## 2. Where Constitutional Inquiries live

Two halves, frequently in **different Assemblies** (posed at GA N, answered at GA N+1):

- **Posed / referred** — a journal minute-paragraph, e.g.
  `22-73 Constitutional Inquiry — The Assembly received the following Constitutional Inquiry and
  referred the matter to the Constitutional Business Committee to report back to the 23rd General
  Assembly: "Does the right of dissent … entail the right to have the 'reasons' presented verbally
  to the GA?"`. Source is named ("from the Presbytery of Ascension", a commissioner, or "refer
  Overture N to the CCB as a constitutional inquiry").
- **Answered** — inside the **CCB report**: a committee appendix in born-digital volumes
  ("APPENDIX O — Committee on Constitutional Business") or a journal paragraph in scanned volumes
  ("`NN-13 Committee on Constitutional Business`"). The CCB report has roman-numeral sections
  (e.g. "II. Advice on Overtures", "Advice to the Stated Clerk", a Constitutional-Inquiries
  section); the advice reads "It is the opinion of the CCB that …" / "Our response to the Inquiry is
  as follows: 1. … 2. …".

Numbering: many years number them in the CCB report — **"Constitutional Inquiry #1 … #19"** (the
common form, ~per-GA). Others are unnumbered ("a Constitutional Inquiry from X"). Like overtures,
the number is GA-relative, not globally unique.

## 3. Eras

- **CCB era (GA18–present)**: the CCB handles inquiries; this is the main target. Present in ~32
  volumes.
- **Pre-CCB (GA1–17)**: the **Committee on Judicial Business** handled constitutional inquiries
  *and* judicial cases together; inquiries appear in the CJB report. (The same volume classification
  in `index/case_volume_class.json` applies; the CJB-split era already drives the case extractor.)

## 4. Extraction approach (reuse the case/overture machinery)

**Anchor on the Digest — Part II (Interpretations of the Constitution).** Part II *is* the
authoritative roster for this layer: the canonical list of CCB advices, each with subject,
provisions, and a Minutes citation (`M-GA p.N`). Parse it into a roster (as in
`SPEC-JUDICIAL-CASES.md` §4a) and drive identity + citation-anchored locate-verbatim + completeness
from it; the minutes remain the verbatim content source. This is especially valuable because the
inquiries layer is **unbuilt** — Part II hands us the ground-truth checklist to build against rather
than reverse-engineering it from a noisy table. Then, structurally, reuse both case and overture
machinery:

1. **Region** — bound to the CCB report (the "Committee on Constitutional Business" appendix /
   `NN-13` paragraph) plus the journal paragraphs that *pose* inquiries (`NN-NN Constitutional
   Inquiry`). Use the same appendix/section bounding as SPEC-JUDICIAL-CASES.md §3 (`page_anchor`-style markers,
   `APPENDIX <X>` headings) so adjacent committee reports don't bleed in.
2. **Segment** — within the CCB report, split on inquiry headers: `Constitutional Inquiry #N`,
   `Inquiry No. N`, or the roman-numeral CCB sub-section that introduces each inquiry/advice. A
   header that is a citation of a prior inquiry (mid-sentence, or with a `(MxxGA …)` back-reference)
   is not a header — reuse the `_CITE`/`_GAREF` guards from `25_case_extract.py`.
3. **Pair posed ↔ answered** — match by inquiry number within an Assembly, and by **subject/provision
   + source** across Assemblies (numbers don't align across GAs, exactly as CJB complaint↔report
   matching in SPEC-JUDICIAL-CASES.md). When the CCB reports back at GA N+1 to an inquiry posed at GA N, link them.
4. **Verbatim** — slice the posed-question span and the CCB-advice span from the markdown; never
   transcribe. For odd/heterogeneous volumes, use the locate-then-slice agent workflow (as for CJB
   and the SJC stragglers) returning line ranges.

## 5. Identity & metadata

Per inquiry: `{number (GA-relative, if any), source (presbytery / commissioner / "Overture N"),
question (verbatim), provisions [BCO/WCF/RAO citations parsed from the text], advice (verbatim CCB
opinion), posed_ga, answered_ga, disposition}`.

- **provisions** — parse `BCO \d+-\d+`, `WCF \d+`, `RAO \d+-\d+` from the question/advice (mirrors
  the case `bco_cited_as_s` field) so inquiries are searchable by the provision they construe — the
  core research use ("what has the CCB said about BCO 21-4?").
- **disposition** — advice given / inquiry found out of order or actually-a-parliamentary-question /
  referred onward / withdrawn. (The CCB sometimes rules an inquiry isn't a constitutional question
  — "this Constitutional Inquiry is actually a question concerning parliamentary procedure".)

## 6. Index (structure-first, like CASES.md)

`INQUIRIES.md`, grouped by Assembly, one row per inquiry linked to a verbatim page (question +
advice), reusing the deep-link page anchors (`#ga<ord>-pN`). Cross-Assembly linking exactly mirrors
SPEC-JUDICIAL-CASES.md's "decided at GA N":
- an inquiry **posed at GA N, answered at GA N+1** shows **"answered at (N+1)th GA"** in GA N and
  links to the advice page; the answer page back-links to where it was posed;
- a row that merely **cites** a prior inquiry (resolved at an *earlier* GA) is a citation, not an
  inquiry of this Assembly → omit (per the precedent-citation rule in SPEC-JUDICIAL-CASES.md §6).
Add Constitutional Inquiries to `18_structure.py` as their own node type (like overtures), so they
appear both in the structural index (queryable) and as headings in the rendered markdown — the
"two representations" rule from the overture work.

## 7. Invariants (acceptance)

1. Each inquiry maps to exactly one page (question + the CCB advice that answers it).
2. Every listed inquiry links to a verbatim page; cross-GA posed/answered halves cross-link; mere
   citations are omitted; 0 orphans / 0 broken links.
3. Page text is verbatim minutes; provisions/source parsed, not invented.
4. RPR "Response" pairs and overture *proposals* are NOT misclassified as inquiries.

## 8. Honest limitations (anticipated, from the case/overture experience)

- The CCB report's section structure drifts by year (numbered inquiries vs. prose "Advice on …");
  expect per-era header profiles as in SPEC-JUDICIAL-CASES.md §3, tuned against a ground-truth count.
- Posed↔answered matching across Assemblies is semantic (subject/source), so a few will need the
  agent locate-and-verify pass and a reconciliation audit, as the cases did.
- Pre-GA18 inquiries are entangled with the CJB case reports and will be the messiest (same scanned-
  OCR issues — space-shattering, parties-before-header — already handled in `25_case_extract.py`).
- "not located" remains the honest label for an inquiry the table/structure references but whose
  text can't be located, exactly as for cases.
