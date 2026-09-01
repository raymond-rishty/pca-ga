# Footnote identification model

Status: experimental evidence model with a guarded Markdown materialization step. The detector remains suitable for measurement and review; only reviewed `v3` scan reports should be used to rewrite published minutes.

## Model contract

The detector keeps independent witnesses and produces `confirmed`, `candidate`, or `ambiguous` classifications. It then clusters overlapping native/OCR observations into one logical marker, so corroboration increases confidence without double-counting markers or links. The classification layer is deterministic for a fixed PDF, OCR artifact, layout artifact, and legacy witness. It never treats a raw inline digit as a footnote solely because a footnote block exists. The `links` field contains accepted (`confirmed`) links only; paired candidates are retained in `review_links` and in the marker clusters.

The evidence implementation is [`scripts/footnote_evidence.py`](../scripts/footnote_evidence.py), with focused tests in [`tests/test_footnote_evidence.py`](../tests/test_footnote_evidence.py). The page-bounded evaluator is [`scripts/evaluate_footnote_evidence.py`](../scripts/evaluate_footnote_evidence.py), scope candidates are derived by [`scripts/derive_footnote_scopes.py`](../scripts/derive_footnote_scopes.py), corpus discovery is driven by [`scripts/scan_footnote_corpus.py`](../scripts/scan_footnote_corpus.py), and gold labels live under `benchmark/footnote_gold_*.json`.

The publication boundary is [`scripts/79_apply_footnotes.py`](../../scripts/79_apply_footnotes.py). It consumes only `confirmed` links from the scanner's `pca-ga.footnote-corpus-scan.v3` report, uses the retained OCR line/context witness to locate the corresponding text in `markdown/`, and writes native CommonMark references/definitions. Markers inside raw HTML tables use linked `<sup>`/`<a>` markup because native `[^...]` syntax is not parsed inside an HTML block. [`scripts/54_apply_layout_render_to_minutes.py`](../../scripts/54_apply_layout_render_to_minutes.py) can invoke this materializer after its layout render with `--footnotes-report`; without `--apply`, both stages remain dry-run/audit-only.

All boxes in the output are normalized to PDF points. The sidecar records the original evidence source, marker text, line context, typography fields where available, note block, pairing, sequence support, score, and reasons.

## Evidence hierarchy

1. **PDF-native typography.** For born-digital pages, PyMuPDF raw character/span data supplies font size, origin, bbox, font flags, and computed superscript information. Reduced size plus an inline/elevated digit is the strongest marker evidence.
2. **OCR geometry and text.** Paddle OCR supplies lines and word regions. Because the current artifact can merge a marker into the preceding word, an interpolated marker box is explicitly marked approximate.
3. **Optional scan glyph geometry.** Tesseract hOCR character boxes can supply per-character height and baseline/elevation evidence. Word-only hOCR does not contain enough geometry for this purpose, so the adapter also accepts the matching Tesseract `.box` sidecar and records whether true character boxes were present. The source is recorded as `tesseract_hocr`; it remains a witness, not an authority. The targeted 40-page Tesseract.js experiment did not recover any additional gold markers and introduced false positives in numbered-list controls, so this witness is not enabled as a production promotion path yet.
4. **Footnote blocks.** PP-Structure `footnote` and credible `vision_footnote` regions are retained as block witnesses; common visual mislabels such as table descriptors and numbered resolutions are rejected. An explicit OCR `Footnotes`/`Footnote 1` heading is also retained. The conservative lower-page run of numbered definitions is used only when layout inference did not run; this prevents PP-Structure's ordinary `text`/`table` regions from being mistaken for notes.
5. **Document structure and case metadata.** Existing case ranges and physical structure-section starts provide deterministic scope candidates. Overlapping case ranges are merged into reviewable components; uncovered pages inherit a disjoint structure-section scope.
6. **Legacy checkpoint.** A page-bounded earlier Markdown extraction can contribute marker values, but cannot replace current source geometry. Values missing from current OCR are reported as `legacy_only_marker_values` and remain review-only; the corpus scanner can load the checkpoint with `--legacy-git-ref` and a deterministic path template.

## Deterministic rules

