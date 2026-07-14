# Study PDF ingestion handoff

These are **future-work instructions only**. Do not perform the ingestion steps simply because this
file exists; use them when a later task explicitly asks to replace/rebuild the study-paper corpus from
PCA Historical Center PDFs and mapped minutes ranges.

This file is intended as a handoff to a future session. The repository now has the first
manifest-driven piece in `index/studies_pdf_manifest.json`. Future sessions should extend that
workflow as a **bulk replacement project**, not as a one-PDF-at-a-time link cleanup: the existing
`studies/*.md` report pages should be treated as provisional/dubious until they have been rebuilt
from PCA Historical Center PDF text and/or confidently mapped GA-minutes ranges. The long-term
workflow is: convert the study PDFs once, fuzzily match them back to the GA minutes, then
regenerate the Markdown pages from the manifest and current minutes whenever those minutes are
corrected.

## Scope: not one PDF at a time

No — this should not be limited to one PDF at a time. A future implementation can still commit in
reviewable chunks, but the data model and generator should assume a corpus-wide replacement:

- every study-paper record gets a manifest row;
- every existing `studies/*.md` page is eligible to be regenerated;
- existing generated study pages are treated as candidates to replace, not as trusted source text; and
- chunking should be operational (for review size), not architectural.

## Target workflow

The desired workflow has four phases. Run these in batches over the full study-paper roster where
possible; do not design the process around manually finishing one PDF before discovering the next
one.

1. **Convert the study-paper PDFs to text in bulk.**
   - Build a worklist from the PCA Historical Center study roster, `index/studies_roster.json`,
     `index/studies_pcahistory.json`, and the existing `studies/*.md` pages.
   - Include papers that already have `studies/*.md` pages; those pages are not authoritative proof
     that the content is correct. This project is meant to replace the dubious generated study-report
     Markdown with PDF/minutes-backed reconstructions.
   - Extract each PDF into an auditable intermediate artifact, preserving page breaks if possible.
   - Record the PDF URL, local extraction artifact, extraction tool/version, extraction date, and any
     OCR warnings.

2. **Find the corresponding text in the minutes.**
   - Search the local `markdown/ga*.md` corpus for each converted PDF.
   - This step must be **fuzzy**, not exact: the source minutes are OCR-derived, so expect hyphenation
     drift, broken words, ligature issues, punctuation differences, page-header noise, and occasional
     missing or duplicated lines.
   - Use several normalized fingerprints from the PDF text: title phrases, opening paragraphs,
     distinctive body phrases, recommendation headings, ending paragraphs, and citation headers.
   - Prefer a confident GA-minutes range over embedding a standalone PDF transcript. The generated
     `studies/*__pcahistory.md` pages should be rebuildable from `markdown/ga*.md` whenever possible.

3. **Write a manifest of page/range mappings.**
   - Store the mapping data in `index/studies_pdf_manifest.json`.
   - The manifest should be the source of truth for PDF-to-minutes mappings; generated records such as
     `index/studies_located.json`, `index/studies_pages.json`, and `studies/*__pcahistory.md` should be
     rebuildable from it.
   - Include confidence/provenance fields so fuzzy matches are auditable and can be revisited.

4. **Rebuild the study-paper Markdown from the manifest and minutes.**
   - Add or update a generator so it reads the manifest, slices the mapped ranges from `markdown/ga*.md`,
     and emits the full-text sections in `studies/*__pcahistory.md`.
   - The rebuild must be deterministic: if formatting fixes are later made to the original minutes, rerun
     the generator and the study-paper pages should pick up those improved minutes slices.

## Proposed manifest shape

Use one manifest record per PCA Historical Center PDF/document. A document may map to one or more
source ranges if the PDF is a compilation.

