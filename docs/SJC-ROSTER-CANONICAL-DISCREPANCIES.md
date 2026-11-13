# SJC roster and canonical case identity review

This report collects known differences between docket numbers in the PCA
Historical Center's SJC roster and the canonical case IDs in
`judicial_cases.jsonl`. The roster is useful for discovering candidates and its
linked decision PDFs remain useful primary evidence. Its docket numbers and
captions are not treated as controlling when they conflict with the decision
record.

## Review status

There are 24 roster-to-canonical docket corrections already represented by
approved rules in `data/cases/overrides/case_identity_overrides.json`. I checked
each mapping against the docket designation and caption in the repository's
text extraction of the corresponding official General Assembly Minutes. The
printed docket and caption support the canonical ID in every case below, and
the linked case pages point to the corresponding official Minutes PDF pages.
The [published roster page](https://pcahistory.org/pca/sjc/1985-1994.html) does
not link individual decision PDFs for these 24 rows, so this check uses the
Minutes rather than separate SJC opinion PDFs.

The report also found two roster rows that appear to duplicate a case already
represented under a different roster number. They need identity review, but
are kept separate from the 24 established mappings because there is no
one-to-one correction rule for those rows yet.

## Known roster number corrections

`Roster ID` is the roster's listed number; `Canonical ID` is the catalogue
identity currently assigned by the approved correction rule. The linked case
page and cited source locations make each record easier to inspect. The last
column links to the official Minutes PDF used to verify the docket and caption.

| Roster ID | Canonical ID | Canonical caption | Case page | Minutes text checked | Review result |
|---|---|---|---|---|---|
| 1986-07 | 1986-08 | Dye et al. v. Missouri Presbytery | [case page](../cases/ga14_1986__case7.md) | `markdown/ga14_1986.md:3169, 4320, 6757` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 216](https://www.pcahistory.org/pca/ga/14th_pcaga_1986.pdf#page=216) |
| 1987-02 | 1986-06 | Carl W. Bogue et al. v. Presbytery of the Ascension | [case page](../cases/ga14_1986__case6.md) | `markdown/ga14_1986.md:3165, 5077; markdown/ga15_1987.md:3418, 4517` | Confirmed as 14th GA Case #6 and its 15th GA continuation: [14th Minutes PDF · p. 156](https://www.pcahistory.org/pca/ga/14th_pcaga_1986.pdf#page=156), [15th Minutes PDF · p. 141](https://www.pcahistory.org/pca/ga/15th_pcaga_1987.pdf#page=141) |
| 1988-03 | 1988-05 | Robert G. Rayburn et al. v. Missouri Presbytery | [case page](../cases/ga16_1988__case3.md) | `markdown/ga16_1988.md:3057, 5907, 7253` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 217](https://www.pcahistory.org/pca/ga/16th_pcaga_1988.pdf#page=217) |
| 1988-04 | 1988-07 | Robert Jamison v. Western Carolina Presbytery | [case page](../cases/ga16_1988__case4.md) | `markdown/ga16_1988.md:3068, 6033, 6749` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 202](https://www.pcahistory.org/pca/ga/16th_pcaga_1988.pdf#page=202) |
| 1988-05 | 1988-08 | John Neville v. Western Carolina Presbytery | [case page](../cases/ga16_1988__case5.md) | `markdown/ga16_1988.md:3072, 6033, 6899` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 205](https://www.pcahistory.org/pca/ga/16th_pcaga_1988.pdf#page=205) |
| 1988-06 | 1988-10 | James Serio et al. v. Palmetto Presbytery | [case page](../cases/ga16_1988__case6.md) | `markdown/ga16_1988.md:3080, 6062, 6511, 6517` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 195](https://www.pcahistory.org/pca/ga/16th_pcaga_1988.pdf#page=195) |
| 1989-01 | 1988-01 | McCready et al. v. Philadelphia Presbytery | [case page](../cases/ga17_1989__case1.md) | `markdown/ga16_1988.md:3041, 5761` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 210](https://www.pcahistory.org/pca/ga/17th_pcaga_1989.pdf#page=210) |
| 1989-04 | 1988-04 | TE Erwin Morrison v. Philadelphia Presbytery | [case page](../cases/ga17_1989__case2.md) | `markdown/ga16_1988.md:3053, 5761` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 229](https://www.pcahistory.org/pca/ga/17th_pcaga_1989.pdf#page=229) |
| 1989-06 | 1988-06 | TE John T. DeBardeleben v. Philadelphia Presbytery | [case page](../cases/ga17_1989__case3.md) | `markdown/ga16_1988.md:3061, 5761` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 211](https://www.pcahistory.org/pca/ga/17th_pcaga_1989.pdf#page=211) |
| 1989-09 | 1988-09 | Morrison et al. v. Philadelphia Presbytery | [case page](../cases/ga17_1989__case4.md) | `markdown/ga16_1988.md:3076, 5761` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 230](https://www.pcahistory.org/pca/ga/17th_pcaga_1989.pdf#page=230) |
| 1989-10 | 1989-01 | D. Stine v. Southern Florida Presbytery | [case page](../cases/ga17_1989__case5.md) | `markdown/ga17_1989.md:6703, 8987` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 234](https://www.pcahistory.org/pca/ga/17th_pcaga_1989.pdf#page=234) |
| 1989-11 | 1989-02 | Session of Grace PCA v. Covenant Presbytery | [case page](../cases/ga17_1989__case6.md) | `markdown/ga17_1989.md:6828, 9291` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 237](https://www.pcahistory.org/pca/ga/17th_pcaga_1989.pdf#page=237) |
| 1989-12 | 1990-01 | First Presbyterian Church of Rowlett v. North Texas Presbytery | [case page](../cases/ga18_1990__case1.md) | `markdown/ga17_1989.md:6871, 6925` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 164](https://www.pcahistory.org/pca/ga/18th_pcaga_1990.pdf#page=164) |
| 1991-01 | 1990-03 | Grace Covenant Presbyterian Church v. New River Presbytery | [case page](../cases/ga19_1991__1990-03.md) | `markdown/ga19_1991.md:12696, 12801` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 483](https://www.pcahistory.org/pca/ga/19th_pcaga_1991.pdf#page=483) |
| 1991-02 | 1990-04 | Chappell v. Eastern Carolina Presbytery | [case page](../cases/ga19_1991__1990-04.md) | `markdown/ga19_1991.md:12698, 13071` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 492](https://www.pcahistory.org/pca/ga/19th_pcaga_1991.pdf#page=492) |
| 1991-03 | 1990-04a | Marshall v. Eastern Carolina Presbytery | [case page](../cases/ga19_1991__1990-04a.md) | `markdown/ga19_1991.md:12700, 13662` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 513](https://www.pcahistory.org/pca/ga/19th_pcaga_1991.pdf#page=513) |
| 1991-04 | 1990-05 | Melton et al. v. Tennessee Valley Presbytery | [case page](../cases/ga19_1991__1990-05.md) | `markdown/ga19_1991.md:12702, 14157` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 532](https://www.pcahistory.org/pca/ga/19th_pcaga_1991.pdf#page=532) |
| 1991-05 | 1990-07 | Stringer v. Mississippi Valley Presbytery | [case page](../cases/ga19_1991__1990-07.md) | `markdown/ga19_1991.md:12704, 14265` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 537](https://www.pcahistory.org/pca/ga/19th_pcaga_1991.pdf#page=537) |
| 1991-07 | 1990-09 | Hathaway v. Grace Presbytery | [case page](../cases/ga19_1991__1990-09.md) | `markdown/ga19_1991.md:12708, 14918` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 569](https://www.pcahistory.org/pca/ga/19th_pcaga_1991.pdf#page=569) |
| 1991-08 | 1990-10 | Hathaway v. Grace Presbytery | [case page](../cases/ga19_1991__1990-10.md) | `markdown/ga19_1991.md:12710, 15274` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 582](https://www.pcahistory.org/pca/ga/19th_pcaga_1991.pdf#page=582) |
| 1992-02 | 1991-02 | Nickoley and Stephens v. Southwest Presbytery | [case page](../cases/ga20_1992__1991-02.md) | `markdown/ga20_1992.md:4752, 4862` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 144](https://www.pcahistory.org/pca/ga/20th_pcaga_1992.pdf#page=144) |
| 1992-03 | 1991-03 | Daniel R. Morse v. Covenant Presbytery | [case page](../cases/ga20_1992__1991-03.md) | `markdown/ga20_1992.md:4754, 5186` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 156](https://www.pcahistory.org/pca/ga/20th_pcaga_1992.pdf#page=156) |
| 1992-04 | 1991-04 | Robert D. Hopper v. James River Presbytery | [case page](../cases/ga20_1992__1991-04.md) | `markdown/ga20_1992.md:4756, 5385` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 162](https://www.pcahistory.org/pca/ga/20th_pcaga_1992.pdf#page=162) |
| 1992-05 | 1991-05 | Herman Gunter III et al. v. Central Florida Presbytery | [case page](../cases/ga20_1992__1991-05.md) | `markdown/ga20_1992.md:4758, 6364` | Confirmed in official Minutes text; linked source: [Minutes PDF · p. 199](https://www.pcahistory.org/pca/ga/20th_pcaga_1992.pdf#page=199) |

## Rows requiring separate identity review

These are duplicate-number rows outside the 24 corrected mappings. The current
evidence establishes a likely duplicate relationship, but I did not mark these
rows as corrected without resolving whether the roster intended separate
decisions.

| Roster row | Current canonical record | Why it is flagged | Review |
|---|---|---|---|
| 1990-01 — Session of First PCA, Rowlett, TX v. North Texas Presbytery | The catalogue has this case as `1990-01`, sourced through roster ID `1989-12`. | The roster contains a second row for the same caption under `1990-01`; determine whether it is a duplicate or points to distinct decision text. | [ ] |
| 2012-03 — Tarter v. Evangel Presbytery | The catalogue has this case as `2012-03`, sourced through roster ID `2012-13`; it now carries the PDF URL from this `2012-03` row. | The build merges both rows into this canonical record. The PDF link is preserved, but its contents have not been independently checked here. | [ ] |

## Method and limits

- Compared the saved parsed roster at `data/cases/sources/sjc_official/roster.jsonl`, the generated canonical catalogue at `data/cases/records/judicial_cases.jsonl`, and the approved identity rules in `data/cases/overrides/case_identity_overrides.json`.
- Included only rules that map a roster ID to a different canonical ID and have a corresponding roster entry. One additional override (`1980-05` to `1980-04`) has no matching parsed roster row, so it is not counted as a roster disagreement here.
- Kept same-number caption corrections, roster-only duplicate rows, and other coverage gaps out of the 24 mapped differences. The two duplicate rows above are surfaced separately.
- The review confirms these 24 canonical docket mappings from the Assembly Minutes; it does not establish that every roster row or every catalogue field is accurate. Individual SJC decision PDFs were not linked for these rows on the roster page.