- Candidate marker values are one-to-three digit runs or Unicode superscript runs occurring in inline context. Weak OCR/native digit suffixes attached to a word are retained as lexical witnesses only when they match an explicit note value and sequence evidence; a native suffix with true superscript/reduced-size typography stays in the strong geometry stream. Standalone parenthesized numeric tokens are eligible inside table geometry under the same explicit-note constraint.
- Line-leading numbers are not promoted as inline markers.
- Citation-like contexts (scripture references, page/volume references, hyphenated codes, dates, and slash/colon-delimited numbers) are suppressed unless independent superscript or legacy evidence exists.
- Written-date days (for example, `February 1, 2002`) are treated as citation/date context; this prevents a paired note number from promoting an ordinary calendar date.
- OCR-only candidates without a paired note or explicit superscript remain ambiguous. A scan witness paired only to an unlabeled heuristic bottom run remains a `candidate`, because tables and numbered lists can produce the same pattern; promotion requires an explicit footnote block/heading or independent native/legacy corroboration.
- A note entry must be found in a recognized note block or explicit footnote section.
- Every witness honors structural exclusions from PP-Structure, including table, header, footer, figure, and image regions. This applies to hOCR character boxes as well as native and Paddle observations.
- A native superscript/reduced-size glyph may cross a non-table structural exclusion only when it is inline at the end of the structural block, matches an explicit note value, and is not citation-like. This handles PP-Structure figure/title mislabels without reopening ordinary structural numbers.
- A table region is reopened only for a true superscript/elevated glyph witness, an exact attached word-suffix witness with sequence support, or a standalone parenthesized token; in every case the value must occur in an explicit footnote block or heading. Reduced font size or an ordinary parenthesized value by itself never reopens a table; this preserves currency/table and budget/list numbers as negative evidence while handling table footnotes such as GA40 page 208 and the GA27/GA33 table cases.
- Equal marker/note values are paired on the same page by default. A cross-page pair is bounded by a two-page window and requires an explicit scope file.
- Increasing neighboring values in both marker and note streams add sequence evidence; interior OCR spikes and symbol-footnote prose are excluded from note labels. A missing label may be recovered only from a run of at least three inline numeric witnesses that appears in reading order, shares at least one value with a recognized note block, and is not already represented elsewhere on the page. Exact native suffixes may join that run one step at a time when each value is adjacent to an already observed marker and explicit note value. A local citation-like warning may remain on one witness without breaking the run, but it still affects that witness's classification; repeated labels are never synthesized across multiple note blocks.
- When a scope file is supplied, a cross-page pair is allowed only when both pages resolve to the same unique scope. Overlapping or unmatched scopes are reported and cannot silently bridge documents. Without a scope file, the output explicitly records the conservative `same_page_only` policy.
- Native/OCR observations with the same value and overlapping/nearby boxes are retained as separate witnesses but clustered into one logical marker. Links are emitted once per logical marker/note pair.
- A non-superscript OCR number at the end of a sentence can be confirmed only when it matches a structurally explicit note block; this recovers markers such as GA18 page 164's terminal `76` while date/list lookalikes remain suppressed.
- If OCR moves a sentence-terminal marker onto a numeric-only line, that line is admitted only when it is vertically adjacent and near the preceding sentence's right edge; the witness remains explicitly labeled `split_line_continuation`.
- If PP-Structure preserves a text block ending in punctuation plus digits while OCR isolates those digits, the detector can rejoin them only when the numeric line falls inside the same layout block and the value occurs in an explicit note entry. Numeric citation tails such as `BCO 40-5.2` do not qualify.
- If the native PDF layer splits a reduced-size/elevated marker into a neighboring text block on the same visual line, the detector can retain it only when the marker begins within 14 PDF points of the preceding line's right edge, the line boxes overlap vertically, the preceding text has a word/punctuation boundary, the value is an explicit note label, and sequence support is present. Ordinary line-leading numbers remain excluded.
- A marker after closing quotation/punctuation may contain intervening whitespace; the context rule preserves that attachment, including GA23 page 118's marker `7`.
- When a scanned note label is collapsed into its prose (for example `1Review`), the detector can recover the missing label only at a note-block line start. A recovered leading label is inserted before the original line-level entries; the original OCR order is otherwise preserved so content adapters cannot reorder valid sequences.
- When an already recognized note block has a PDF text layer, native line labels are merged only by same-block geometry. Longer native labels can correct truncated OCR values such as `4`→`43` or `15`→`156`; exact native labels can restore labels omitted by Paddle, while the block source remains visible for audit.
- Note labels that are indented relative to the block's label column, and wrapped parenthesized citation tails such as `190)and ...`, remain retained evidence but are marked sequence anomalies rather than note targets.
- The corpus scanner emits two separate review classes: unresolved marker decisions and recognized note entries with no marker pair in the selected pages. The latter is the recall audit for OCR omissions; neither class is emitted as an accepted link.
- Ambiguous pairs remain in marker evidence for audit but are not emitted as accepted links. Candidate pairs are emitted only under `review_links`; they cannot reach a renderer through `links`.

