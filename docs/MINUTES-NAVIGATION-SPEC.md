# Navigation in the General Assembly Minutes

Implementation specification · PCA General Assembly Minutes · 19 November 2026

## Outcome and scope

A clerk opens a citation on a phone, identifies the Assembly and printed page, opens Contents, visits another section, and returns to the original reading position in one tap. A reader who arrived through search can also return directly to the filtered results after following a case into its source. Both journeys must work with the keyboard.

The first release adds orientation and direct navigation to Minutes volumes. The second applies a consistent location and source-link treatment to judicial cases, constitutional inquiries and CCB advice, overtures, RPR exceptions, and study papers. Work belongs in the Minutes repository. The Constitution Reader remains an external destination for reading constitutional text.

PR #229 has merged into main. Its Back action, result context, disclosure restoration, and browser regression tests are the baseline. Search, Browse, and My Research remain the global destinations. A volume outline belongs with its volume rather than in the site-wide menu. [Merged Back implementation](https://github.com/raymond-rishty/pca-ga/pull/229)

## Reader controls

| Control | Destination or effect |
| --- | --- |
| Back in the header | Traverse one prior in-site browser entry, including a deliberate jump within a volume. On direct entry, show the reader’s present location and available destinations. |
| Back to results | Reopen the originating query or catalogue with its filters, loaded results, and scroll position. Keep the existing previous/next result sequence. |
| Contents | Open this volume’s outline at the current section. Choosing an entry jumps within the volume. |
| Go to page | Find a printed folio or a physical PDF page in this volume. The chosen coordinate is explicit. |
| Read in the Minutes | Open the record’s cited passage in the HTML volume. Opening the archival PDF is a separately labeled action. |

## Release 1 · Volume navigator

### Reading surface

Render one compact sticky row immediately below the existing header on volume pages. Show the Assembly ordinal, year, and current page, for example **51st GA · 2024 · p. 808**. Include visible **Contents** and **Go to page** controls. At narrow widths allow a second line before truncating a control or obscuring the folio. Keep the title short on phones. The outline panel can show the full section path. Page-level Save, Cite, and Share remain available on the existing markers.

Use the top of the unobscured reading area to determine the current page. The last stationary page boundary at or above that line wins. Before the first boundary, show the volume identity alone. At the end, retain the last page. On initial deep links, resize, restored history, and font/layout changes, recalculate after layout settles. Use the actual combined sticky heights for anchor offsets. Check the existing sticky page markers and Back to top control for overlap.

### Contents

Use a labeled panel with a close button, keyboard-operable disclosures, and real links. On wide screens it can sit beside the text. On phones use a sheet with a scrollable body that fits the viewport. Both layouts expose the same outline. Open the current branch, mark the current section with accessible text, and scroll that entry into view. Keep other top-level branches collapsed initially. Preserve the author’s hierarchy, order, and duplicate titles. Give same-title siblings their page labels so readers can distinguish them.

Resolve the current section by the nearest *preceding physical start page*, independently of outline display order. On ties, prefer the deepest node in a single ancestry chain. Where unrelated sections start on the same page and the text lacks a finer verified anchor, mark their common parent if known, or identify the page alone. A section link may land at the start of the containing page. A row with no validated destination may group children but cannot trigger a jump. If the tree is empty, offer the existing static outline when available and keep page lookup usable.

### Go to page

Open a labeled form with **Printed page** and **PDF page** choices. Default to printed if the volume has usable folios, otherwise default to PDF. Printed input accepts text, including preserved nonnumeric folios. Trim surrounding whitespace and match stored folio labels without converting Roman numerals into Arabic numbers. PDF input accepts a positive whole number present in the volume’s page map.

