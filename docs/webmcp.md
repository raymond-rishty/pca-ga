# WebMCP browser tools

This site implements the [webmachinelearning WebMCP specification](https://webmachinelearning.github.io/webmcp/) using `document.modelContext.registerTool()`. Tools register automatically when the page loads in a browser exposing that API. They are marked with `annotations.readOnlyHint: true`.

Use a compatible browser agent while the site is open over HTTPS (or localhost for development). There is no site connection widget, token exchange, API key, npm client, or localhost bridge. A conventional desktop MCP client does not automatically discover these browser tools.

WebMCP is evolving and browser support varies. See upstream [implementation status](https://github.com/webmachinelearning/webmcp/blob/main/implementation-status.md) for current support and experimental setup. This integration targets the current document API; implementations exposing only the earlier `navigator.modelContext` API need updating. Browsers without `document.modelContext.registerTool` keep the normal reading and search experience. Registration failures are caught and reported in the browser console.

Start with **`prepare_pca_research({question})`**, the primary entry point. It returns the Ask research prompt with the supplied question. The browser agent follows those instructions, uses search and reading tools, and verifies sources before answering. Call it once per question; the returned prompt continues the workflow and must not send the agent back to the entry tool. This tool supplies a research brief; it does not call an AI model or produce an answer. The question is inserted locally and is not sent with the prompt fetch.

The Assembly Ask page and public `assets/pca-research-prompt.txt` are rendered from `_includes/pca-research-prompt.txt`. Both sites load that published text on demand so the instructions stay consistent. The Reader needs network access to the Assembly site to load it. Failed loads can be retried; the Ask page remains a human-readable fallback. `llms.txt` is an optional map for finding more sources, not a required step after the prompt.

`search_assembly_records` searches the same catalogues and constitutional provision index as the homepage. It accepts a nonempty `query` and an optional `limit` (1–50, default 10). Results include public source URLs. `read_current_record` reads the public article on the current page; the homepage and personal research workspace are excluded.

Search retrieves catalogue records, not every passage in the Minutes. Follow the returned source links for verbatim evidence. Distinguish constitutional text, judicial holdings, CCB advice, RPR exceptions, and Assembly actions when drawing conclusions. Personal research collections are not exposed.

The integration is in `assets/webmcp-integration.js` and loads through both the shared layout and the Ask layout. No external WebMCP JavaScript library is required.