## Validation observations

The first runs established these behaviors:

- GA40 pages 361–362: the native superscript `1` on page 361 pairs with `Footnote 1` on page 362; the current Paddle OCR witness agrees, although its marker box is approximate.
- GA40 page 538: native markers `1` and `2` pair with the PP-Structure footnote block; OCR provides corroborating witnesses while parenthesized `(2)` and BCO/date numbers remain ambiguous.
- GA40 page 541: native marker `1` pairs with the PP-Structure footnote block; vote totals and legal citations are not promoted.
- GA14 pages 486–489: current OCR identifies markers `1`–`4` and pairs them with the explicit `Footnotes` section. The checkpoint adds marker `5`, which current OCR renders without sufficient inline geometry; with the checkpoint witness it becomes confirmed. Page 487's apparent scripture citation `2` is rejected as ambiguous.
- GA18 page 164: the terminal OCR marker `76` pairs with the structurally explicit footnote block; calendar and paragraph-reference numbers on the same page remain ambiguous.
- GA23 pages 117–118: the marker sequence `1`–`7` is recovered, including marker `7` after a closing quotation and intervening whitespace.
- GA32 page 62: the detector keeps the real superscript-linked marker `1` and rejects the calendar-date lookalikes (`February 1, 2002` and `July 1, 2002`); the page-bounded gold check is exact.
- GA44 page 64 is a multi-source recovery case: Paddle and Tesseract omit or misread the table marker `¹`, while PyMuPDF supplies the superscript geometry and PP-Structure supplies a note block whose first label is collapsed into `1Review`. The collapsed-label rule restores the note sequence and confirms the native marker; the OCR omissions remain visible as source-level limitations.
- GA21 pages 324 and 326, GA22 page 572, and GA40 page 767 provide additional positive budget-note controls. The detector recovers the visible note sequences, including GA21's continued 3–7 section, without promoting the surrounding budget-table numbers.
- GA40 page 636: native markers `123`–`128` pair with a lower-page numbered note run even though the heading `Footnotes, Glossaries, and Other Paratextual Solutions` is correctly treated as a body heading rather than a note block.
- Scoped GA40 validation reduces 47 marker witnesses to 39 logical clusters and 14 duplicate witness-links to 10 logical links, while retaining native/Paddle source agreement on the accepted links.
- Scoped GA14 validation retains five confirmed links on the explicit `Footnotes` page; the checkpoint contributes marker `5`, while unpaired checkpoint values on page 488 remain candidates or legacy-only observations.
- A 30-page stratified GA11 benchmark produced zero confirmed markers and zero links. Two former citation false positives were corrected by applying the citation guard before the confirmation threshold; two catechism/Confession references remain visible as candidates for review rather than being promoted.
- Visually adjudicated GA15 pages 440, 456, 457, and 459 recover all 18 visible marker/link pairs, including the quoted/punctuated markers and the 50–53 note sequence after rejecting an OCR citation number as a note label.
- The first same-page-only layout discovery scan across GA01–GA52 covered 7,865 pages and found 615 note-block pages, 531 accepted logical links, 207 review candidates, and one review-only link. Those historical counts are retained as a baseline; they are discovery leads, not accuracy estimates.
- The scan exposed and fixed three concrete false-positive classes: citation numbers promoted by pairing score, numeric rows inside PP-Structure tables, and ordinary numbered lists at the bottom of layout pages. An additional PP-Structure filter prevents symbol-footnote prose such as `1 graduate...` from becoming a numeric note label.
- GA40 page 208 provides a positive table exception: the native superscripts `1` and `2` in the table pair with the PP-Structure `SPECIFIC COMMITTEE AND AGENCY NOTES` block. The table guard retains exactly those two elevated glyphs and rejects the ordinary reduced-size currency digits; the page-bounded gold check is exact (2/2 markers and 2/2 links).
- GA18 page 164 provides a positive terminal-marker case: OCR `76` at the end of the sentence pairs with a PP-Structure footnote block and is confirmed. GA23 pages 117–118 provide a quoted/punctuated sequence case; markers `1`–`7` and links are recovered exactly.
- The current 30-page GA11 Tesseract tranche has both hOCR and `.box` sidecars. With PP-Structure layout supplied, it produces zero confirmed markers and zero accepted links, while retaining 24 review candidates and 10 review-only links. The visible table on page 303 produces no accepted marker after structural exclusion. In the no-layout regression, the table still yields review-only geometry, but zero confirmed markers and zero accepted links, so the scan witness is not discarded while it is prevented from silently becoming accepted output.
- A no-layout hOCR experiment showed why the guard is necessary: Tesseract character boxes made ordinary table digits look reduced/elevated, and the unlabeled bottom-run heuristic paired them with false note numbers. Those observations remain auditable candidates; they are not sufficient for confirmation without an explicit block or independent witness.
- Automatically derived GA40 scopes combine 17 indexed case ranges into two non-overlapping components plus structure-section ranges; the representative GA40 gold evaluation remains exact (10/10 markers and 10/10 links) when driven by the derived scope file rather than the hand-authored scope file. The derived files remain marked `derived_pending_review` until the raw overlap groups are adjudicated.
- Scope derivation now completes for all 52 available volumes: 52 non-overlapping derived scope lists covering 2,637 ranges, with 645 indexed case ranges and 60 retained overlap groups. These are safe pairing candidates, not silently authoritative document boundaries, until the overlap groups are reviewed.
- The evaluator now reports both exact-set and occurrence-level metrics, so repeated same-valued markers cannot be hidden by set deduplication. The current GA14, GA15, GA18, GA23, GA40, GA11-negative, and GA07-negative gold slices all pass their strict checks; these remain small adjudicated slices, not corpus-wide estimates.
- The lexical-suffix experiment recovered visible GA26 page 112 markers 5–7 from exact native text after OCR omitted them, using the existing 2–8 note sequence as corroboration. The standalone parenthesized-table witness then recovered GA27 page 234 values 1–3 and GA33 page 451 value 1; restricting it to an exact `(n)` line avoided the GA21 budget-list false positive `(7)` in ordinary prose.
- Sentence-boundary handling recovers the true terminal markers on GA24 page 183 and GA30 page 173 without reopening citation-like numbers; the adjacent split-line rule recovers GA26 page 114 marker 15, and the PP-Structure trailing-suffix rejoin recovers GA48 page 694 marker 9. The layout rejoin has a regression guard for numeric citation tails.
- A native cross-block visual-continuation rule recovers GA51 page 839 markers 5 and 6: each is a reduced-size native glyph whose block begins at the preceding body's right edge, and the explicit 4–6 note sequence supplies the required corroboration. The rule remains review-only for ordinary line-leading digits.
- A 42-page visually adjudicated corpus sample is stored in [`benchmark/footnote_gold_corpus_adjudicated_sample.json`](../benchmark/footnote_gold_corpus_adjudicated_sample.json), with measurements in [`reports/footnote_corpus_adjudicated_sample_eval.json`](footnote_corpus_adjudicated_sample_eval.json). After the structural, native-label, and sequence-recovery rules, it gives note-block precision/recall of 100% (36/36) and note-label occurrence precision/recall of 100% (112/112). This is an expanded measurement slice, not a corpus-wide estimate.
- The 40-page marker gold slice is stored in [`benchmark/footnote_gold_marker_sample.json`](../benchmark/footnote_gold_marker_sample.json), with the refreshed current and checkpoint measurements in [`reports/footnote_marker_sample_eval_current_refresh.json`](footnote_marker_sample_eval_current_refresh.json) and [`reports/footnote_marker_sample_eval_legacy.json`](footnote_marker_sample_eval_legacy.json). Current evidence confirms 57/61 marker labels and links (100% set precision; 93.4% recall); adding the 99d6ec9 checkpoint witness confirms 58/61 (100% set precision; 95.1% recall). The remaining misses are concentrated in one scan-only table superscript and one current-OCR omission, with the checkpoint-only marker still lacking current geometry; this remains a recall gap, not a reason to loosen the confirmation rule. Note-block detection remains exact on the expanded slice (36/36 pages; 112/112 note labels).
- The targeted hOCR/box diagnostic is [`reports/footnote_hocr_marker_sample_eval.json`](footnote_hocr_marker_sample_eval.json). Adding Tesseract.js character boxes left recall at 50.8% (31/61) and reduced precision to 58.5% by introducing 22 false positives, mostly in budget/list controls. The current sidecars therefore do not provide a safe independent witness for promotion; a future recall experiment should use a higher-quality glyph-baseline source or tightly constrained image crops and the same negative controls.
- The refreshed scope-aware layout-backed discovery scan covered 7,865 pages across GA01–GA52 and found 429 note-block pages. The baseline produced 792 confirmed logical markers, 816 accepted links (155 cross-page), 160 candidate clusters, and 2,185 targeted review items: 2,126 marker decisions plus 59 note entries without any marker pair in the selected pages. With the checkpoint witness, it produced 793 confirmed markers, 817 accepted links, 179 candidate clusters, and 2,204 review items: 2,145 marker decisions, 58 note-only items, and one legacy-only review item. The cross-block visual-continuation rule accounts for two additional GA51 confirmations; the checkpoint-only marker remains review-only when current geometry is absent. The 52 scope files remain `derived_pending_review`, and 609 selected pages have no unique derived scope; 49 marker decisions are explicitly blocked by scope boundaries. These are discovery counts under derived-scope policy, not accuracy estimates; every accepted page and every note-only review item still requires gold adjudication before rendering.
- The refreshed scoped reports are [`reports/footnote_scan_all_52_scoped_review.json`](footnote_scan_all_52_scoped_review.json) and [`reports/footnote_scan_all_52_scoped_review_legacy.json`](footnote_scan_all_52_scoped_review_legacy.json). Their `review_queue` records the page, scope, value, geometry, source, and reason for each unresolved marker, legacy-only witness, or unpaired note entry; ordinary ambiguous digits without note/block/sequence evidence remain abstentions rather than queue noise.

