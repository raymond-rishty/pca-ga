# Extracted-document source PDFs

Source-PDF links for extracted pages are maintained as data, not inferred by the
templates.

## Durable data

- `index/source_registry.json` assigns stable `source_id` values to canonical
  minutes PDFs and dedicated case/study PDFs. Its case mappings use canonical
  judicial dockets and PDF assignments from
  `data/cases/records/judicial_cases.jsonl`; source links for extracted Minutes
  pages use their explicit volume and page locators. The SJC roster is an input
  to building the canonical case catalogue, but the registry does not read the
  roster directly.
- `index/dedicated_pdf_inventory.json` is the curated inventory of dedicated
  case PDFs in the canonical case records and study PDFs in the study manifest.
- `index/studies_pdf_manifest.json` remains the study manifest of record. The
  source registry projects its PDF entries into the common source model; it does
  not create a competing study catalogue.

The repository does not vendor the external PDF binaries. A source entry's
`pdf_path` is the stable path below `pcahistory.org`; `local_pdf_path` is
explicitly null. Study text audit artifacts, when present, are recorded
separately as `local_artifact_path`.

Minutes HTML links distinguish a printed folio from its physical PDF page.
`gaNN-pdf-pN` identifies PDF page N. `gaNN-pN` identifies printed folio N
when present; repeated folios use an occurrence-qualified printed ID such as
`ga33-p300-at-pdf590`. A missing printed folio has only its PDF-page ID. The
external PDF action always uses the physical PDF page coordinate.

## Source precedence

A record may have more than one source:

1. a dedicated PDF, when the registry knows one;
2. the relevant General Assembly minutes PDF, with a 1-based PDF page fragment.

Dedicated PDFs are listed before minutes fallbacks. A minutes page must use the
PDF page coordinate, not merely the printed page number. The resolver maps
printed anchors or source line ranges through the authoritative `PAGE` markers
in the minutes markdown. A bare legacy printed anchor resolves to the first
occurrence only for compatibility; new references to a repeated folio must
carry a source span or occurrence-qualified ID.

## Adding or correcting a source

1. Update the authoritative input index or manifest.
2. Run `python3 scripts/build_source_registry.py --write` to rebuild the registry and inventory with deterministic ordering.
3. Add or update the record mapping using a stable record identity.
4. Preserve the existing `source_id` when only a URL or note changes; IDs are
   used by generated pages and tests.
5. Run:

   ```text
   python3 scripts/build_source_registry.py . --check
   python3 tests/test_source_registry.py
   python3 tests/test_extracted_source_pdf_metadata.py
   ```

6. Regenerate the affected extracted pages, or run the build-time enrichment
   step for legacy committed pages.

Inventory status records the provenance decision carried by the canonical
record or study manifest. The inventory does not imply that a remote PDF has
been copied into this repository.
