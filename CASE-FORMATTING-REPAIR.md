# Case formatting repair

This workflow restores visual semantics that OCR text alone cannot carry. It
uses PP-OCR word boxes for alignment, 300-DPI source-PDF pixels for horizontal
marks, and PP-Layout indentation for blockquote candidates. It never replaces
recognized words.

## Safety model

Planning is read-only and produces a JSON report plus page overlays. Every
candidate starts with `"decision": "pending"`. A human inspects the overlay and
changes only correct candidates to `"approved"`. Applying a reviewed report
verifies both the minute-file SHA-256 and the exact source substring before it
inserts markup.

The canonical markup is:

- `<u>text</u>` for a single underline
- `<del>text</del>` for a single strikethrough
- `<u class="double-underline">text</u>` for a double underline
- `<del class="double-strikethrough">text</del>` for a double strikethrough
- Markdown `>` prefixes for reviewed blockquotes

## Runtime

Use the existing OpenCV/PyMuPDF environment. No VLM or GPU is required:

```powershell
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\plan_case_formatting_repairs.py --pages ga42:527-528,ga52:23
```

Omit `--pages` to process the 2,888 unique pages referenced by case files on
`main`:

```powershell
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\plan_case_formatting_repairs.py --ref main
```

The report is written to `build/case-formatting-repair/report.json`; compact
JPEG overlays are written only for pages with review candidates. Inspect an overlay, edit the
corresponding report candidate to `"decision": "approved"`, then apply:

```powershell
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\plan_case_formatting_repairs.py --apply-approved build\case-formatting-repair\report.json
```

The checked visual fixtures for GA 42 pages 527-528 and GA 52 page 23 provide a
repeatable detector regression test:

```powershell
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\evaluate_case_formatting_repairs.py build\case-formatting-repair\report.json
```

Create a non-writing review bundle with page overlays, candidate IDs, proposed
minute copies, and unified diffs:

```powershell
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\build_case_formatting_review.py build\case-formatting-repair\bakeoff-compact-report.json --output build\case-formatting-review
```

The bundle's `approval-report.json` remains entirely pending. Approve candidates
by ID (or by reviewed page) before using it with `--apply-approved`.

## Propagate repaired minutes to cases

First run the existing page-aware re-extractor without `--apply` and inspect
`build/formatted_case_reextract.json`:

```powershell
ocr-bakeoff\.venv\Scripts\python.exe scripts\55_reextract_cases_from_formatted_minutes.py --ref main --ga-from 3 --ga-to 52
```

After review, rerun with `--apply`, then audit for structural regressions:

```powershell
ocr-bakeoff\.venv\Scripts\python.exe scripts\55_reextract_cases_from_formatted_minutes.py --ref main --ga-from 3 --ga-to 52 --apply
ocr-bakeoff\.venv\Scripts\python.exe scripts\67_audit_case_regressions.py
```

## Confidence boundaries

Horizontal marks have the strongest signal because the rule must cross an OCR
word box at the expected vertical position and align with the marked token
span. Parallel rules become double-line styles. Blockquotes are less certain:
PP-Layout indentation proposes them, but lists and ordinary hanging indents can
look similar, so they always require visual review.

Bold and italic are not inferred by this script. The tested PDFs do not expose
native font-decoration flags, and pixel-weight/slant heuristics are not yet
precise enough for corpus-wide writing. Existing heading/list formatting from
PP-Layout remains intact, while bold/italic should be added as separately
reviewed fixtures or with corroborating parser evidence.

## Calibrated corpus-wide automation

The corpus contains 32,377 PDF pages. Corpus automation uses an abstaining
`conservative-v2` policy rather than treating the detector's heuristic score as
a probability. Inline marks must survive three threshold/kernel variants with
the same feature and token span, align through unique full-line context, exceed
strict overlap/density thresholds, and not overlap another inline candidate.
Automatic writing is currently limited to single underlines. A line with multiple
word-sized underline detections abstains because applying only the strongest
fragments would misrepresent a longer underlined phrase. Double underlines and
strikethroughs also
remain review-only: ordinary lowercase letter strokes produced stable false
positive strikethroughs in the first calibration round, while the fresh holdout
does not contain unseen double-underlines. Directly reviewed examples can still
be approved as a bounded batch. Blockquotes remain detection-and-review
only in `conservative-v2`. A stratified
case-page sample showed that indentation plus a colon-ended lead-in can still
confuse ordinary recommendations lists with quotations, so the policy abstains
until an independent corroborating signal is available.

Generate a report without thousands of unnecessary review images:

```powershell
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\plan_case_formatting_repairs.py --scope all-pages --auto-policy conservative-v2 --overlay-mode none --output build\case-formatting-calibration\all-pages-auto-report.json
```