```json
{
  "schema_version": 1,
  "generated_from": "manual/fuzzy PDF-to-minutes matching",
  "documents": [
    {
      "topic": "Example topic",
      "title": "Example PCA Historical Center PDF title",
      "pcahistory_file": "2-000.pdf",
      "pcahistory_url": "https://www.pcahistory.org/pca/digest/studies/2-000.pdf",
      "study_page": "studies/example-topic__pcahistory.md",
      "pdf_text_artifact": "index/studies_pdf_text/2-000.txt",
      "status": "mapped",
      "match_confidence": "high",
      "match_notes": "Opening paragraph, title, and closing recommendation all matched after OCR normalization.",
      "ranges": [
        {
          "vol": "gaNN_YYYY",
          "line_start": 1234,
          "line_end": 1300,
          "label": "Nth GA (YYYY), citation or appendix label",
          "anchor_hint": "gaNN-p123",
          "pdf_pages": "1-4",
          "printed_pages": "123-126",
          "match_method": "fuzzy fingerprint",
          "fingerprints": [
            "normalized opening phrase",
            "distinctive body phrase",
            "closing recommendation phrase"
          ]
        }
      ]
    }
  ]
}
```

Recommended `status` values:

- `mapped` — matched to local minutes ranges and safe to rebuild from `markdown/ga*.md`.
- `partial` — some but not all PDF text was matched to local minutes ranges.
- `pdf_only` — no reliable minutes location yet; keep extracted PDF text as an auditable fallback.
- `unresolved` — PDF exists, but text extraction or matching still needs work.

Recommended `match_confidence` values:

- `high` — multiple independent fingerprints match, start/end ranges are clear, and page/citation data agrees.
- `medium` — enough evidence to render, but range edges or page/citation data need review.
- `low` — do not render as authoritative minutes text without human review.

## Fuzzy matching guidance

When matching PDF text to OCR minutes text:

- Normalize case, whitespace, punctuation, curly quotes, OCR ligatures, and end-of-line hyphenation.
- Compare word shingles rather than relying on exact substrings.
- Ignore page headers, page footers, line numbers, printed-page comments, and Markdown anchors.
- Use multiple short fingerprints rather than one long quote; OCR often damages isolated words.
- Verify both the **start** and **end** of the proposed range.
- Preserve the original line ranges even if the OCR text is imperfect; later minutes cleanup should improve
  the generated study page automatically.
- Mark low-confidence or partial matches honestly in the manifest instead of silently treating them as complete.

## Generator requirements

The generator path should continue to:

1. Read `index/studies_pdf_manifest.json`.
2. Validate that every `mapped` range has an existing `markdown/<vol>.md` file and valid line numbers.
3. Slice minutes text directly from the current `markdown/ga*.md` files.
4. Render `## Full text` sections into the appropriate `studies/*__pcahistory.md` pages.
5. Preserve the original PCA Historical Center PDF link for comparison.
6. Emit source links using the mapped volume, line range, page/anchor hints, and confidence notes.
7. Fail loudly on missing files, invalid ranges, or `mapped` records whose source slice is empty.

The current `full_text_sources` pattern in `index/studies_pcahistory.json` is an interim version of this
idea. The future manifest should supersede hand-maintained inline range metadata while keeping the same
rebuild behavior.

## Validation checklist for the future session

After updating the manifest or generator, run at least:

```bash
python -m json.tool index/studies_pdf_manifest.json >/dev/null
python -m json.tool index/studies_pcahistory.json >/dev/null
python -m json.tool index/studies_located.json >/dev/null
python -m json.tool index/studies_pages.json >/dev/null
python -m py_compile scripts/36_study_extract.py scripts/37_study_pages.py
python scripts/36_study_extract.py .
python scripts/37_study_pages.py .
python scripts/39_study_reconcile.py .
python scripts/38_study_index.py .
git diff --check
```

Also manually inspect each newly rebuilt `studies/*__pcahistory.md` page to confirm that:

- the original PCA Historical Center PDF link remains available;
- the `## Full text` section is present when a mapped range exists;
- line-range/source links are accurate;
- low-confidence or partial matches are labeled as such; and
- no standalone PDF transcript is presented as minutes-derived text unless the manifest says it is `pdf_only`.
