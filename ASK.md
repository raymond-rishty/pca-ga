---
layout: ask
permalink: /ask.html
title: Ask AI about the PCA General Assembly record
description: A source-disciplined research prompt for finding and citing the PCA Minutes of the General Assembly.
---

# Ask AI about the PCA Constitution and history

Use this prompt with any AI assistant that can browse the web. It first points the assistant to `llms.txt`, the compact map of the corpus, then requires it to use the relevant indexes, open the verbatim minutes, and distinguish different kinds of General Assembly records before drawing a conclusion.

## Copy the research prompt

Replace the final bracketed line with your question. You can also give the AI a known BCO provision, case number, presbytery, Assembly, or approximate year.

<div class="prompt-toolbar">
  <span>PCA source-checking research prompt</span>
  <button type="button" id="copyPrompt">Copy prompt</button>
</div>

```text
Research the question below using both the PCA General Assembly Records corpus and the PCA Constitution Reader.

Open:
https://raymond-rishty.github.io/pca-ga/llms.txt
https://raymond-rishty.github.io/pca-constitution-reader/llms.txt
https://raymond-rishty.github.io/pca-constitution-reader/
https://raymond-rishty.github.io/pca-ga/api/bco/index.json

Use the Constitution Reader for the exact Westminster Standards and BCO text; use the General Assembly corpus for historical actions, cases, inquiries, overtures, RPR findings, study reports, and Assembly minutes. For present BCO wording, use the official current BCO linked in the corpus map and keep it separate from historical Minutes evidence. If a provision is named, read it first, then search the historical record for interpretation, application, amendment, and later resolution, including predecessor numbers when relevant.

When a BCO provision is named or identified, use the BCO authority manifest to retrieve the provision-scoped JSON record before scanning broad catalogues. Treat the manifest as a finding aid: select relevant artifacts from it, open the linked source records, and cite those underlying records rather than the manifest itself.

Use the narrowest relevant catalogue first. Treat indexes and llms-full.txt as finding aids, but do not load the full pack unless the question needs broader discovery. Open the underlying extracted record or page-anchored Minutes entry before citing it. Before finalizing each material historical citation, verify the linked page's title or record identifier and disposition, then verify the claim in the cited passage. For a Minutes link, read its PAGE marker and derive the printed citation in the form M<GA>GA p.<page> from printed_page; keep URL fragments and PDF-page numbers as locators only. Use an external PDF only when the corpus record is unavailable or unclear. Cite constitutional text by book/provision and reader link. If any check fails, omit the citation or label the item unverified. State the source type and do not generalize beyond what the source supports.

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
