# Judicial-case taxonomy

This is the controlled vocabulary for the canonical judicial-case layer. The
authoritative checklist is `index/sjc_official/roster.jsonl`; the Minutes remain
the source for verbatim case text, and `index/cases.jsonl` supplies extracted
metadata when it has been reconciled to the roster.

## Identity

`index/judicial_cases.jsonl` contains one record per unique rostered case. The
current saved roster has 480 entries but repeats six canonical IDs; the
generator collapses those repeats to 473 numbered cases plus one explicit
unknown-number audit row.

- `case_id` is the stable, human-facing canonical ID: `YYYY-NN` (for example,
  `2023-07` or `1985-06`). A letter suffix is retained for split matters,
  such as `1992-09a`.
- `legacy_case_id` is the repository's existing unpadded key, such as
  `2023-7`. It is retained for joins to existing case pages and citation edges.
- `era_id` is populated only when the Minutes explicitly identify the matter by
  an era-based number, such as `case-6`; `era_label` preserves the display form
  `Case #6`.
- `minute_ids` contains other printed identifiers, such as `5-13` or `5-87`,
  when those identifiers are available. They are aliases, not additional cases.
- `title` is the clean editorial caption. Roster text, citation brackets,
  disposition notes, and `Summary:` material do not belong in the title.

## Proceeding types

`proceeding_type` is the procedural posture, not the subject matter. Subject
matter belongs in `topic_tags`.

| Code | Use |
|---|---|
| `complaint` | A complaint challenging an action or decision of a lower court. This is the default for an ordinary `v.` case without another posture. |
| `appeal` | An appeal from a lower-court judgment, including an appeal of censure or discipline. |
| `reference` | A BCO 41 reference submitted by a lower court for advice, other action, or a requested original adjudication. The purpose/stage belongs in the summary and provisions, not in a competing primary type. |
| `review_and_control` | A BCO 40 supervisory matter, including a memorial or citation proceeding under BCO 40-5. |
| `original_jurisdiction_request` | A BCO 34-1 request or petition asking the General Assembly/SJC to assume original jurisdiction. The later trial or judgment remains part of that proceeding. |
| `other` | A genuine judicial matter that does not fit the categories above; explain it in `disposition_detail`. |

Do not create separate proceeding types for discipline, ordination, divorce,
church property, or other subjects. Those are topic tags.

## Outcomes / dispositions

`outcome` and `disposition` use the same canonical code. `disposition` is the
compatibility name used by the existing catalogue; `outcome` is the explicit
facet for search and analysis. `disposition_detail` retains the useful nuance
that cannot be represented by one code, including remand, annulment,
affirmance, specification-level votes, or mootness.

| Code | Meaning |
|---|---|
| `sustained` | The challenge or appeal succeeded in the material respect decided. |
| `partially_sustained` | At least one material specification succeeded and at least one failed or was otherwise unresolved. |
| `not_sustained` | The complaint/specification failed, or the lower court's action was confirmed. |
| `denied` | The court expressly denied the complaint, appeal, or request. |
| `dismissed` | The matter was dismissed without a merits determination or by an express dismissal order. |
| `out_of_order` | The matter was not properly before the court, including an administratively out-of-order matter. |
| `in_order` | The matter was found in order, without this record supplying the final merits disposition. |
| `administrative` | An administrative judicial-business action, such as appointing or receiving a commission. |
| `referred` | The matter was referred/remanded to another court or commission for further action. |
| `granted` | A request or petition was granted where the record does not use a more specific merits code. |
| `abandoned` | The complainant/appellant withdrew, failed to appear, or otherwise abandoned the matter. |
| `other` | A real disposition that cannot safely be mapped to the controlled vocabulary; explain it in `disposition_detail`. |

`withdrawn`, `deemed_abandoned`, and equivalent wording normalize to
`abandoned`; `administratively_out_of_order` normalizes to `out_of_order`;
`sustained_in_part` and mixed specification results normalize to
`partially_sustained`; and remand/remission normalizes to `referred` when no
stronger merits result is present. The original wording is not discarded.

## Metadata facets

- `summary` is a concise editorial headnote: dispute, higher-court action, and
  decisive limiting detail where available. It is never substituted for the
  verbatim case page.
- `summary_review_status` distinguishes `audited` summaries—checked against
  the available case source or official docket record—from `pending_audit`
  summaries inherited from the reconciled corpus and not yet individually
  reviewed in this pass.
- `summary_source` and `summary_audit_basis` record the source layer and the
  repeatable quality gate used for the audit. `scripts/14_judicial_summary_audit.py`
  writes `index/judicial_case_summary_audits.json`; editorial overrides remain
  the place for substantive rewriting.
- `bco_provisions` contains only provisions actually attributed to the case,
  normalized to bare codes such as `38-1` or `43-1`. Non-BCO constitutional
  references remain in prose or topics.
- `topic_tags` is a small set of subject tags, not a list of every noun in the
  record.
- `review_standards` is the authoritative review-standard list. Its controlled
  values are `clear_error_facts`, `clear_error_discretion`,
  `independent_constitutional`, and `bco_40_5`. A case may have more than one
  because different issues or procedural stages can receive different treatment.
- `standard_of_review` is a compact derived/display value for that same facet:
  one applicable standard, `mixed` when there are several, `not_reached` when
  the matter ended before merits review, `not_applicable` for a non-appellate
  proceeding such as an original-jurisdiction request, `not_stated` when the
  court reviewed the matter but did not state a distinct standard, or `unknown`
  when the decision text is unavailable. Its values also include `bco_40_5` for
  a merits-level BCO 40-5 supervisory review.
- `standard_of_review_detail` gives the short human-readable explanation and
  the relevant BCO subsection where the source identifies one. The generator
  examines the adopted decision only; a dissent's proposed standard is not
  silently combined with the court's standard.
- `classification_status` is `classified`, `needs_review`, or `roster_only`.
  `roster_only` means the official case is known but the local Minutes
  extraction has not yet supplied enough metadata; it is not permission to
  invent a summary or disposition.

The generator is `scripts/12_case_taxonomy.py` and is run after the existing
roster reconciliation/hunt steps. It is deliberately additive so older links
and citation edges continue to use their legacy keys.
