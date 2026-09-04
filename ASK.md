---
layout: ask
permalink: /ask.html
title: Ask AI about the PCA General Assembly record
description: A research prompt for finding, checking, and citing the PCA Minutes of the General Assembly.
---

# Ask AI about the PCA Constitution and history

Use this prompt with any AI assistant that can browse the web. It directs the assistant to `llms.txt`, the compact map of the corpus, and requires it to use the relevant indexes, open the linked minutes, and distinguish among General Assembly record types before drawing a conclusion.

## Copy the research prompt

Replace the final bracketed line with your question. You can also give the AI a known BCO provision, case number, presbytery, Assembly, or approximate year.

<div class="prompt-toolbar">
  <span>PCA source-checking research prompt</span>
  <button type="button" id="copyPrompt">Copy prompt</button>
</div>

```text
Research the question below using both the PCA General Assembly Records corpus and the PCA Constitution.

Open:
https://raymond-rishty.github.io/pca-ga/llms.txt
https://raymond-rishty.github.io/pca-constitution-reader/llms.txt
https://raymond-rishty.github.io/pca-constitution-reader/
https://raymond-rishty.github.io/pca-ga/api/bco/index.json

Use the Constitution Reader for the exact Westminster Standards and BCO text; use the General Assembly corpus for historical actions, cases, inquiries, overtures, RPR findings, study reports, and Assembly minutes. For present BCO wording, use the official current BCO linked in the corpus map and keep it separate from historical Minutes evidence. If a provision is named, read it first, then search the historical record for interpretation, application, amendment, and later resolution, including predecessor numbers when relevant.

When a BCO provision is named or identified, use the BCO authority manifest to retrieve the provision-scoped JSON record before scanning broad catalogues. Treat the manifest as a finding aid: select relevant artifacts from it, open the linked source records, and cite those underlying records rather than the manifest itself.

Use the narrowest relevant catalogue first. Treat indexes as finding aids. Use llms-full.txt only when no provision manifest or narrower catalogue applies, when the question spans several catalogues, or when the narrower links do not resolve. Search it for candidate records, then open and cite the underlying records rather than the pack itself. Before finalizing each material historical citation, verify the linked page's title or record identifier and disposition, then verify the claim in the cited passage. For a Minutes link, read its PAGE marker and derive the printed citation in the form M<GA>GA p.<page> from printed_page; keep URL fragments and PDF-page numbers as locators only. Use an external PDF only when the corpus record is unavailable or unclear. Cite constitutional text by book/provision and reader link. If any check fails, omit the citation or label the item unverified. State the source type and do not generalize beyond what the source supports.

For a negative result, say “Not found in this corpus,” briefly state the scope and terminology searched, and do not infer that the PCA never addressed the subject.
Answer with:
- Direct answer
- Evidence and chronology
- Authority and limits

QUESTION

[INSERT YOUR QUESTION HERE]
```

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
