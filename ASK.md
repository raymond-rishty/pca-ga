---
layout: ask
permalink: /ask.html
title: Ask AI about the PCA Constitution and General Assembly record
description: A research prompt for finding applicable BCO text and checking answers against the PCA Minutes of the General Assembly.
---

# Ask AI about the PCA Constitution and history

Use this prompt with an AI assistant that can retrieve web sources. It routes a provision, topic, or known case to the relevant constitutional text and Minutes records, then asks the assistant to verify what those sources support.

The Minutes corpus covers GA1–GA52 (1973–2025); the RPR catalogue begins at GA18 (1990). The current BCO may include later amendments. GA53 overture research is available separately, but does not extend the Minutes coverage.

## Ask through a browser agent

If your browser agent supports WebMCP, give it your question and ask it to start with `prepare_pca_research`. This is the primary tool on the Ask page, the Assembly site, and the Constitution Reader. It returns the research prompt with your question filled in; the agent then retrieves evidence and answers with citations. It does not run an AI model or produce an answer by itself.

The tool and the copyable prompt below use the same instructions. Assistants without WebMCP can still use the copyable prompt and `llms.txt`.

## Copy the research prompt

Replace the final bracketed line with your question. Include a known provision, case number, presbytery, Assembly, or year. Say whether you want the current rule, the rule at a particular date, or its interpretive history.

<div class="prompt-toolbar">
  <span>PCA source-checking research prompt</span>
  <button type="button" id="copyPrompt">Copy prompt</button>
</div>

```text
{% include pca-research-prompt.txt %}
```

When reading this page as Markdown on GitHub, open the [published plain-text prompt](https://raymond-rishty.github.io/pca-ga/assets/pca-research-prompt.txt) to copy the expanded instructions.

## Questions that work well

- “What does the current BCO say about withdrawal from church membership under BCO 38-4, and which cases or inquiries help explain its application?”
- “Find cases discussing the difference between an unconstitutional and a grossly unconstitutional proceeding. Identify the court's reasoning and any later action.”
- “Trace RPR exceptions involving paedocommunion and explain how each was resolved.”
- “Has the Assembly considered session judicial commissions under BCO 15-2? Distinguish the proposals, advice, and adopted actions.”

## Useful refinements

- **Name the provision or case when you know it.** A concrete identifier allows direct retrieval.
- **Give the date that matters.** Historical provision numbers and wording can differ from the current BCO.
- **Ask for the disposition.** A report's presence in the Minutes does not establish that its recommendations were adopted.
- **Check the citation.** Follow the source link and verify the passage and printed page before relying on the answer.

The agent retrieval guide is [`llms.txt`](llms.txt). The optional [`llms-full.txt`](llms-full.txt) pack combines selected catalogues for broader discovery.
