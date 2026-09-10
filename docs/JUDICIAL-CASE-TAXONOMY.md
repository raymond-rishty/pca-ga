# Judicial-case taxonomy

This is the controlled vocabulary for the canonical judicial-case layer. The
authoritative checklist is `index/sjc_official/roster.jsonl`; the Minutes remain
the source for verbatim case text, and `index/cases.jsonl` supplies extracted
metadata when it has been reconciled to the roster.

## Identity

`index/judicial_cases.jsonl` contains one record per unique rostered case. The
current saved roster has 480 entries; after source duplicates are collapsed and
expressly consolidated dockets are expanded, the generator emits 476 records:
475 canonical IDs plus one era-only record.

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

## Matter types

`matter_type` is the procedural vehicle, not the subject matter. Subject matter
belongs in `topic_tags`. BCO 39-1 supplies the broad appellate categories of
review and control, reference, appeal, and complaint; this taxonomy also names
BCO 34-1 requests and BCO 40-5 matters when the source identifies those more
specific vehicles.

| Code | Use |
|---|---|
| `complaint` | A complaint challenging an action or decision of a lower court. This is the default for an ordinary `v.` case without another posture. |
| `appeal` | An appeal from a lower-court judgment, including an appeal of censure or discipline. |
| `judicial_reference` | A BCO 41 reference submitted by a lower court for advice, other action, or a requested original adjudication. |
| `original_jurisdiction_request` | A BCO 34-1 request or petition asking the General Assembly/SJC to assume original jurisdiction. The later trial or judgment remains part of that proceeding. |
| `bco_40_5_matter` | A memorial, report, citation, or resulting judicial matter expressly proceeding under BCO 40-5. Its review basis is the important-delinquency-or-grossly-unconstitutional-proceeding threshold. |
| `review_and_control` | Another BCO 40 supervisory matter, including a citation arising from review of presbytery records, that the source does not identify as a BCO 40-5 matter. |
| `other` | A genuine judicial matter that does not fit the categories above; explain it in `disposition_detail`. |

Do not create separate matter types for discipline, ordination, divorce,
church property, or other subjects. Those are topic tags.

## Final dispositions

`final_dispositions` is an ordered list because a decision can contain more
than one terminal ruling or action. An appeal may be sustained and remanded; a
complaint may be judicially out of order and dismissed. `disposition_detail`
preserves the source wording and specification-level detail.

Matter type and final disposition remain independent. The combination
`matter_type: complaint` plus `final_dispositions: [sustained]` renders as
“Complaint sustained”; it does not require a redundant
`complaint_sustained` code.

| Code | Meaning |
|---|---|
| `sustained` | The challenge or appeal succeeded in the material respect decided. |
| `partially_sustained` | At least one material specification succeeded and at least one failed or was otherwise unresolved. |
| `not_sustained` | The complaint/specification failed, or the lower court's action was confirmed. |
| `denied` | The court expressly denied the complaint, appeal, or request. |
| `granted` | A request was expressly granted where `sustained` is not the source's formulation. |
| `guilty` | The deciding body rendered a guilty verdict in a matter within its trial jurisdiction. |
| `not_guilty` | The deciding body rendered a not-guilty verdict or acquitted the accused. This does not describe a lower-court acquittal merely mentioned in procedural history. |
| `administratively_out_of_order` | The matter failed an administrative filing, standing, timing, or form requirement. |
| `judicially_out_of_order` | The judicial body expressly found the matter judicially out of order. |
| `out_of_order` | The source says only that the matter was out of order and does not identify which kind. |
| `dismissed` | The matter was dismissed without a merits determination or by an express dismissal order. |
| `withdrawn` | The initiating party withdrew the matter. |
| `abandoned` | The matter was deemed abandoned or ended through nonappearance or another failure to prosecute. |
| `moot` | The deciding body treated the matter, or a distinct part of it, as moot. |
| `affirmed` | A lower-court judgment or action was expressly affirmed or confirmed. |
| `reversed` | A lower-court judgment, censure, or action was expressly reversed. |
| `vacated` | A judgment, censure, or action was expressly vacated. |
| `annulled` | A judgment, censure, or action was expressly annulled. |
| `remanded` | The matter was sent back or remitted for further proceedings or correction. |
| `referred` | The matter or materials were referred to another body without a remand ruling. |
| `in_order` | The matter was found in order, without this record supplying the final merits disposition. |
| `no_final_disposition` | The available record reports only an administrative or interlocutory action and supplies no final disposition. |
| `other` | A real disposition that cannot safely be mapped to the controlled vocabulary; explain it in `disposition_detail`. |

Only the deciding body's action is classified. A summary's reference to a
lower-court acquittal, a requested remand, or a party's allegation does not
become a final disposition. The original wording is not discarded.

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
- `review_standards` is the single authoritative review facet. Its controlled
  values are `factual_findings`, `discretion_and_judgment`,
  `constitutional_interpretation`, and
  `important_delinquency_or_grossly_unconstitutional_proceeding`. These are
  basis labels, not conclusions about whether the court was correct. A case may
  have more than one only when the adopted decision applies different bases to
  distinct issues.
- Older `standard_of_review` override values are migration residue and are
  ignored by the generator. A substantive basis must be recorded in
  `review_standards` or supported by the adopted decision text; the generator
  does not translate legacy labels into new ones.
- `standard_of_review` is a compact derived/display value for that same facet:
  one applicable basis, `mixed` when there are several, `not_reached` when
  the matter ended before merits review, `not_applicable` for a non-appellate
  proceeding such as an original-jurisdiction request, `not_stated` when the
  court reviewed the matter but did not state a distinct standard, or `unknown`
  when the decision text is unavailable. Its
  `important_delinquency_or_grossly_unconstitutional_proceeding` value
  identifies the BCO 40-5 threshold rather than an appellate level of deference.
- `standard_of_review_detail` gives the high-fidelity explanation and the
  relevant BCO subsection where the source identifies one. The generator
  examines the adopted decision only; a dissent's proposed basis, a generic
  citation, or a boilerplate quotation is not silently promoted to a case
  classification.
- Human-readable views group the shared BCO 39-3 deference rule before naming
  its applications. For example, a case invoking both subsections (2) and (3)
  displays “Great deference unless clear error (factual findings; discretion
  and judgment)” rather than repeating the deference language for each basis.
- `classification_status` is `classified`, `needs_review`, or `roster_only`.
  `roster_only` means the official case is known but the local Minutes
  extraction has not yet supplied enough metadata; it is not permission to
  invent a summary or disposition.

The generator is `scripts/12_case_taxonomy.py` and is run after the existing
roster reconciliation/hunt steps. It is deliberately additive so older links
and citation edges continue to use their legacy keys.
