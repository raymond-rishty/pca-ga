---
layout: ask
permalink: /ask.html
title: Ask AI about the PCA Constitution and General Assembly record
description: A research prompt for finding applicable BCO text and checking answers against the PCA Minutes of the General Assembly.
---

# Ask AI about the PCA Constitution and history

Use this prompt with an AI assistant that can retrieve web sources. It routes a provision, topic, or known case to the relevant constitutional text and Minutes records, then asks the assistant to verify what those sources support.

The Minutes corpus covers GA1–GA52 (1973–2025); the RPR catalogue begins at GA18 (1990). The current BCO may include later amendments. GA53 overture research is available separately, but does not extend the Minutes coverage.

## Copy the research prompt

Replace the final bracketed line with your question. Include a known provision, case number, presbytery, Assembly, or year. Say whether you want the current rule, the rule at a particular date, or its interpretive history.

<div class="prompt-toolbar">
  <span>PCA source-checking research prompt</span>
  <button type="button" id="copyPrompt">Copy prompt</button>
</div>

```text
Research my question using the PCA constitutional text and General Assembly records. Begin with this retrieval guide:
https://raymond-rishty.github.io/pca-ga/llms.txt

Choose the shortest applicable route:
1. BCO or Westminster wording: for BCO, fetch the compact chapter JSON at https://raymond-rishty.github.io/pca-ga/assets/constitution/chapters/<chapter>.json and read the requested section from `sections`; use https://raymond-rishty.github.io/pca-ga/assets/constitution/bco-index.json to locate available chapters and sections. Consult the full content/bco.js file listed at https://raymond-rishty.github.io/pca-constitution-reader/llms.txt only when chapter JSON omits needed introductory or structural material. Fetch the separate WCF, WLC, or WSC content file listed there only when that book is needed. Treat the Constitution Reader as the verified source for current BCO wording, identify the edition it displays, and link directly to the requested provision in the reader. Do not fetch a PDF when the machine-readable text supplies the needed wording. Use a PDF only to resolve a discrepancy, verify formatting or pagination, or retrieve text unavailable in those sources. A wording-only question can stop with verified text. For interpretation or application, also check the Minutes evidence below.
2. Known BCO provision: fetch its manifest directly, e.g. https://raymond-rishty.github.io/pca-ga/api/bco/38-4.json for BCO 38-4. For missing or more specific provisions, use api/bco/index.json to find exact, parent, and related entries. Chapter and section manifests are not rollups of all subsections. Select relevant artifacts and read their source records using url or raw_url.
3. Known case, presbytery, overture, or topic: use the guide's matching catalogue. For a topic without a provision, search distinctive terms and synonyms to identify the applicable text and records; include STUDIES for doctrinal or denominational-position questions.

Manifests and catalogues are finding aids. Provision tags are not exhaustive, and a citation may occur in a party's argument or dissent. Search relevant catalogues by topic as well as provision; manifests omit studies and untagged records. Follow later action, related cases, RPR responses, and an overture's referenced answer or amendment ratification when they could affect the conclusion. For historical wording, check the text then in force and date-specific predecessor numbers; renumbering data may be partial. Expand to volume outlines and full Minutes when catalogue evidence is insufficient. Use llms-full.txt only as an optional combined-catalogue fallback; it is not the full Minutes or every catalogue.

Before citing a historical claim, verify the record's identity, the supporting passage, who said it, and the actual disposition. When extracted metadata or a headnote conflicts with the original Minutes report, use the original report's heading and passage and briefly identify any material discrepancy. Distinguish judicial judgments from arguments/dissents, CCB non-binding advice, RPR exceptions and responses, proposals, adopted Assembly actions, and study-report reception or adoption. Do not treat an index summary or authority_weight as the source's authority. Separate what a source states from your inference. If the question requests multiple categories, periods, procedural steps, or record types, address each requested item separately with a verified source or state that none was found.

Cite the underlying published .html record with its case/item identifier and verified Minutes page. Include a clickable link to every underlying source used for a material claim; do not link only to a manifest, catalogue, search result, or machine-readable asset. An extracted record may combine excerpts from different Minutes pages: verify the printed page and link for the particular excerpt being cited, rather than carrying a nearby PAGE marker across excerpts. Read the PAGE comment in raw Markdown if necessary: ga and printed_page give M<GA>GA p.<page>. URL fragments and pdf_page are locators; never infer printed pagination from them. Copy an existing anchor or use the record's base URL. If printed_page is missing, label the available locator and the pagination limit. For every constitutional provision cited, link directly to its reader-facing route (for example, https://raymond-rishty.github.io/pca-constitution-reader/#bco/38-4 or https://raymond-rishty.github.io/pca-constitution-reader/#wlc/Q.135). Read corpus Markdown first, and use a source PDF only when OCR, layout, wording, or pagination remains uncertain.

Give the direct answer first, followed by the strongest relevant evidence, chronology where needed, and material limits. Keep the answer proportional to the question. State the edition/date and historical scope relied on. For a negative result, say "Not found in this corpus" and specify catalogues, years, provision variants, and topic terms searched. Inaccessible or truncated sources are search limits, not negative findings. Do not infer that the PCA never addressed the subject or that coverage through 2025 establishes the current rule.

QUESTION

[INSERT YOUR QUESTION HERE]
```

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