| Lookup | Required behavior |
| --- | --- |
| Unique printed folio | Jump to its existing canonical printed anchor. |
| Repeated printed folio | List each occurrence in physical order with its PDF page and verified section name when available. Wait for a choice. |
| PDF page | Jump to the explicit PDF-page anchor. Show the corresponding printed folio when known. |
| Missing or invalid input | Keep the form open and retain the input. Explain the problem inline. Offer PDF lookup for a missing folio. |
| Physical page without a printed folio | Display **PDF p. N** in the row and use the PDF anchor for sharing. |
| Already at the chosen destination | Close the panel and focus the passage. Add no duplicate history entry. |

### History, focus, and ordinary links

Use normal anchor navigation for a confirmed jump. If JavaScript handles the jump, create exactly one browser entry and retain the canonical fragment. Keep modified clicks, copy-link, and open-in-new-tab behavior on real links. Ordinary scrolling updates the location label without writing history or changing the shared URL. Opening, expanding, typing in, or dismissing a panel adds no entry.

For a confirmed jump, dismiss the panel, bring the destination below the sticky row, and move keyboard focus to a meaningful destination label without triggering another scroll. Escape or Close returns focus to the invoking control and preserves the reading position. A mobile modal confines focus while open and prevents the reading surface from scrolling underneath. Desktop nonmodal controls follow normal tab order. Browser Back and Forward must restore the previous reading position even if the reader had scrolled beyond the incoming fragment before jumping. Prefer native scroll restoration. If a browser needs additional state, attach it to the individual history entry and merge with the state owned by #229. Preserve the search-return context across same-document jumps.

Keep the navigator outside the indexed primary text. Give controls visible focus states and touch targets of at least 44 CSS pixels where feasible. At 320 CSS pixels and 200% zoom, every action must remain reachable without horizontal page scrolling. Announce lookup errors and explicit jump destinations. Continual scroll updates must stay silent for screen readers. Honor reduced motion. Without JavaScript, retain readable volumes, stationary anchors, ordinary outline links, and source links.

## Data and build contract

Use the locator contract already implemented for the corpus. A physical page is identified by volume and 1-based PDF page. The printed folio is a separate label with provenance. Reuse the existing resolver, generated boundaries, and registered source-PDF links. Never derive the PDF number from a volume-wide offset. Preserve existing public fragments and the historical first-occurrence alias for repeated folios. New jumps to repeated folios use an occurrence-qualified printed anchor or an explicit PDF anchor. [Page anchor contract](MINUTES-PAGE-ANCHORS-PLAN.md) · [Locator implementation](../scripts/minutes_page_locators.py)

Use the generated page-marker dataset in the current volume for page lookup. Include stationary targets even when a page has no standalone content wrapper. Build the outline from the volume’s structured tree under `index/structure/`. Its nodes already contain type, label, title, children, and source page coordinates. Resolve each recorded PDF page against the volume’s actual page map. When the structure’s printed label disagrees with that physical destination, use the page map’s label and report the discrepancy for editorial review. Preserve an unlocated entry’s children. Do not calculate destinations by interpreting the numeric suffix of a legacy outline URL. [Example structure](../index/structure/ga51_2024.json) · [Page markup generator](../scripts/46_minutes_page_markup.py)

Extend the Gradle stage that generates volume page markers to emit a compact, versioned outline per volume, for example `assets/volume-outlines/ga51_2024.json`. Each file carries the volume ID and ordered nested nodes with a stable key within that edition, display label, physical page or null, and canonical fragment or null. Render plain text as text. Load only the current outline, on first opening Contents. Index page markers once per volume and use visibility observation or a bounded lookup for scroll tracking. Do not scan an entire thousand-page DOM on every scroll event. A failed outline fetch exposes a link to the static outline and a retry; page lookup continues from the local markers.

Declare the structure files, resolver, page markup, and generator as Gradle inputs and the generated outline files as outputs. Include them in the Pages artifact and both full and incremental build paths. Regeneration must be idempotent, remove obsolete outline artifacts, and respect the site base path. Validate volume identity, one-to-one PDF coordinates, uniqueness of emitted fragment IDs, and existence of every enabled outline target in its own rendered volume. A missing documentary locator is an editorial coverage condition. An emitted link with a missing target fails validation.

