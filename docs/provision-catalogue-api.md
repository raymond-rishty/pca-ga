# Provision Catalogue and API

The provision catalogue is a generated read model at `index/provision_catalogue.json`. The build joins current text from the PCA Constitution Reader with curated case, inquiry, CCB advice, RPR, overture, case-citation, and BCO-history data. Authority Markdown, provision pages, search records, and provision JSON are projections of this catalogue. Generators must not use a previously generated authority index as relationship input.

## Routes

- `/api/provisions/index.json` lists every supported provision API record.
- `/api/provisions/{book}/{reference}.json` returns one provision, using the canonical page route slug for the reference. Examples: `/api/provisions/bco/38-4.json` and `/api/provisions/wlc/q-62.json`.
- `/api/bco/index.json` lists unique BCO compatibility routes. `/api/bco/{slug}.json` is a byte-identical copy of the corresponding `/api/provisions/bco/{reference}.json` response.

The BCO API has schema version 2. Consumers of the previous artifact-manifest schema must update to the new provision object and inspect `schema_version` before reading it.

## Provision object

The top-level object includes:

- Stable provision `id`, book/reference fields, and canonical human and Reader URLs.
- `current_text.html` and plain `current_text.text` from the Reader source.
- `source.revision`, Reader file digests, and the catalogue input fingerprint.
- `relationships`, each with a stable relationship and record ID, record type, source metadata, `evidence_basis`, `relevance_status`, and an `occurrences` array.
- Qualified BCO `history`, `parent_id`/`children`, and explicit `coverage` notes.

Occurrence URLs retain available source anchors. The locator can include a Minutes page or case-text line and the indexed excerpt. `evidence_basis` says whether a link came from direct text, structured metadata, a provision tag, or a title/subject reference. `relevance_status` defaults to `unreviewed`; an indexed citation does not establish substantive interpretation. Recommendation and study coverage remains marked incomplete unless a curated source supplies a reliable record identity and locator.

The index includes empty-result provisions as well as provisions with relationships. A zero relationship count means the current catalogue found no indexed relationship for that provision; it is not evidence that no relevant record exists.
