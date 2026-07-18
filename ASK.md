---
layout: ask
permalink: /ask.html
title: Ask AI about the PCA General Assembly record
description: A source-disciplined research prompt for finding and citing the PCA Minutes of the General Assembly.
---

# Ask AI about the PCA Constitution and history

Use this prompt with any AI assistant that can browse the web. It directs the assistant through the corpus indexes, requires it to open the verbatim minutes, and asks it to distinguish different kinds of General Assembly records before drawing a conclusion.

## Copy the research prompt

Replace the final bracketed line with your question. You can also give the AI a known BCO provision, case number, presbytery, Assembly, or approximate year.

<div class="prompt-toolbar">
  <span>Source-disciplined PCA research prompt</span>
  <button type="button" id="copyPrompt">Copy prompt</button>
</div>

```text
Research the question below using the PCA General Assembly Minutes corpus:
https://raymond-rishty.github.io/pca-ga/

Base your answer on the corpus, not on memory or a generic web summary.

REQUIRED RESEARCH WORKFLOW

1. Begin with the relevant corpus indexes. Use as many as the question requires:
   - Judicial cases: https://raymond-rishty.github.io/pca-ga/index/CASES.html
   - Judicial cases by constitutional provision: https://raymond-rishty.github.io/pca-ga/index/CASES-BY-PROVISION.html
   - Review of Presbytery Records exceptions by provision: https://raymond-rishty.github.io/pca-ga/index/RPR-BY-PROVISION.html
   - Constitutional inquiries: https://raymond-rishty.github.io/pca-ga/index/INQUIRIES.html
   - CCB advice on overtures and amendments: https://raymond-rishty.github.io/pca-ga/index/CCB-OVERTURE-ADVICE.html
   - Overtures and their outcomes: https://raymond-rishty.github.io/pca-ga/index/OVERTURES.html
   - Position papers and study committee reports: https://raymond-rishty.github.io/pca-ga/index/STUDIES.html
   - Full corpus and per-volume outlines: https://raymond-rishty.github.io/pca-ga/index/INDEX.html

2. Treat an index entry or headnote only as a finding aid. Follow its link and inspect the verbatim minutes before relying on it.

3. Identify what kind of record you found and its procedural status. Do not flatten together:
   - an adopted General Assembly action,
   - a judicial decision or procedural disposition,
   - non-binding CCB advice,
   - an RPR exception and its later resolution,
   - a committee recommendation,
   - a minority report,
   - an overture that was answered, declined, referred, or amended,
   - and a study report with its particular adoption or commendation status.

4. Quote only the language that directly bears on the question. For every material quotation or factual claim, give:
   - a direct link to the relevant corpus page, and
   - the Minutes volume and printed page in the form “M50GA p.517.”

5. When the record develops across multiple Assemblies, trace the sequence rather than quoting only the final entry.

6. If the corpus does not answer the question, say so plainly. Distinguish “not found in this corpus” from “the PCA has never addressed this.” Do not invent quotations, page numbers, outcomes, or authority.

ANSWER FORMAT

- Direct answer: State the best-supported conclusion first.
- Evidence: Present the relevant records with brief quotations, links, and Minutes citations.
- Authority and limits: Explain the source type, procedural posture, and any uncertainty or contrary material.

The corpus records what the General Assembly did and said over time. It is not a substitute for checking the current text of the PCA Constitution when the question concerns present constitutional wording.

QUESTION

[INSERT YOUR QUESTION HERE]
```

## Why this prompt is stricter

The catalogues contain editorial descriptions designed to help researchers locate material. The underlying minutes remain the evidence. This prompt therefore makes the AI leave the catalogue, read the source page, and tell you whether it found an adopted action, judicial decision, advisory answer, records-review finding, or some other kind of material.

## Questions that work well

- “What has the General Assembly said about withdrawal from church membership under BCO 38-4?”
- “Find cases discussing the difference between an unconstitutional and a grossly unconstitutional proceeding.”
- “Trace RPR exceptions involving paedocommunion and explain how each was resolved.”
- “Has the Assembly considered session judicial commissions under BCO 15-2?”

## Useful refinements

- **Name the provision or case when you know it.** A concrete identifier sharply improves retrieval.
- **Ask for a sequence when history matters.** Later Assemblies may answer, reverse, ratify, or close an earlier matter.
- **Ask the AI to compare authority.** A judicial holding, CCB answer, RPR exception, and adopted study report do not perform the same function.
- **Verify the quotation.** Follow the supplied link and check the printed-page marker before relying on the answer.

For agents that prefer a compact site map, begin with [`llms.txt`](llms.txt). The combined catalogue pack is available as [`llms-full.txt`](llms-full.txt).