Select a deterministic stratified calibration sample. The current policy
requires 300 inline labels spread across at least 20 assemblies. With zero
errors, the one-sided 95% Wilson lower precision bound must be at least 0.99.
Any sample used to change the policy is treated as tuning evidence and excluded
from the fresh holdout used for certification.

```powershell
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\sample_formatting_calibration.py build\case-formatting-calibration\all-pages-auto-report.json --exclude-sample build\case-formatting-calibration\case-pages-sample.json --seed pca-ga-formatting-calibration-v2-holdout --output build\case-formatting-calibration\sample.json
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\plan_case_formatting_repairs.py --pages-file build\case-formatting-calibration\sample.json --auto-policy conservative-v2 --output build\case-formatting-calibration\sample-overlays.json
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\build_formatting_calibration_review.py build\case-formatting-calibration\sample.json build\case-formatting-calibration\sample-overlays.json
```

After labeling `correct` or `incorrect` in the sample JSON—or recording concise
default-plus-exceptions feedback—evaluate it. A
formatting family can be approved independently, so inline marks may proceed
while blockquotes continue to abstain.

```powershell
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\evaluate_formatting_calibration.py build\case-formatting-calibration\sample.json --feedback build\case-formatting-calibration\feedback.json --output build\case-formatting-calibration\summary.json
ocr-bakeoff\.venv\Scripts\python.exe ocr-bakeoff\scripts\make_auto_approval_report.py build\case-formatting-calibration\all-pages-auto-report.json build\case-formatting-calibration\summary.json --output build\case-formatting-repair\auto-approved-report.json
```

The approval command verifies the exact report hash, detector configuration,
policy name, and passing families. The apply command then re-verifies every
minute-file hash, detector configuration hash, and exact source substring before
inserting any markup.

Human-reviewed candidates remain a separate bounded path. Concise feedback can
be materialized against a fresh detector report; it approves only the candidate
IDs actually present in the reviewed sample and does not confer corpus-level
approval on their feature class.

### Calibration rounds

The first 300-candidate review accepted 287 candidates, rejected four false
strikethroughs, and identified nine correct-but-incomplete underline fragments.
That 95.7% acceptable-edit rate failed the automatic gate and was used only to
tune `conservative-v2`. The revised case-page report has 709 auto-eligible
single underlines. It excludes all first-round IDs from a fresh 300-candidate,
28-assembly holdout. The holdout passed 300/300 with no errors and a one-sided
95% Wilson precision lower bound of 0.991062. The resulting hash-bound approval
report contains exactly 709 single-underlines pending application.

Recall is measured separately from candidate acceptance. A deterministic,
stratified page audit compares unannotated page images with detector overlays and
counts every complete visible single-underline, including marks for which the
detector emitted no candidate. Marginal threshold bands are reviewed separately
so a lower-confidence expansion cannot weaken the already-certified tier.

Frontier A is the complete 98-candidate single-underline band from confidence
0.915 through 0.920 that passed the original policy gates. Its marks were
reviewed 98/98 as visually correct, but three GA20 heading candidates were
withheld because applying only the detected word would misrepresent a longer
underlined span. The bounded applied addition is therefore 95 candidates, for
804 total case-page repairs. Fragment detection now runs independently of the
confidence gate, and the user-rejected or incomplete IDs are explicitly blocked
at both report generation and application. This does not lower the policy
threshold for unseen pages outside the reviewed case-page population.

### Provisional adjacency scoring

`conservative-v3-adjacency` is an uncertified recall experiment kept in
`ocr-bakeoff/config/case_formatting_repair_v3_adjacency.json`; the default v2
configuration remains separate and reproducible. V3 adds at most 0.05 total
confidence from two auditable forms of corroboration:

- contiguous same-line underline components are assembled into one complete
  source span; bounded gaps may be filled only for short words or all-caps
  heading lines, and every filled word is recorded in `score_adjustments`;
- an underline ending at the final OCR word of one line supports an underline
  beginning at the first OCR word of the next line when vertical spacing and
  left-edge geometry are consistent with a wrapped paragraph.

Adjacency never overrides source alignment, component density, or stability
requirements. When a new span overlaps existing single-underline markup, the
application operation takes their union, removes the interior underline tags,
and emits one canonical `<u>...</u>` block rather than nesting or rejecting it.
On the already-formatted case-page corpus, v3 found 719
adjacency-supported underline candidates and 126 previously unapplied
candidates that pass every provisional gate. Of those, 118 crossed the 0.92
threshold because of adjacency. The complete 126-candidate, 71-page review is
`build/case-formatting-adjacency/REVIEW-adjacency-v3.md`. All 126 candidates
were independently reviewed and approved, then applied to the source minutes.
That pass added 125 new underline blocks and expanded one existing block by
canonical union, bringing the case-page total to 929. The apply-time and
post-apply checks found balanced, non-nested markup, preserved all 32,377 page
markers, and confirmed that removing inline tags reproduces the original source
text exactly. Downstream case regeneration was left in dry-run mode.
