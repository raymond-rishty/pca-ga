# Judicial synopsis candidate audit

Use the candidate-review rendering of
[`JUDICIAL-CASES.md`](../JUDICIAL-CASES.md) to review the selected Sol and
DeepSeek drafts before any candidate is promoted to the maintained editorial
overrides. Work in batches of roughly 10–20 cases so decisions and corrections
remain easy to verify.

For the faster side-by-side review interface, run:

```powershell
.\scripts\run-synopsis-review.ps1
```

This opens a local reviewer at `http://127.0.0.1:8765/`. The left pane shows the
case text; the right pane compares the existing and candidate synopses and their
metadata. Decisions are saved immediately to
`candidate-intake-1/audit-decisions.json`. Stop the server with `Ctrl+C`.

Keyboard controls:

| Key | Action |
|---|---|
| `A` | Approve after completing the source check |
| `C` | Edit synopsis, matter type, or dispositions |
| `Ctrl+Enter` | Save the correction |
| `R` | Reject the candidate; an audit note is optional but useful |
| `X` | Mark source repair needed; an audit note is required |
| `U` | Return the case to unreviewed |
| `J` / `K` | Next / previous case |

Enter a reviewer name or initials before recording a decision. Approval here
means that the candidate passed the source audit; it does not authorize
publication. All decisions are reversible.

## Risk-based corpus audit

Do not treat all candidates as equally informative review work. Build the
deterministic priority queue before a review session:

```powershell
python scripts/79_prioritize_synopsis_review.py
```

The default queue contains three deliberately separate groups:

- **Must review** includes candidates with a reported source problem or a
  canonical-identity remap. These cannot be cleared by sampling.
- **High priority** ranks meaningful changes from the prior synopsis and
  metadata, mixed outcomes, special procedural vehicles, dissenting records,
  benchmark cases, and unusually sparse or long sources.
- **Statistical sample** is a fixed random sample, stratified by provider,
  matter type, and risk band, from cases not selected in the first two groups.
  Do not replace convenient or interesting sample cases; doing so invalidates
  the error-rate estimate.

The reviewer opens on **Recommended audit queue**. Use its priority filter to
work one group at a time or to inspect all 456 candidates. Each case displays
the mechanical reasons for its priority. The score orders attention; it is not
evidence that a synopsis is accurate or inaccurate.

The header tracks completion of the random sample. For that sample, approval
counts as a pass; correction, rejection, or source repair counts as an observed
failure. The reviewer reports a 95% Wilson interval after sampled cases are
decided. This estimates the failure rate only for the lower-risk population
from which the sample was drawn. It does not certify individual unread cases,
and it must not be combined with the deliberately selected cases as though the
whole queue were random.

The sample uses seed 149 and remains stable when the priority file is rebuilt.
Use `--target`, `--random-sample`, or `--seed` only when deliberately creating a
new audit design, and record that change before comparing results.

The review rendering overlays three candidate fields: **matter type**, **final
disposition**, and **candidate synopsis**. Review basis, BCO provisions, topic
tags, title, aliases, classification status, and source links remain the current
catalog values; they are useful context but are not claims that the synopsis
model independently verified them.

## Review one case

1. Open the row's **Source** link and its **Candidate** link. Confirm that the
   source contains the target docket rather than a neighboring or related case.
   If the decision incorporates another judgment, locate and read the material
   incorporated result as well.
2. Identify the actual deciding body's adopted action. Distinguish it from a
   party's allegations or requested relief, the lower court's ruling, a panel or
   committee recommendation not adopted, and a dissent or other separate opinion.
3. Check the candidate's **matter type** against the proceeding actually before
   the Assembly or SJC: complaint, appeal, judicial reference,
   original-jurisdiction request, BCO 40-5 matter, or review and control. Classify
   the vehicle, not the subject matter of the dispute.
4. Check every **final disposition** against the operative judgment. Preserve
   distinct results such as sustained versus partially sustained; denied versus
   not sustained; administratively versus judicially out of order; guilty versus
   not guilty; and reversed, annulled, vacated, or remanded. A remand does not by
   itself imply acquittal, and an answer by reference is not a referral.
5. Read the synopsis sentence by sentence. It should accurately and economically
   state:

   - the concrete issue-producing dispute;
   - what the deciding body held;
   - the decisive reason actually adopted;
   - the practical relief or procedural consequence; and
   - any material unsuccessful issue, limitation, condition, or remaining
     proceeding.

6. Reject allegations phrased as findings, dissenting reasoning phrased as the
   holding, invented significance, and broad constitutional rules not stated by
   the case. Names, locations, vote counts, and filing chronology should remain
   only when they help explain the holding or result.

## Record one of three decisions

### Pass

Use **pass** only when the matter type, dispositions, and every material synopsis
claim agree with the source. Fidelity is a hard requirement: attractive prose or
a high model score cannot cure a misstated holding, actor, reason, remedy, or
qualification.

### Revise

Use **revise** when the source is adequate but the candidate needs a prose or
metadata correction. State the exact correction, preferably with a source
locator. Typical examples are an omitted unsuccessful issue, a remand described
as an acquittal, a recommendation confused with the adopted judgment, or excess
party detail displacing the legal issue.

### Source repair

Use **source repair** when an accurate decision cannot be established from the
linked case page—for example, the page is truncated, contains the wrong docket,
ends at a pending notice, combines dockets incorrectly, or omits an incorporated
decision. Do not make a candidate pass by guessing around the source defect.

## Report a review batch

The simplest review note is:

```text
Pass: 1976-01, 1976-02, 1977-01

Revise:
- 1978-01 — The judgment remanded for a new hearing; it did not sustain the
  underlying complaint. See the adopted judgment, lines 84–91.

Source repair:
- 1980-01 — Linked page contains only the initial docket notice; locate the later
  disposition before approving a synopsis.
```

For a passed case, no generic “looks good” explanation is needed; **pass** means
the complete checklist above was performed. For a revision or repair, identify
the defect rather than supplying only a score. Send or record batches in
ascending case order so the review can resume without ambiguity.

## Promotion boundary

Review decisions should be recorded separately from the model candidates.
Passing the conservative DeepSeek gate or the structured Sol validation is not
an audit. Only source-checked, approved cases should be merged into
`index/judicial_case_editorial_overrides.json`, regenerated into
`index/judicial_cases.jsonl`, and rendered into the ordinary
`index/JUDICIAL-CASES.md`. Source repairs follow the case-ingestion workflow
before synopsis approval.

To rebuild the candidate review page:

```powershell
python scripts/13_judicial_taxonomy_index.py --candidate-registry index/synopsis_workflow/candidate-intake-1/registry.json
```

To restore the ordinary canonical page:

```powershell
python scripts/13_judicial_taxonomy_index.py
```
