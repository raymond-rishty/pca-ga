# Federated catalogue and full-text search

The home-page search is a federated, static client-side search. One query runs against two
indexes without requiring an external search service, database, API key, or server-side query
endpoint:

- The compact `app/search_index.json` catalogue ranks structured records in the browser.
- Pagefind searches the rendered primary-source text and returns the best matching anchored
  passage from each document.

Use the **All**, **Catalogue**, and **Full text** controls to select both result groups or one of
them. Record-type filters apply to both indexes, and the query, filters, and scope are retained
in the URL.

## Search behavior

- Ordinary words are forgiving: punctuation, whitespace, capitalization, apostrophes, dashes,
  and accents are normalized. A record matching several words ranks above one matching only
  one word; the search remains useful when a researcher remembers only part of a phrase.
- Quoted text is an exact phrase. Every quoted phrase must occur in a searchable field.
- Recognized identifiers are exact lookups: `BCO 38-4`, `case 2022-23`, `overture 15`, and
  `CCB inquiry 12` (with common dash/spacing variations accepted). An exact identifier takes
  precedence over ordinary keyword matching.
- Results show which fields matched. Empty results explain whether the identifier, phrase,
  or keywords were not found and offer a narrower or broader next search.
- `q` and the selected `type` filters are kept in the URL, so a search can be copied and
  reopened with the same state.

## Indexed fields

Every record may contribute the following fields. Missing fields are allowed and never exclude
the record.

| Record type | Searchable fields |
| --- | --- |
| Judicial case | title, case identifiers, Assembly/year, parties/court, BCO references, topics, editorial synopsis, disposition, catalogue context |
| Constitutional inquiry | title, CCB inquiry identifier, Assembly/year, BCO references, answer/headnote, disposition, catalogue context |
| RPR exception | exception identifier, presbytery/title, Assembly/year, BCO references, topic text, status, catalogue context |
| Overture | title, overture identifier, Assembly/year, sponsoring body, BCO references, subject/topic, outcome |
| Study / position paper | title/topic, document identifier, Assembly/year, document kind |

## Full-text passage index

Pagefind runs after Jekyll and the corpus-linking build steps, indexing the final HTML under
`_site`. Shared navigation, search controls, and other page furniture are excluded; only marked
primary-source content is indexed. Results link to the highest-ranked heading or section when
the rendered document provides an anchor. The generated Pagefind files are included in the
GitHub Pages artifact and loaded only when a full-text search is requested.