The compact, reproducible same-page baseline is [`reports/footnote_scan_all_52_authoritative.json`](footnote_scan_all_52_authoritative.json). The current scope-aware review output is [`reports/footnote_scan_all_52_scoped_review.json`](footnote_scan_all_52_scoped_review.json). Both retain only positive/review pages; the detector's page-level reports retain the complete evidence when a page is selected for adjudication.

Current verification matrix:

| Slice | Pages | Result |
| --- | ---: | --- |
| GA14 explicit Footnotes | 486 | 5/5 markers and 5/5 links; exact |
| GA14 judicial cross-page sequence | 106–107 | 2/2 markers and 2/2 links; exact |
| GA15 explicit footnote blocks | 440, 456–457, 459 | 18/18 markers and 18/18 links; exact |
| GA40 native/checkpoint/derived scopes | 361–362, 538, 541, 636 | 10/10 markers and 10/10 links; exact |
| GA40 table superscript exception | 208 | 2/2 markers and 2/2 links; exact |
| GA18 terminal explicit block | 164 | 1/1 marker and 1/1 link; exact |
| GA23 quoted/punctuated sequence | 117–118 | 7/7 markers and 7/7 links; exact |
| GA32 date/citation controls | 62 | 1/1 marker and 1/1 link; exact |
| GA11 negative controls | 140 plus seven layout/table/list pages | 0 false-positive markers and 0 false-positive accepted links |
| GA07 numeric negative controls | 118, 157 | 0 false-positive markers and 0 false-positive accepted links |
| 40-page marker gold slice | 40 | Current 57/61; checkpoint 58/61; both 100% set precision, 93.4%/95.1% recall; not release-ready |

