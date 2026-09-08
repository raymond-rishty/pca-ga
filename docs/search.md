# Catalogue search

The home-page search is a static, client-side catalogue search. It loads the compact
`app/search_index.json` file and ranks matching records in the browser, so it does not require
an external search service, database, API key, or server-side query endpoint.

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

The index is intentionally a catalogue index rather than a full-text Minutes index. For a
passage-level search across every page, the next useful step would be a generated static
full-text index (for example Pagefind or a small SQLite/FTS build), while keeping the same
record-level catalogue search as the first pass.
