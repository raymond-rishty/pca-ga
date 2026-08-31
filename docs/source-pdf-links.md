# Extracted-document source PDFs

Source-PDF links for extracted pages are maintained as data, not inferred by the
templates.

## Durable data

- `index/source_registry.json` assigns stable `source_id` values to canonical
  minutes PDFs and dedicated case/study PDFs. Its `record_sources` map associates
  those IDs with extracted records.
- `index/dedicated_pdf_inventory.json` is the curated inventory of dedicated
  PDFs currently known from the SJC roster and study manifest.
- `index/studies_pdf_manifest.json` remains the study manifest of record. The
  source registry projects its PDF entries into the common source model; it does
  not create a competing study catalogue.

The repository does not vendor the external PDF binaries. A source entry's
`pdf_path` is the stable path below `pcahistory.org`; `local_pdf_path` is
explicitly null. Study text audit artifacts, when present, are recorded
separately as `local_artifact_path`.

## Source precedence

A record may have more than one source:

1. a dedicated PDF, when the registry knows one;
2. the relevant General Assembly minutes PDF, with a 1-based PDF page fragment.

Dedicated PDFs are listed before minutes fallbacks. A minutes page must use the
PDF page coordinate, not merely the printed page number. The resolver maps
printed anchors or source line ranges through the authoritative `PAGE` markers
in the minutes markdown.

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

Inventory status is evidence-aware: `listed` means the dedicated PDF is
listed in the repository's SJC source roster, while `mapped` and
`pdf_only` come from the study manifest's provenance decisions. The inventory
does not imply that a remote PDF has been copied into this repository.
