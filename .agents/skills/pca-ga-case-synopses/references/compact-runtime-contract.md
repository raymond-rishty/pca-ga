# Compact synopsis runtime contract

Use this contract for one case at a time. The supplied case text is the only
authority for the case-specific answer. Catalog metadata and examples are hints;
correct them when the text conflicts. Never invent a reason, result, or rule.

## Read and classify

Confirm the canonical case ID and title, procedural vehicle, deciding or adopting
body, challenged action, every material successful and unsuccessful issue,
decisive adopted reasons, relief, remaining proceedings, and qualifications.
Distinguish the adopted judgment from party arguments, lower-court actions,
committee proposals, attachments, and separate opinions. If a decision is
incorporated by reference, use its supplied result; flag a repair when a material
incorporated result is unavailable. A sparse notice supports only a short status
synopsis.

Use exactly one `matter_type` code:

- `complaint`: challenge to a lower court's action or decision.
- `appeal`: appeal from a lower-court judgment, censure, or discipline.
- `judicial_reference`: BCO 41 reference from a lower court, including a trial
  accepted by reference.
- `original_jurisdiction_request`: BCO 34-1 request that the GA/SJC assume
  original jurisdiction.
- `bco_40_5_matter`: memorial, report, citation, or resulting matter expressly
  under BCO 40-5.
- `review_and_control`: other BCO 40 supervisory review or citation.
- `other`: genuine judicial matter outside these codes; explain it.

Matter type describes the proceeding being decided, not a procedure mentioned
in its history. A complaint about a reference or original jurisdiction remains a
complaint. A BCO 41 trial is not a BCO 34-1 request.

Use one or more exact `final_dispositions` codes, in operative order:
`sustained`, `partially_sustained`, `not_sustained`, `denied`, `granted`,
`guilty`, `not_guilty`, `administratively_out_of_order`,
`judicially_out_of_order`, `out_of_order`, `dismissed`, `withdrawn`,
`abandoned`, `moot`, `affirmed`, `reversed`, `vacated`, `annulled`, `remanded`,
`referred`, `in_order`, `no_final_disposition`, or `other`.

Classify only the deciding body's action and preserve exact issue-level results
in `disposition_detail`. Do not turn a lower-court verdict, requested remedy, or
hypothetical result into a disposition. Use administrative or judicial
out-of-order only when the source identifies that subtype. Dismissal, withdrawal,
abandonment, mootness, and out-of-order rulings are distinct. Reversal, vacatur,
or annulment does not imply acquittal. Remand returns a matter for proceedings;
referral sends a matter or materials elsewhere. An answer *by reference to*
another decision is not `referred`. Use `no_final_disposition` only for a truly
interlocutory or unfinished record, not merely because no merits opinion appears.

## Draft

Write a public synopsis that lets a reader decide whether to retrieve the case.
Lead with the concrete issue, not names, addresses, or filing chronology. State
the decision, decisive adopted reason, practical relief or next step, and the
case's useful distinction or limitation. Preserve mixed outcomes and refused
relief. Usually write 60–90 words for a reasoned decision and less for a sparse
record. Do not claim later influence or historical importance without evidence.

Score 0–2 on each dimension:

- `concrete_dispute`: identifies the challenged conduct or court action.
- `decision`: states every material success and failure.
- `decisive_reason`: explains the adopted reason, or faithfully says none is given.
- `distinctive_value`: preserves the useful rule, distinction, limit, or remedy.
- `fidelity`: keeps allegations, findings, adopted reasoning, separate opinions,
  and procedural history distinct.
- `economy`: every retained detail helps explain the dispute, result, or value.

Fidelity must be 2 for publication; a total score cannot cure a material error.
Examples guide editorial form only and are never evidence for this case.

## Verify and return

First create `first_summary`. Then reread the operative judgment and adopted
reasoning and produce corrected `summary`. Check actor, challenged action and
grounds, each material outcome and remedy, what remained in force or was refused,
and historical qualifications. `verification_notes` must name actual corrections
or specifically identify what was rechecked; never say only "verified."

Return the required JSON only. Keep the five `evidence_notes` sections concise
and source-located: identity/adoption; dispute; outcomes/reasons; qualifications;
incorporated decisions. Give precise line or printed-page locators and the supplied
source path/hash. Set `repair_needed` only for an actual source or catalog defect,
and explain it. Friendly prose belongs in the synopsis; enum fields retain codes.
