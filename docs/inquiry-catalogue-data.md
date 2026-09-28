# Inquiry catalogue data

`index/inquiries.jsonl` is the canonical record set for constitutional inquiries and CCB advice. It contains one record per Digest or CCB entry, including stable `inquiry_id` and `page_slug` values. Records preserve the Digest title, section and citation alongside the synopsis, provisions, disposition, originating body, classification, and source-minute locators.

The `source_range` and optional `posed_range`, `substantive`, and `assembly_action` fields identify inclusive one-based line ranges in `markdown/<minutes_volume>.md`. `page_anchor` and `printed_page` retain the corresponding printed source locator. `legacy_locator` and `relocation` record source-line changes when `scripts/46_relocate_sources.py` applies a reviewed relocation.

Run `generateInquiryCatalogue` through Gradle to regenerate the inquiry pages, `index/INQUIRIES.md`, `index/CCB-OVERTURE-ADVICE.md`, and `index/inquiries_search.json`. Downstream catalogue, authority, search, and source-registry tasks consume those projections. The previous roster and locator JSON files have been consolidated into the JSONL records and are no longer build inputs.
