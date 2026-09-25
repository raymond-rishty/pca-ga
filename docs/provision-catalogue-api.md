# Provision Catalogue and API

The build joins current text from the PCA Constitution Reader with curated case, inquiry, CCB advice, RPR, overture, case-citation, and BCO-history data. `index/provision_catalogue.json` is the authoritative generated read model. Provision pages, search records, authority Markdown, and provision JSON are generated from it. The internal catalogue and assessment input are excluded from the deployed site.

## Routes

- `/api/provisions/index.json` lists every supported provision API record.
- `/api/provisions/{book}/{reference}.json` returns one provision, using the canonical page route slug for the reference. Examples: `/api/provisions/bco/38-4.json` and `/api/provisions/wlc/q-62.json`.
- `/api/bco/index.json` lists unique BCO compatibility routes. `/api/bco/{slug}.json` is a byte-identical copy of the corresponding `/api/provisions/bco/{reference}.json` response.

The provision API uses schema version 3. Consumers should inspect `schema_version` before reading the response.

## Provision object

The top-level object includes:

- Stable provision `id`, book/reference fields, and canonical human and Reader URLs.
- `current_text.html` and plain `current_text.text` from the Reader source.
- Reader revision and file digests, the catalogue input fingerprint, and an assessment fingerprint.
- `relationships`, each with stable relationship and record IDs, record type, source metadata, `evidence_basis`, editorial `relevance_status`, a reader-facing `reference_presentation`, and an `occurrences` array.
- Qualified BCO `history`, `parent_id`/`children`, and explicit `coverage` notes.

Each `reference_presentation` has a `group` and an optional `label`. Groups are `discusses`, `cites`, `other_case_discussion`, `other_mentions`, and `review`. These are the same groups used by the provision pages. Unclear, incomplete, mismatched, not-yet-reviewed, and insufficiently supported references stay in `review`; they are not deleted. `relevance_status` remains `unreviewed` until an editorial review changes it.

The public API omits model identifiers, assessment scores, score distributions, and detailed internal role labels. The repository keeps assessment lineage for audit, while readers can inspect the source excerpt, source link, and locator. These groupings guide navigation and do not establish legal correctness. Recommendation and study coverage remains marked incomplete unless a curated source supplies a reliable record identity and locator.

The index includes empty-result provisions as well as provisions with relationships. A zero relationship count means the current catalogue found no indexed relationship for that provision; it is not evidence that no relevant record exists.
