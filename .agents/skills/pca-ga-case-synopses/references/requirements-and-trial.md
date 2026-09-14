# Structured requirements and model qualification

## Evidence before prose

Keep a compact, source-located evidence note with these named sections:

- Identity and adoption: source caption, docket, actual deciding body, and passage
  adopting the recommendation or judgment. A committee recommendation is not
  itself the Assembly's adjudication.
- Dispute: challenged conduct and why the lower body acted. “Divestiture” alone
  can hide the important distinction between discipline and removal without censure.
- Outcomes and reasons: each material successful/unsuccessful issue and its reason.
- Qualifications: relief refused, proceedings remaining, conditions and material
  historical rules. Explain omissions rather than silently dropping them to fit
  a word limit.
- Incorporated decisions: identify and read the incorporated result, or record
  the missing source. Preserve its outcome in the synopsis without inventing a
  separate ruling on the incorporating docket. State not applicable when appropriate.

Then draft the synopsis. Reopen the operative source for a separate same-model
check, comparing the note and draft to the source. A self-score does not establish
accuracy. Save actual corrections and source limitations. For a trial, retain the
first draft as well as the final candidate so correction effort is inspectable.

## Structured output contract

For new evaluation records use these fields, keeping the previous bakeoff unchanged:

| Field | Requirement |
|---|---|
| `case_id`, `title` | Source-checked canonical identity; do not invent an ID. |
| `matter_type` | Exact code from `docs/JUDICIAL-CASE-TAXONOMY.md`. |
| `final_dispositions` | Nonempty, unique, ordered array of exact taxonomy codes. |
| `disposition_detail` | Source-specific wording, issue-level results and remedies. |
| `summary` | Public synopsis, not editorial instructions. |
| `sources` | Objects with repository-relative `path`, `sha256`, precise `locator`, and `supports`. |
| `evidence_notes` | The five named sections above, each source-located. |
| `source_limits` | Complete opinion, sparse final notice, or actual unresolved defect, explained. |
| `benchmark_examples` | Array of consulted example IDs; their prose is not evidence. |
| `scores`, `score_reasons` | Six rubric dimensions, integer 0–2, with reasons for each. |
| `verification_notes` | Actual pass type, outcome-to-sentence coverage, corrections and remaining limits. |
| `repair_needed`, `repair_notes` | Boolean and description of any actual source/catalog defect. |

Use `final_dispositions`, not the ambiguous pilot field `dispositions`. For example,
use `vacated` with detail identifying the portion, not a new code `vacated in part`.
Use `other` with an explanation if no code safely fits; do not automatically map
an answer by reference to `referred`. Friendly display labels do not belong in
enum fields. Before returning, mechanically compare every code to the current
taxonomy and check required fields, JSON types, duplicates and source hashes.
Such checks do not establish that a valid code is historically correct.

The ledger helper retains its existing checkpoint payload format. Put evidence
in triage notes, the synopsis in draft fields, and outcome coverage in verification
qualifications; evaluation records are not directly importable ledger payloads.
These additional editorial requirements are not automatically enforced by the
existing helper. Do not claim its success validates this entire contract.

## Qualification trial, not permanent double-model review

The question is whether one model can produce acceptable candidates with its own
source-checking pass. A one-time external acceptance audit is an evaluation cost,
not automatically a larger-model review of every future case. Never assume a
model can reliably route its own undetected mistakes to another model.

Before the next authorized run:

1. Freeze 15 cases absent from the first bakeoff and from direct benchmark sample
   synopses. Include at least four actual appeals, complaints, nonmerits results,
   and other vehicles where uncontaminated examples are available. Record any
   missing stratum. Catalog labels are provisional until source-checked.
2. Save case IDs, the requirements/benchmark versions and assignment. Do not give
   the drafter expected answers, case-specific failure hints, or previous model
   comparisons. Analogous examples from other cases remain available.
3. Run one draft and source-check cycle per case, permitting corrections from that
   pass and mechanical validation. Retain first and final drafts. Measure actual
   start/end times, usage when available, reruns and interventions. Do not invent
   token counts or substitute elapsed time for billed consumption.
4. Audit every final candidate regardless of confidence or repair flags. Keep
   audit corrections separate from the measured candidate. Do not repeatedly
   improve the test outputs until they pass and report only the repaired results.

Proposed pilot acceptance criteria, fixed before seeing outputs: zero material
holding, actor, adopted-reasoning or qualification errors; at most one minor
factual correction across 15 records; valid metadata in every final record; and
at least 10/12 on each reasoned synopsis. Score sparse notices separately rather
than inventing content to meet a threshold. Report all exceptions, not just means.
These are model-selection criteria, not a statistical guarantee about the corpus.

For a cost comparison, give Sol the same revised assignment on the same unseen
cases when authorized. Measure generation, self-check, correction and rerun usage
consistently. Do not compare Terra's new scores to Sol's easier old sample as if
equivalent. If usage is unavailable, leave the cost conclusion unproven.

A successful trial supports a bounded rollout with random acceptance sampling,
not checks only on cases the drafter flags. A failed trial calls for another
model/workflow decision, not a hidden permanent Sol pass called a Terra saving.
This reference does not itself authorize agent launches or publication.
