---
name: pca-ga-case-ingestion
description: Ingest or repair PCA General Assembly judicial cases in this repository, including later decisions for previously pending dockets, canonical case pages, corpus metadata, case links, dispositions, topics, BCO provisions, and every derived case/provision/search manifest. Use when adding a case, replacing a docket-only or pending record with its eventual decision, correcting judicial-case metadata, or auditing incomplete case ingestion.
---

# PCA GA Case Ingestion

Treat a case as ingested only when its authoritative decision is present in the
case page, represented in the structured corpus, and discoverable through every
derived index.

## Establish the authoritative record

1. Search later General Assembly minutes when the first docket mention says the
   matter is pending, deferred, carried forward, or otherwise undecided.
2. Keep the historical status-only page when it documents an earlier Assembly,
   but label it as pending and link it directly to the later decision page.
3. Make the canonical case target the decision, never the status-only page.
4. Extract only text belonging to the docket. Check both ends against adjacent
   headings so the previous or next case is not included.
5. Preserve the decision's statement of facts, issues, judgment, reasoning,
   vote, and separate opinions. Cite the exact minutes volume and page span.

## Complete the case artifacts

For every docket, update all of these:

- `cases/*.md`: accurate caption, court, deciding Assembly, disposition,
  dissent status, source pages, and complete decision text.
- `index/case_pages_map.json`: every normalized docket alias maps to the
  decision page; consolidated decisions may map several dockets to one page.
- `index/case_pages_overrides.json`: durable corrections when reconciliation
  would otherwise restore a stale combined or pending-page target.
- `index/case_metadata_overrides.json`: durable audited corrections and any
  records the automated segmenter missed.
- `index/cases.jsonl`: title, parties, body, Assembly/year, source page range,
  disposition, vote, dissent flag, BCO citations, topics, synopsis,
  description, precedent relationships, and provenance where available.

Use the repository's disposition vocabulary:
`sustained`, `partially_sustained`, `not_sustained`, `denied`, `dismissed`,
`out_of_order`, `in_order`, `administrative`, `referred`, `granted`,
`abandoned`, or `other`. Put finer detail in the synopsis.

Record only provisions actually belonging to the case. Normalize bare BCO
references, preserve non-BCO constitutional references in topics or prose, and
check separate opinions because they frequently cite additional provisions.

## Regenerate in dependency order

Run with UTF-8 enabled:

1. `python scripts/07_build_cases.py`
2. `python scripts/27_case_index_reconcile.py`
3. `python scripts/08_index_cases.py build`
4. `python scripts/20_markdown_index.py`
5. `python scripts/44_case_provision_index.py .`
6. `python scripts/43_authority_index.py .`
7. `python scripts/35_search_index.py .`
8. `python scripts/45_bco_manifests.py . --out api/bco`
9. `python scripts/34_llm_pack.py .`

## Verify the ingestion

Do not consider the work complete until all checks pass:

- Every docket appears exactly once as a canonical structured record.
- `index/CASES.md` links each docket to the decision and shows its real
  disposition and synopsis, including dockets such as `2000-02`.
- No decision page contains text or BCO citations from an adjacent case.
- `index/CASES-BY-PROVISION.md` and
  `index/case_provision_index.json` contain every directly cited provision.
- `index/authority_index.json`, `app/search_index.json`, search chunks,
  `api/bco/*`, and `llms-full.txt` expose the corrected decision URL and
  metadata.
- Cross-references in rendered output prefer the later decision over an
  earlier pending page.
- `python scripts/27_case_index_reconcile.py` reports no regression.
- The diff contains no unrelated generated or user-owned changes.

When auditing for similar omissions, flag small case pages, null or placeholder
dispositions, missing synopses/topics/parties, dockets in prose but absent from
`cases.jsonl`, and case-index entries without links. Confirm each candidate
against later minutes before changing it.
