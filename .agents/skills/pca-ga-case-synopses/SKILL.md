---
name: pca-ga-case-synopses
description: Write, revise, or assess editorial synopses of PCA General Assembly judicial cases using the case text and the repository's synopsis benchmarks. Use for judicial case-summary drafting, improvement, and scoring; use the case-ingestion workflow for repairing case text or catalog metadata.
---

# PCA judicial case synopses

Write a concise editorial explanation of the dispute, the deciding court's
answer, its decisive reason, and the practical result. Help readers understand
why they would retrieve this case without substituting the synopsis for the
authoritative text. This skill belongs to the pca-ga repository; resolve the
relative links below from this file, not from the current shell directory.

## Select the reference and evidence

For corpus-wide or resumable batch work, first read
[the batch workflow](references/batch-workflow.md). Its ledger tracks individual
dockets, source evidence, drafts, verification, and approval without treating
existing catalog audit labels as proof of review. Use the helper for checkpoints;
it does not write synopses or publish to production automatically.

Read the opening scoring guidance and coverage limits in
[JUDICIAL-SYNOPSIS-BENCHMARKS.md](../../../docs/JUDICIAL-SYNOPSIS-BENCHMARKS.md).
Then read the relevant matter-type coverage table, the complete entries for
the closest applicable examples, and any discrepancy notes for the target
case. Do not load the entire example library for an ordinary single-case
request. The examples are editorial candidates, not infallible holdings or
evidence that a catalog classification is correct.

Useful starting points for different editorial problems:

| Problem | Benchmark entries |
|---|---|
| Some issues succeed and others fail | C01 Allin; C02 Turner |
| Different remedies within one decision | A01 Grady; A03 Mitchell |
| Dismissal's practical effect | A19 Spann; A20 Marshall |
| Allegations, acquittal, and trial versus appellate posture | A05 Dudt; J04 Herron |
| Constitutional error found but relief refused | B03 Northwest Georgia |
| Procedural rulings and separate opinions | C17 Wilson; A10 Robar |
| Sparse notices or no adopted explanation | C20 Daniels; C23 Oh; J02 Evangel |
| Supervisory action rather than an adversarial win | R01 Korean Eastern; R04 South Florida |
| A decision incorporated by reference | O04 Missouri; O05 Central Indiana |

Use [JUDICIAL-CASE-TAXONOMY.md](../../../docs/JUDICIAL-CASE-TAXONOMY.md)
when assigning or interpreting labels. Use friendly descriptions in prose;
do not insert enum values into a synopsis.

Locate the target's actual decision in `cases/` and its linked `markdown/`
minutes. Confirm the docket, title, deciding body, year, and source boundaries.
Canonical and printed era IDs may differ. A shared page may contain several
distinct proceedings, unrelated neighboring cases, or later manual proposals.
Read the target decision's facts, issues, adopted judgment, and relevant
reasoning, not merely its generated header or existing summary. Distinguish
adopted reasoning from panel proposals, attachments, and separate opinions.

If the page is incomplete, misidentified, or only an initial docket notice,
check the minutes and later records before treating the matter as unresolved.
Do not borrow another docket's holding to fill the gap. If the decision cannot
be established, identify the source limit and provide only a supported status
synopsis. Date a genuinely historical pending stage; do not imply it is still
pending today.

## Establish what the synopsis must preserve

Before drafting, keep a compact evidence note, separate from the public prose:

- Case identity and procedural vehicle actually before the deciding court.
- The challenged conduct or court action and the material question presented.
- The adopted answers, including material successful and unsuccessful issues.
- Decisive reasons, relief, remaining proceedings, and important limitations.
- Source file and section/page or line references supporting those claims;
  identify information drawn only from a separate opinion.

Record the adopting body and its operative action separately from the committee
or panel that recommended it. Verify names retained in the caption or prose
against the actual source, not the generated heading. Record evidence for any
conflict; omit an unnecessary name rather than copy an uncertain spelling.

Retain these distinctions where the case makes them consequential:

- A complaint about a reference or an assumption of jurisdiction remains a
  complaint. A trial accepted through BCO 41 is not a BCO 34-1 request.
- The deciding body's ruling is not a lower-court ruling recited in the facts,
  a party's requested remedy, or a hypothetical result discussed in reasoning.
- An unsuccessful challenge, a guilty verdict, and a conviction left intact
  with reduced censure are different outcomes.
- Reversal, annulment, or vacatur may permit further proceedings rather than
  acquit anyone. Dismissal may protect the appellant rather than defeat them.
