# Provision Reference Assessment

The generated provision catalogue joins current constitutional text to indexed PCA records. A saved assessment classifies the relationship between one record and one provision. It does not replace editorial review: `relevance_status` stays `unreviewed` until an editor reviews the connection.

## Coverage

The current saved pass covers 11,481 provision-to-record links: 2,993 judicial case links, 6,871 RPR exception links, 655 overture links, 542 CCB advice links, and 420 constitutional inquiry links. The build checks that assessment inputs match the current catalogue sources before applying them.

The repository retains detailed classification and source lineage for audit. Those internal fields are not deployed in the public API. Pages and API responses use reader-facing groups generated from the same catalogue.

## Reader-facing groups

- **Discusses this provision** contains a substantive treatment, such as an application in a majority opinion, an exception that addresses the provision, or a proposed change to it.
- **Cites this provision** contains a reference that materially frames an issue or response without being the main subject of the record.
- **Other discussion in the case** holds relevant judicial discussion outside the majority opinion. It may come from a separate opinion, party argument, or background discussion.
- **Other mentions** contains clearly incidental references.
- **References to review** contains unclear or mismatched links, links with incomplete source support, and links that have not yet been reviewed.

These groups affect display order only. Every indexed link remains in the catalogue and public provision API. Readers should follow the cited passage before relying on a connection.

## Source coverage limits

The RPR citation parser found 619 direct-text candidate occurrences. All mapped either to a supported relationship or to `unmatched_relationships`. Two unmatched provisions appeared four times: WCF 22.8 in Covenant 018's response text (the indexed exception is WCF 21.8), and WCF 107–109 in Heritage 045 (which currently normalizes to WCF 7.10). They were not added to supported provision pages. This audit checks the parser's candidates; it does not establish that every possible reference was found.

WLC Q.119 has four indexed RPR links, including Arizona 018 and Korean Central 121, as well as Philadelphia 046 and Metropolitan New York 041.
