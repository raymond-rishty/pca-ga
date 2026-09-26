# Authority index relationship policy

`index/provision_catalogue.json` is the joined read model. `index/authority_index.json`, the authority Markdown pages, search records, and provision API files are projections from that catalogue. A provision-to-record relationship identifies why the record is associated with the provision; each occurrence retains its own source, locator, excerpt, method, confidence, and Reader scope.

## Evidence and relationship kinds

| Record type | Included relationship | Evidence basis and locator | Reader scope |
|-------------|-----------------------|---------------------------|--------------|
| Judicial case | Every provision in `index/case_provision_index.json` | Preserve the audited index's evidence and source list. Direct text hits retain line and excerpt. Metadata-only hits remain labeled structured case metadata and have no invented excerpt. | Primary |
| Constitutional inquiry | Curated provision tags in `index/inquiries_search.json` | Structured provision tag; keep the summary as metadata, not as a source excerpt. | Primary |
| CCB advice | Curated CCB provision tags | Keep CCB advice as its own record type, separate from ordinary constitutional inquiries. Do not turn a synopsis into evidence. | Contextual |
| Overture | A provision named in the title or disposition is a proposal target. An explicit provision citation in body text is a separate citation occurrence. | Title/subject and disposition target sources remain distinguishable from direct body text. Body citations retain a page anchor and excerpt. | Adopted proposal targets are primary. Non-adopted targets and body mentions are candidates. |
| RPR exception | Structured exception tags and provision citations found in exception text | Exception-header hits are exception targets; other direct mentions are body mentions. Retain Markdown line and excerpt. | Contextual for exception targets; candidate for other mentions. |
| Study or recommendation | No comprehensive provision relationship is inferred from incomplete study coverage. | Keep the catalogue's coverage status incomplete until records have stable identities and source locators. | Not included in the Reader feed by inference. |

An overture is treated as adopted for Reader inclusion only when its curated disposition exactly identifies `Adopted`, `Adopted (final)`, an affirmative answer, or `Approved & ratified` (with an optional year). “Approved but not ratified,” “ratification not located,” “Answered by reference,” and other dispositions do not qualify. This is a display inclusion rule; it does not claim that every sentence in an adopted overture became constitutional text.

## Matching and display fields

- `relationship_kind` classifies the relationship, such as `explicit_citation`, `structured_case_reference`, `proposal_target`, `structured_exception_tag`, or `body_mention`.
- `evidence_basis` states whether support came from direct text, structured metadata, or a curated target tag.
- `match_method` records the parser or source index that produced the association.
- `match_confidence` measures confidence in the extraction or source tag. It is not a relevance score or an authority ranking.
- `locator` and `excerpt` belong to individual occurrences. A synopsis, title, or summary is metadata and must not be represented as a quotation from the source body.
- `reader_scope` is an evidence/display classification. The Constitution Reader includes every relationship for supported record types across `primary`, `contextual`, and `candidate` scopes, and displays the scope and evidence metadata with each record. It does not treat scope as a legal-authority ranking.
- `authority_weight` is a legacy display field. It does not state the legal force of the record. Model-generated `relevance_assessment` fields remain advisory and are not human confirmation.

Preliminary Principles are recognized only by explicit “Preliminary Principle(s)” wording or uppercase `PP` citation syntax. Lowercase `pp. 174` page references are not provision citations. The Constitution Reader consumes supported record types from all scopes in the generated authority index; it must not independently scan record bodies or reinterpret provision references.

## Audit output

`scripts/47_authority_index_audit.py` generates `index/authority_index_audit.json` and `index/AUTHORITY-INDEX-AUDIT.md`. The report counts relationships and occurrences by type, relationship kind, evidence basis, match method, confidence, and Reader scope; lists unmatched relationships and advisory model classifications; reports incomplete study coverage; and checks the Acree example against the canonical case provision index.
