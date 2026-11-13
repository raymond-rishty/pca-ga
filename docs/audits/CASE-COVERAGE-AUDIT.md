# Judicial case coverage audit

This report compares the Minutes-derived case corpus, the canonical catalogue, and the case-page map.
The Historical Center roster is not used to define coverage because it can omit cases or list wrong docket numbers.

A page is treated as represented when a canonical record points to it or a companion docket on the same mapped page has a canonical record. Only explicit docket identities from the Minutes-derived corpus and case-page map count as coverage evidence; a number missing between two others is not presumed to be an assigned docket. A shared-page docket alias counts as represented.

- Canonical records: 548
- Mapped case pages without a canonical record: 0

## Case pages without canonical records

| Docket ID(s) | Page | Caption | Extracted disposition(s) |
|---|---|---|---|

## Reviewed docket-number findings

These reviewed findings are retained as source input in `data/cases/overrides/case_coverage_reviews.json`; this section is generated from that file, not entered only in this report.

| Docket ID | Status | Reviewed | Finding | Evidence |
|---|---|---|---|---|
| `2021-04` | `not_found_as_sjc_docket` | 2026-11-07 | No SJC case heading or SJC-case citation for 2021-04 was found. The number sequence alone does not establish that an SJC docket was assigned. | markdown/ga51_2024.md:11124 — 2021-4 is a transfer-record exception.<br>markdown/ga51_2024.md:11403 — 2021-4 is a transfer-exam exception.<br>markdown/ga52_2025.md:11268,12057 — 2021-04/2021-4 occurs in RPR and transfer-exam references, not an SJC case heading or citation. |

## Checkpoint

`2021-09` is present in `judicial_cases.jsonl`: yes.