- “Answered by reference to” another decision is not a referral to another
  body. Read the incorporated decision and state the material result supplying
  the answer while keeping the proceedings distinct. A docket number or “the
  answer lies elsewhere” is not a substitute for explaining the outcome. If the
  incorporated text cannot be located, state that limitation; do not invent a
  separate grant, denial, or reason for the incorporating notice.
- Administrative and judicial out-of-order rulings, unspecified out-of-order
  findings, withdrawal, abandonment, and mootness are not interchangeable.
  Absence of a merits opinion does not mean absence of a final disposition.
- Acceptance of responses or referral for records review is a real supervisory
  action, but need not imply substantive approval of the underlying records.

Include a review basis only when the adopted decision supports it and it helps
explain the result. Do not infer clear error, a BCO 40-5 threshold, or any other
review basis from matter type, a citation alone, or a dissent. Preserve any
historical version of a rule that explains the outcome.

## Draft and assess

Usually lead with the issue-producing facts, not the participants' full names,
church addresses, or the filing chronology. The surrounding card or index
already supplies the caption. Keep a particular only when it explains the
holding, such as a closely divided restoration vote or an intervening rule
change. If the synopsis will stand alone, include enough identity to orient
the reader.

For a reasoned case, aim for roughly 60 to 90 words; allow more for material
complexity and fewer for a short procedural record. A useful shape is concrete
dispute, decision and reason, then relief or limiting qualification. This is
not a mandatory sentence template. Explain the distinctive constitutional
distinction, evidence problem, procedural requirement, or remedy within the
paragraph. Do not manufacture a “landmark” claim, later influence, or a broad
rule that exceeds the case.

Compare the draft to the selected benchmarks. Assess the six dimensions in
the benchmark rubric: concrete dispute, decision, decisive reason, distinctive
value, fidelity, and economy, each from 0 to 2. Use the score to find revisions,
not to award automatic perfect marks. For a sparse source, accurately retaining
its limits satisfies the applicable reasoning test; invented explanation does
not. A materially inaccurate holding or omitted material qualification blocks
publication regardless of the total score.

Check every substantive sentence against the evidence note. Remove names and
chronology that displace the issue; allegations presented as facts; dissenting
reasoning presented as the holding; unsupported generalizations; and repeated
disposition language. Recheck mixed outcomes after shortening. Keep editorial
lessons, scoring comments, and drafting instructions out of the synopsis itself.

Make the source-check a comparison, not an affirmation: reopen the adopted
judgment and relevant reasoning, then compare who acted, the challenged action
and its grounds, each material outcome and remedy, what remained in force or
was refused, and any decisive historical qualification. Map each material
outcome to a draft sentence or explain why omitting it does not change the
reader's understanding. Record actual corrections and remaining limits, not
just “verified.” This pass can use the same model; it is not independent
certification and does not require an automatic larger-model handoff.

For structured batch/evaluation output and model qualification, read
[the requirements and trial contract](references/requirements-and-trial.md).

For a drafting request, return the synopsis with its case ID/title and a source
reference, with any unresolved limitation outside the paragraph. Add scores
and brief reasons when the user asks for assessment or comparison; do not force
a visible scoring report onto every writing request. For batches, keep evidence
and assessment case-specific, including separate outcomes for related dockets.

## Applying approved synopses

A request for examples or evaluation does not authorize publication, corpus
repair, or a PR push. When asked to apply changes, preserve existing work and
inspect the current writers and consumers of the affected summary fields.

The canonical editorial layer uses
[`index/judicial_case_editorial_overrides.json`](../../../index/judicial_case_editorial_overrides.json)
and [`scripts/12_case_taxonomy.py`](../../../scripts/12_case_taxonomy.py).
Merge into the correct record without replacing unrelated overrides. Do not
edit only the generated `index/judicial_cases.jsonl` or assume this layer also
updates the legacy index, case pages, and app summaries. Trace and update the
requested surfaces through their maintained sources and generators; inspect
the resulting diffs for unrelated changes. Preserve verbatim case text.

Do not mark an entry audited solely because a heuristic or generator accepts
it. Record only review status and provenance justified by the actual source
check and supported by the current schema. Keep rubric scores in a review
artifact or response unless their persistence has been requested and designed.

If a metadata or source defect prevents an accurate synopsis, report it with
evidence rather than silently reproducing it. For authorized case-text or
catalog repairs, follow
[pca-ga-case-ingestion](../pca-ga-case-ingestion/SKILL.md), including its
dependent-output verification. Drafting a correct synopsis does not by itself
complete that repair workflow.
