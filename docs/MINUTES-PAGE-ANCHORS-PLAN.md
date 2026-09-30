# Resolve printed-page and PDF-page anchor ambiguity

Status: implemented locally and validated. The full Gradle `siteBuild` passes,
and a fresh local browser load of `#ga51-p808` lands on printed page 808 (PDF
page 815), while `#ga51-p801` and `#ga51-pdf-p808` land on printed page 801
(PDF page 808). A warm incremental preview also passed after marker cleanup was
made idempotent. The broad locator/link audit and public-site verification
after release remain follow-up work.

Tracking issue: [#214](https://github.com/raymond-rishty/pca-ga/issues/214).

## Problem and reproduction

The [Evans case, 2023-07](https://raymond-rishty.github.io/pca-ga/cases/ga51_2024__2023-07.html)
cites printed pages 808–824. Its [Minutes link](https://raymond-rishty.github.io/pca-ga/markdown/ga51_2024.html#ga51-p808)
lands at printed page 801. Clicking the printed page 808 marker also returns to 801.

Published HTML inspected on September 30, 2026 contains an old empty
`ga51-p808` anchor immediately before `PAGE ga=51 pdf_page=808 printed_page=801`,
and a newer marker with the same ID at `pdf_page=815 printed_page=808`.
The browser selects the first matching ID. Even correctly numbered legacy
anchors can duplicate the newer marker's ID at the same location.

This needs a corpus-wide correction, not a seven-page adjustment to GA51.
Printed folios can also repeat: GA33 printed page 300 occurs at PDF pages
302 and 590, as documented in `tests/minutes-page-source-pdf.test.js`.
Related issue: [#211](https://github.com/raymond-rishty/pca-ga/issues/211)
addressed deep-link startup delays and build-time page markup; this issue
concerns destination identity and duplicate IDs.

## Anchor contract

- Identify a physical page by `(volume, pdf_page)`, with a 1-based PDF coordinate.
  Store the printed folio and its provenance separately. Use authoritative
  `PAGE` metadata and approved pagination runs, never a global offset.
- Give every physical page a stable `ga51-pdf-p815` anchor. Open the external
  source PDF with `#page=815`.
- Reserve `ga51-p808` for printed page 808. Retain this short form when the
  folio is unique in the volume. Human citations remain printed-page citations.
- For repeated folios, use an occurrence-qualified printed anchor, such as
  `ga33-p300-at-pdf590`, or the explicit PDF anchor. Keep the unqualified
  legacy alias on the first occurrence to preserve the existing documented
  fallback, but require new links with known source coordinates to select the
  intended occurrence. A bare repeated citation without context is ambiguous;
  do not silently resolve new citations to the first occurrence.
- For missing printed pagination, publish only the explicit PDF locator and
  label it `PDF p. N`. Preserve nonnumeric folios without converting them to
  Arabic numbers or creating colliding identifiers.
- Give each ID one owner. Put the canonical PDF ID and printed aliases on
  stationary targets beside the PAGE boundary, before the sticky marker. Keep
  IDs off the sticky marker; its visible label links to the appropriate target.
- Existing `gaNN-pN` fragments cannot retain both PDF and printed meanings.
  Standardize them as printed locators and migrate repository-owned links
  that previously meant PDF coordinates. Do not add conflicting PDF aliases.

## Implementation sequence

### 1. Audit locators and capture failing examples

- [ ] Inventory all 52 Minutes volumes: physical pages, detected folios,
  repeated/missing/nonnumeric folios, legacy anchors, mismatches, and duplicate IDs.
- [ ] Inventory links in cases, inquiries, overtures, RPR, studies, catalogues,
  provision pages, API manifests, and search outputs. Classify their intended
  coordinate from source metadata, page boundaries, and text context.
- [ ] Record unresolved references for review. Keep existing user edits and
  curated pagination evidence intact; do not guess from the numeric fragment.
- [x] Add the GA51 PDF-808/printed-801 and PDF-815/printed-808 collision as a
  regression fixture, plus GA33's repeated printed page 300.

### 2. Centralize page identity and anchor generation

- [x] Add a shared page-locator resolver that returns PDF coordinate, printed
  folio/provenance, canonical anchor, printed aliases, and ambiguity status.
- [x] Support explicit PDF, unique printed, and qualified printed locators;
  validate existence and preserve volume identity. Normalize GA-number padding
  consistently without creating duplicate rendered aliases.
- [x] Replace ad hoc fragment-number inference and first-match lookups where
  source coordinates are available. Compatibility fallbacks must be explicit.
- [x] Document the contract and update `docs/source-pdf-links.md`.

### 3. Correct source anchors and rendered targets together

- [ ] Update active Markdown generators and pagination normalization so future
  regeneration cannot restore PDF-numbered `-pN` anchors. Audit legacy scripts
  such as `41_source_pagelinks.py` before changing their callers.
- [ ] Repair existing page-boundary anchors from their associated `PAGE`
  records through a deterministic Gradle-managed migration. Preserve source
  text, page boundaries, footnote identifiers, record IDs, and curated folios.
- [x] Update `scripts/46_minutes_page_markup.py` to consume the shared mapping,
  remove obsolete empty page anchors, and produce unique stationary targets.
  Do not remove unrelated editorial anchors or footnote targets.
- [ ] Retain marker metadata and page-action behavior. Add suitable scroll
  clearance for the top navigation and sticky record context.
- [x] Make fresh builds, repeated transforms, and incremental previews converge
  on the same markup; invalidate cached pre-migration output appropriately.

### 4. Migrate all link and index consumers

- [x] Update `scripts/source_links.py`, extracted source-PDF metadata enrichment,
  `scripts/44_link_constitution_refs.py`, source relocation, and active record
  generators to use the shared resolver. Current regexes and anchor-first
  lookups need explicit support for the new PDF/qualified forms.
- [ ] Resolve repeated folios using the record's PDF coordinate or source span.
  Preserve the intended passage when migrating a link; changing the fragment
  spelling alone is insufficient.
- [x] Update `assets/minutes-pages.json` generation to retain all occurrences,
  with a physical-page lookup and explicit printed-folio multiplicity. Update
  every reader and version the schema if its public structure changes.
- [x] Regenerate affected catalogues, provision/citation indexes, API and app
  search manifests, and Pagefind through the Gradle graph. Inspect every
  generated diff; avoid unrelated content or taxonomy changes.
- [ ] Ensure source-PDF actions still use the selected physical page and
  dedicated PDFs retain their existing precedence.
- [x] Fix render ordering in `scripts/render_site.py`: the citation linker
  currently runs before page markup. It must see the same canonical mapping
  as final HTML in both full and preview builds. Track new inputs/dependencies
  and cache versions in Gradle and incremental rendering.

### 5. Enforce the contract and test navigation

- [x] Extend `scripts/validate_site_build.py` to reject duplicate page IDs,
  metadata/anchor mismatches, nonexistent local page fragments, and generated
  locators that silently select an ambiguous folio. Report volume and coordinate.
- [x] Test the GA51 collision, repeated folios, both anchor meanings, stale
  anchors, source-index occurrences, and transform idempotency. Include
  negative checks for the original collision.
- [x] Update relevant source-link tests. Integrate new checks
  into the Gradle validation chain.
- [ ] Add browser checks for a fresh fragment load, page-marker self-link,
  cross-page case link, back/forward navigation, and source-PDF page action.
  Fresh local desktop loads for the cross-page case link and both page targets
  passed; still check back/forward navigation, the PDF action, mobile layout,
  sticky-header clearance, and navigation with JavaScript disabled.

### 6. Build, review, and release

- [x] Run the full validating build:
  `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build-local.ps1`.
  Use Gradle for data/site generation, not individual generator invocations.
  During development, `-Incremental -RefreshSearch` is available for previews;
  it does not replace final validation. Use `-RegenerateOvertures` only if
  curated overture-source artifacts changed. Completed with Temurin JDK 17;
  Gradle reported `BUILD SUCCESSFUL` after all regression tasks and rendered
  site validation passed.
- [x] Review generated changes and inspect the GA51 local preview at
  `http://127.0.0.1:8000/pca-ga/`. The inquiry/index changes update fragments
  while retaining source PDF coordinates; the generated corpus passed the
  site-wide uniqueness and metadata checks.
- [x] Verify the GA51 collision and GA33 repeated folios in regression tests;
  inspect a fresh local load of `#ga51-p808` in the browser.
- [x] Check a warm incremental preview for stable markup. It passed after
  fixing nested markers that previously survived the cleanup pass.
- [ ] Check an early inferred-folio volume and a page without a printed folio.
- [ ] After review and deployment, repeat public-site navigation checks.
  Document the interpretation of old fragments and any remaining ambiguous
  references. The local preview used for this validation has been stopped.

## Acceptance criteria

1. Locally verified: the Evans source link and printed-page-808 self-link land
   at the case's start, with `printed_page=808` and `pdf_page=815`.
2. `#ga51-pdf-p815` reaches that same page; `#ga51-pdf-p808` reaches printed
   page 801. Its PDF action opens `51st_pcaga_2024.pdf#page=808`.
3. Every physical page has one unique PDF target. Printed targets and aliases
   are unique within each HTML document, and no PDF coordinate masquerades
   as a printed folio.
4. Both occurrences of GA33 printed page 300 are individually addressable;
   context-backed links and PDF actions select the intended occurrence.
5. Citation indexes, record source links, API/search assets, and rendered HTML
   agree on the same physical page. Missing/ambiguous folios are explicit.
6. The full `siteBuild` passes with regression validation. A warm incremental
   preview also passes; deployed public-site checks remain pending release.

The plan is complete when recorded in the issue. Implementation is complete
only after these acceptance criteria pass and the deployed regression is checked.