The candidate and review-link counts are intentionally not treated as detections in this matrix; they are the audit queue for future gold expansion. The all-volume scan counts above are likewise leads, not precision/recall claims.

These are behavioral checks, not precision/recall claims. A scan-adjudicated gold set is still required before applying classifications to the full corpus.

## Remaining gates before rendering

1. Review and promote the derived non-overlapping scope files from case/page metadata and document headings; the derivation tool now preserves raw overlaps and fills uncovered pages with structure-section ranges, while the scoped scan records unresolved pages and refuses silent cross-scope links.
2. Keep the current Tesseract.js hOCR/`.box` path diagnostic-only: the 40-page extension added no recall and introduced 22 false positives. If the marker-recall gate requires improvement, test a higher-DPI/true-baseline OCR source or tightly cropped OpenCV/CV measurements on table-marker pages, always against the existing negative controls; do not treat word-only hOCR or ordinary reduced glyph height as sufficient evidence.
3. Adjudicate the scoped `review_queue`, starting with the 59 baseline (58 checkpoint) note entries without marker pairs, the one legacy-only GA24 review item, and the highest-evidence marker items. Then expand the verified gold set beyond the current 42-page sample to cover GA14, GA18/23 context variants, GA32 date controls, GA40 judicial/table cases, ordinary numbered paragraphs, citations, vote totals, and pages with no notes. Use the measured false-positive list/table cases to refine note-block boundaries before changing marker thresholds.
4. Measure marker precision/recall, note-block precision/recall, and marker-to-note pairing accuracy separately for vector and scanned pages.
5. Apply only a reviewed `v3` report. The materializer preserves candidates, ambiguities, citation-shaped numbers, unlocated markers, and unlocated definitions for review rather than silently altering text; its audit records intended links separately from actually applied markers and definitions.
6. Consider PP-Structure fine-tuning or a VLM only if the measured block/marker recall remains inadequate after the evidence model is complete.