## Release 2 · Orientation on individual records

Use the shared layout and existing record metadata to display the record family, its human identifier when available, Assembly and year, and the primary Minutes source. A direct visitor should be able to open the family catalogue, the relevant volume, or the exact source passage. Desktop breadcrumbs can expose the full path. At phone widths keep essential location text and a labeled source link visible near the title. Reuse the existing sticky case treatment where a long record benefits from it. Avoid stacking a second sticky toolbar above a short record.

| Record family | Identity readers should see |
| --- | --- |
| Judicial case | Docket number and parties |
| Inquiry or CCB advice | Inquiry identifier or advice subject and its Assembly |
| Overture | Assembly and overture number, with its subject |
| RPR exception | Presbytery and the exception’s recorded identifier or citation |
| Study or position paper | Document title and kind, with the reporting Assembly when known |

Format a verified range as **Read in the Minutes, pp. 742–766** and land on the first cited page. Preserve multiple source passages when a record spans actions or Assemblies. Label each by its actual source. If only a physical page is known, say **Read in the Minutes, PDF p. N**. If only the volume is known, use **Open Assembly volume**. Without a verified source, omit the exact-page action. Reuse the existing PDF and record links, including their source-specific labels. [Source link conventions](source-pdf-links.md)

## Delivery and verification

1. **Volume navigation PR.** Implement marker lookup, validated outline generation, the responsive controls, accessible focus and history behavior, and the tests below. Primary integration points are the shared volume layout, the page-marker Gradle stage, scoped navigation JS/CSS, and the existing browser test workflow. The volume release can ship independently of record-header changes.
2. **Record orientation PR.** Apply the record patterns above. Cover at least one real example per family, a multi-source record, and an incomplete citation. Re-run the search-to-source and provision-to-case journeys from #229.
3. **Usability check.** Ask a clerk or commissioner to try the primary journey on a phone without coaching. Observe whether they identify the Assembly and page, discover Contents, open another section, return in one tap, and distinguish printed from PDF lookup. Record any intervention needed. Repeat the journey keyboard-only and spot-check the panel with VoiceOver. Report human testing separately from automated results.

| Acceptance fixture | Pass condition |
| --- | --- |
| Direct link to GA51 printed p. 808 | Identifies the 51st Assembly and p. 808 at PDF p. 815. Explicit PDF p. 808 identifies printed p. 801. |
| GA33 printed p. 300 | Offers the PDF p. 302 and p. 590 occurrences. Choosing the latter produces an unambiguous shareable destination that works in a fresh tab. |
| Missing, nonnumeric, or unmapped folio | Labels PDF-only pages explicitly, accepts an actual nonnumeric label where available, and reports an unknown input without moving. Include a small fixture if needed. |
| Direct citation on a phone | Open Contents, expand a branch, choose a section, and use Back once. The original passage is visible at the prior reading position. Forward revisits the section. |
| Passive scroll and cancelled jump | Current marker follows scrolling across page boundaries. Opening and closing either panel, or submitting an invalid page, leaves URL, history length, and reading position intact. |
| Search → record → Minutes → page jump | Back retraces the jump. Back to results restores query, filters, and loaded result position. A fresh tab has no inherited result trail. |
| Direct entry to each record family | Identify the record and Assembly where known, open the correct catalogue, and follow the source action to the labeled destination. |
| Keyboard, responsive layout, and degraded loading | Enter and Escape work, focus is visible and returns predictably, sticky UI leaves the target visible, and static outline links work if the outline payload fails. |

Run pure locator and outline tests against ordinary and pathological fixtures, browser tests against rendered HTML at phone and desktop widths, and the repository’s full validating build through `pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build-local.ps1`. Inspect affected pages at the local preview under `/pca-ga/`, verify the deployed base-path form of deep links, and review generated diffs before staging. The release is ready for review when the full build passes and the applicable acceptance journeys pass against its output.
