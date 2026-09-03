---
layout: ask
permalink: /ask.html
title: Ask AI about the PCA General Assembly record and Constitution
description: A compact, source-disciplined research prompt for connecting PCA constitutional texts with General Assembly history.
---

# Ask AI about the PCA Constitution and history

This prompt pairs two complementary sources. The PCA Constitution Reader supplies the text of the Westminster Standards and Book of Church Order; the PCA General Assembly Records corpus supplies the cases, inquiries, overtures, RPR findings, study reports, and Assembly actions that interpret, apply, amend, or resolve that text.

## Copy the research prompt

Replace the final bracketed line with your question. Include a BCO or Westminster provision, case, presbytery, Assembly, or approximate year when you know one.

<div class="prompt-toolbar">
  <span>Source-disciplined PCA research prompt</span>
  <button type="button" id="copyPrompt">Copy prompt</button>
</div>

```text
Research the question below using both the PCA General Assembly Records corpus and the PCA Constitution Reader.

Open:
https://raymond-rishty.github.io/pca-ga/llms.txt
https://raymond-rishty.github.io/pca-constitution-reader/llms.txt
https://raymond-rishty.github.io/pca-constitution-reader/

Use the Constitution Reader for the exact Westminster Standards and BCO text; use the General Assembly corpus for historical actions, cases, inquiries, overtures, RPR findings, study reports, and Assembly minutes. When present BCO wording matters, check the official current BCO linked in the corpus map. If a provision is named, read it first, then search the historical record for interpretation, application, amendment, and later resolution, including predecessor numbers when relevant.

Treat indexes and summaries as finding aids. Verify material conclusions in the underlying record and distinguish source type and procedural status. For each material historical conclusion, provide a public HTML link and a printed-page citation such as “M50GA p.103”; cite constitutional text by book/provision and reader link. Derive Minutes citations from the underlying printed-page marker; minutes URL fragments and PDF pages are locators, not printed-page citations. Use a base URL for an extracted record unless its anchor is verified. Do not invent links, quotations, page numbers, outcomes, or authority.

For a negative result, say “Not found in this corpus,” briefly state the scope and terminology searched, and do not infer that the PCA never addressed the subject.

Answer with:
- Direct answer
- Evidence and chronology
- Authority and limits

QUESTION

[INSERT YOUR QUESTION HERE]
```

## Questions that work well

- “What has the General Assembly said about withdrawal from church membership under BCO 38-4, and how does that compare with the current text?”
- “Find cases discussing a confession or case handled without process under BCO 38-1.”
- “Trace an elder’s perpetual inactivity under BCO 17-3 and 34-10, including relevant parts of Chapter 24, inquiries, overtures, and Assembly actions.”
- “Trace RPR exceptions involving paedocommunion and explain how each was resolved.”

## Useful refinements

- Name the provision or case when you know it; search both the Constitution Reader and the historical corpus.
- Ask for a sequence when history matters. Later Assemblies may answer, reverse, ratify, or close an earlier matter.
- Ask the AI to compare authorities. A constitutional text, judicial holding, CCB answer, RPR exception, and adopted study report do not perform the same function.
- Follow each supplied link and check the printed-page marker before relying on the answer.

For a compact site map, begin with [llms.txt](llms.txt). The combined catalogue pack is available as [llms-full.txt](llms-full.txt).