Example runs:

```powershell
& .\ocr-bakeoff\envs\common\Scripts\python.exe .\ocr-bakeoff\scripts\footnote_evidence.py `
  --pdf .\minutes\40th_pcaga_2012.pdf `
  --ocr-dir .\ocr-bakeoff\corpus\ga40\paddle_ocr_json `
  --layout-dir .\ocr-bakeoff\corpus\ga40\paddle_layout_json `
  --legacy-git-ref 99d6ec9976a2c6d1c29c0f08045ccddb96218a7e `
  --legacy-git-path markdown/ga40_2012.md `
  --pages 361-362,538,541 `
  --scope-json .\tmp\footnote_scopes_ga40_2012_derived.json `
  --output .\tmp\footnote_ga40.json
```

To reproduce the scope-aware discovery and review queue on a representative set:

```powershell
& .\ocr-bakeoff\envs\common\Scripts\python.exe `
  .\ocr-bakeoff\scripts\scan_footnote_corpus.py `
  --volumes ga14,ga23,ga40 `
  --scope-dir .\tmp `
  --output .\tmp\footnote_scan_representative_scoped.json
```

For scan geometry, add `--hocr-dir <directory> --box-dir <directory>` (and adjust `--hocr-dpi` if the hOCR was generated from a different render resolution). The hOCR sidecar is optional; missing character boxes do not cause the detector to invent typography. Supply `--layout-dir` whenever PP-Structure output is available so structural exclusions apply to every OCR witness.

To reproduce a gold check:

```powershell
& .\ocr-bakeoff\envs\common\Scripts\python.exe `
  .\ocr-bakeoff\scripts\evaluate_footnote_evidence.py `
  --report .\tmp\footnote_ga15_layout_hits.json `
  --gold .\ocr-bakeoff\benchmark\footnote_gold_ga15.json `
  --strict
```

To measure the corpus-level note-block and note-label slice:

```powershell
& .\ocr-bakeoff\envs\common\Scripts\python.exe `
  .\ocr-bakeoff\scripts\evaluate_footnote_corpus.py `
  --scan .\ocr-bakeoff\reports\footnote_scan_all_52_scoped_review.json `
  --gold .\ocr-bakeoff\benchmark\footnote_gold_corpus_adjudicated_sample.json `
  --output .\ocr-bakeoff\reports\footnote_corpus_adjudicated_sample_eval.json
```

To materialize reviewed links in the published Markdown:

```powershell
& .\ocr-bakeoff\envs\common\Scripts\python.exe `
  .\scripts\79_apply_footnotes.py `
  --report .\tmp\footnote_scan_reviewed_v3.json `
  --ga ga14,ga40 `
  --output .\tmp\footnote_apply_report.json `
  --apply
```

The default is a dry run. Review the audit report and the Markdown diff before
passing `--apply`; the wrapper in `54_apply_layout_render_to_minutes.py` uses
the same rule when `--footnotes-report` is supplied.

To derive reviewable scope candidates from the indexed case ranges and physical
structure metadata:

```powershell
& .\ocr-bakeoff\envs\common\Scripts\python.exe `
  .\ocr-bakeoff\scripts\derive_footnote_scopes.py `
  --volume ga40_2012 `
  --pdf .\minutes\40th_pcaga_2012.pdf `
  --output .\tmp\footnote_scopes_ga40_derived.json
```
