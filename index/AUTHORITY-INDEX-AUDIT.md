# Authority index audit

Catalogue input fingerprint: `b03938b466f6e2399ef9f5d8b29f442d2b595b98602df319fc7d88f438067d4b`.

The catalogue contains 1172 provisions, 12439 relationships, 16105 evidence occurrences, and 97 unmatched source references.

Relationship kinds describe why a record is linked. Evidence basis describes the source of that link. Match confidence describes extraction confidence. Reader scope labels the relationship in the Constitution Reader. These fields do not describe legal force.

The Reader includes indexed relationships for its supported record types across all scopes. Primary, contextual, and candidate links remain distinguishable in each record; scope describes the evidence relationship and is not a legal-authority ranking.

## Relationships by record type

| Record type | Relationships | Reader included |
|-------------|--------------:|----------------:|
| CCB advice | 542 | 542 |
| Constitutional inquiry | 420 | 420 |
| Judicial case | 3260 | 3260 |
| Overture | 1330 | 1330 |
| RPR exception | 6887 | 6887 |

Reader-included relationships by scope:

| Record type | Scope | Count |
|-------------|-------|------:|
| CCB advice | `contextual` | 542 |
| Constitutional inquiry | `primary` | 420 |
| Judicial case | `primary` | 3260 |
| Overture | `candidate` | 1234 |
| Overture | `primary` | 96 |
| RPR exception | `candidate` | 136 |
| RPR exception | `contextual` | 6751 |

### Relationships by relationship kind

| Value | Count |
|-------|------:|
| `body_mention` | 203 |
| `exception_target` | 224 |
| `explicit_citation` | 3448 |
| `proposal_target` | 643 |
| `structured_case_reference` | 823 |
| `structured_exception_tag` | 6711 |
| `structured_provision_tag` | 962 |

### Relationships by evidence basis

| Value | Count |
|-------|------:|
| `direct_text` | 3849 |
| `overture_action_target` | 643 |
| `structured_case_metadata` | 823 |
| `structured_provision_tag` | 7673 |
| `title_subject_reference` | 15 |

### Relationships by match confidence

| Value | Count |
|-------|------:|
| `high` | 4259 |
| `medium` | 8180 |

### Relationships by reader scope

| Value | Count |
|-------|------:|
| `candidate` | 1370 |
| `contextual` | 7293 |
| `primary` | 3776 |

### Relationships by match method

| Value | Count |
|-------|------:|
| `case_provision_index:case_markdown_text` | 936 |
| `case_provision_index:case_markdown_text,cases.jsonl:bco_cited_as,cases.jsonl:bco_cited_current` | 279 |
| `case_provision_index:case_markdown_text,cases.jsonl:bco_cited_as,cases.jsonl:bco_cited_current,judicial_cases.jsonl:bco_provisions` | 1335 |
| `case_provision_index:case_markdown_text,cases.jsonl:bco_cited_as,judicial_cases.jsonl:bco_provisions` | 6 |
| `case_provision_index:case_markdown_text,judicial_cases.jsonl:bco_provisions` | 39 |
| `case_provision_index:cases.jsonl:bco_cited_as,cases.jsonl:bco_cited_current` | 123 |
| `case_provision_index:cases.jsonl:bco_cited_as,cases.jsonl:bco_cited_current,judicial_cases.jsonl:bco_provisions` | 643 |
| `case_provision_index:cases.jsonl:bco_cited_as,judicial_cases.jsonl:bco_provisions` | 3 |
| `case_provision_index:cases.jsonl:bco_cited_current` | 9 |
| `case_provision_index:judicial_cases.jsonl:bco_provisions` | 66 |
| `disposition_bco` | 152 |
| `disposition_bco,title_subject` | 495 |
| `index/inquiries_search.json:provisions` | 962 |
| `index/rpr_search.json:provisions` | 6711 |
| `overture_body_explicit_reference_match` | 920 |
| `rpr_markdown_line:100` | 1 |
| `rpr_markdown_line:104` | 1 |
| `rpr_markdown_line:105` | 2 |
| `rpr_markdown_line:106` | 1 |
| `rpr_markdown_line:11` | 32 |
| `rpr_markdown_line:114` | 1 |
| `rpr_markdown_line:116` | 2 |
| `rpr_markdown_line:121` | 1 |
| `rpr_markdown_line:122` | 1 |
| `rpr_markdown_line:127` | 5 |
| `rpr_markdown_line:13` | 21 |
| `rpr_markdown_line:134` | 1 |
| `rpr_markdown_line:137` | 2 |
| `rpr_markdown_line:144` | 1 |
| `rpr_markdown_line:15` | 32 |
| `rpr_markdown_line:156` | 1 |
| `rpr_markdown_line:160` | 1 |
| `rpr_markdown_line:161` | 1 |
| `rpr_markdown_line:162` | 1 |
| `rpr_markdown_line:170` | 1 |
| `rpr_markdown_line:18` | 16 |
| `rpr_markdown_line:20` | 17 |
| `rpr_markdown_line:22` | 16 |
| `rpr_markdown_line:24` | 103 |
| `rpr_markdown_line:25` | 11 |
| `rpr_markdown_line:26` | 8 |
| `rpr_markdown_line:27` | 13 |
| `rpr_markdown_line:29` | 14 |
| `rpr_markdown_line:30` | 4 |
| `rpr_markdown_line:31` | 81 |
| `rpr_markdown_line:32` | 7 |
| `rpr_markdown_line:33` | 1 |
| `rpr_markdown_line:34` | 9 |
| `rpr_markdown_line:35` | 2 |
| `rpr_markdown_line:36` | 19 |
| `rpr_markdown_line:37` | 21 |
| `rpr_markdown_line:38` | 27 |
| `rpr_markdown_line:39` | 6 |
| `rpr_markdown_line:40` | 5 |
| `rpr_markdown_line:41` | 9 |
| `rpr_markdown_line:42` | 11 |
| `rpr_markdown_line:43` | 12 |
| `rpr_markdown_line:44` | 7 |
| `rpr_markdown_line:45` | 14 |
| `rpr_markdown_line:46` | 1 |
| `rpr_markdown_line:48` | 3 |
| `rpr_markdown_line:49` | 2 |
| `rpr_markdown_line:50` | 4 |
| `rpr_markdown_line:51` | 3 |
| `rpr_markdown_line:52` | 6 |
| `rpr_markdown_line:53` | 3 |
| `rpr_markdown_line:54` | 5 |
| `rpr_markdown_line:55` | 1 |
| `rpr_markdown_line:56` | 1 |
| `rpr_markdown_line:57` | 5 |
| `rpr_markdown_line:58` | 5 |
| `rpr_markdown_line:59` | 2 |
| `rpr_markdown_line:60` | 1 |
| `rpr_markdown_line:61` | 2 |
| `rpr_markdown_line:62` | 5 |
| `rpr_markdown_line:63` | 4 |
| `rpr_markdown_line:64` | 2 |
| `rpr_markdown_line:65` | 1 |
| `rpr_markdown_line:66` | 6 |
| `rpr_markdown_line:67` | 4 |
| `rpr_markdown_line:68` | 3 |
| `rpr_markdown_line:69` | 2 |
| `rpr_markdown_line:70` | 2 |
| `rpr_markdown_line:71` | 1 |
| `rpr_markdown_line:72` | 1 |
| `rpr_markdown_line:73` | 1 |
| `rpr_markdown_line:74` | 2 |
| `rpr_markdown_line:75` | 1 |
| `rpr_markdown_line:78` | 1 |
| `rpr_markdown_line:79` | 3 |
| `rpr_markdown_line:80` | 2 |
| `rpr_markdown_line:81` | 2 |
| `rpr_markdown_line:85` | 2 |
| `rpr_markdown_line:86` | 1 |
| `rpr_markdown_line:91` | 1 |
| `rpr_markdown_line:92` | 3 |
| `rpr_markdown_line:94` | 1 |
| `rpr_markdown_line:95` | 1 |
| `rpr_markdown_line:96` | 1 |
| `rpr_markdown_line:97` | 1 |
| `rpr_markdown_line:98` | 2 |
| `rpr_markdown_line:99` | 6 |
| `title_subject` | 15 |

### Evidence occurrences by relationship kind

| Value | Count |
|-------|------:|
| `body_mention` | 366 |
| `exception_target` | 284 |
| `explicit_citation` | 6229 |
| `proposal_target` | 709 |
| `structured_case_reference` | 844 |
| `structured_exception_tag` | 6711 |
| `structured_provision_tag` | 962 |

### Evidence occurrences by evidence basis

| Value | Count |
|-------|------:|
| `direct_text` | 6879 |
| `overture_action_target` | 694 |
| `structured_case_metadata` | 844 |
| `structured_provision_tag` | 7673 |
| `title_subject_reference` | 15 |

### Evidence occurrences by match confidence

| Value | Count |
|-------|------:|
| `high` | 7588 |
| `medium` | 8517 |

### Evidence occurrences by reader scope

| Value | Count |
|-------|------:|
| `candidate` | 2384 |
| `contextual` | 7537 |
| `primary` | 6184 |

## Unmatched source references

| Record type | Count |
|-------------|------:|
| CCB advice | 14 |
| Constitutional inquiry | 3 |
| Judicial case | 16 |
| Overture | 45 |
| RPR exception | 19 |

| Provision | Record type | Record ID | Evidence | Confidence | Scope | Source |
|-----------|-------------|-----------|----------|------------|-------|--------|
| BCO 10-18 | Judicial case | `case:cases/ga36_2008__2007-08.md` | `structured_case_metadata` | `medium` | `primary` | [Jones v. Louisiana](../cases/ga36_2008__2007-08.md) |
| BCO 11-36 | Overture | `overture:ga11_1983:18` | `direct_text` | `high` | `candidate` | [Divide Calvary Presbytery into Two Presbyteries](../markdown/ga11_1983.md#ga11-p56) |
| BCO 13-19.b | RPR exception | `rpr_exception:rpr/exc/korean-eastern__038.html` | `structured_provision_tag` | `medium` | `contextual` | [Korean Eastern: BCO 13-19b. No record of Presbytery reviewing minutes of church sessions.](../rpr/exc/korean-eastern__038.html) |
| BCO 14-46 | Overture | `overture:ga19_1991:5` | `direct_text` | `high` | `candidate` | [Amend BCO 15-4 to Permit General Assembly to Adjudicate Cases Directly](../markdown/ga19_1991.md#ga19-p163) |
| BCO 14-46 | Overture | `overture:ga20_1992:30` | `direct_text` | `high` | `candidate` | [Amend BCO 15-4 to Permit GA to Adjudicate](../markdown/ga20_1992.md#ga20-p116) |
| BCO 14-71 | Constitutional inquiry | `inquiry:inquiries/ga15_1987__ci01.md` | `structured_provision_tag` | `medium` | `primary` | [Informal versus formal admonition and due-process requirements under BCO 27-5](../inquiries/ga15_1987__ci01.md) |
| BCO 14-9.b | RPR exception | `rpr_exception:rpr/exc/nashville__064.html` | `structured_provision_tag` | `medium` | `contextual` | [Nashville: No record of Presbytery action on review of Session records.](../rpr/exc/nashville__064.html) |
| BCO 15-15 | Constitutional inquiry | `inquiry:inquiries/ga20_1992__ci02.md` | `structured_provision_tag` | `medium` | `primary` | [SJC authority to issue decisions contradicting prior General Assembly actions](../inquiries/ga20_1992__ci02.md) |
| BCO 18-19 | RPR exception | `rpr_exception:rpr/exc/rio-grande__011.html` | `structured_provision_tag` | `medium` | `contextual` | [Rio Grande: No record of candidate coming under care, licensure or ordination exams, or internship.](../rpr/exc/rio-grande__011.html) |
| BCO 18-19 | RPR exception | `rpr_exception:rpr/exc/rio-grande__027.html` | `structured_provision_tag` | `medium` | `contextual` | [Rio Grande: No record of candidate coming under care, licensure or ordination exams, or internship.](../rpr/exc/rio-grande__027.html) |
| BCO 18-22 | RPR exception | `rpr_exception:rpr/exc/new-river__043.html` | `structured_provision_tag` | `medium` | `contextual` | [New River: No motion to receive men as candidates under care. Exception : October 25, 2014 ( BCO 13-7](../rpr/exc/new-river__043.html) |
| BCO 21-12 | CCB advice | `ccb_advice:inquiries/ga52_2025__ci19.md` | `structured_provision_tag` | `medium` | `contextual` | [20-1](../inquiries/ga52_2025__ci19.md) |
| BCO 21-12 | Overture | `overture:ga52_2025:30` | `direct_text` | `high` | `candidate` | [Amend BCO 8-4, 20-1, 21-1, 21-12, and 23-1 re Calling and Dissolution of TE Relationships for Needful Works](../markdown/ga52_2025.md#ga52-p1254) |
| BCO 21-14 | RPR exception | `rpr_exception:rpr/exc/korean-central__103.html` | `structured_provision_tag` | `medium` | `contextual` | [Korean Central: Stated difference not recorded in candidate’s own words.; not judged according to prescrib](../rpr/exc/korean-central__103.html) |
| BCO 23-10 | RPR exception | `rpr_exception:rpr/exc/highlands__007.html` | `structured_provision_tag` | `medium` | `contextual` | [Highlands: No record that the Congregation/Session concurred with dissolution of pastoral relations.](../rpr/exc/highlands__007.html) |
| BCO 23-10 | RPR exception | `rpr_exception:rpr/exc/highlands__013.html` | `structured_provision_tag` | `medium` | `contextual` | [Highlands: No record that the Congregation/Session concurred with dissolution of pastoral relations.](../rpr/exc/highlands__013.html) |
| BCO 23-21 | Overture | `overture:ga51_2024:30` | `overture_action_target` | `high` | `candidate` | [Amend BCO 23-1 to Require Presbytery Exit Interview Before Dissolution of Call](../markdown/ga51_2024.md#ga51-p1190) |
| BCO 23-7 | Overture | `overture:ga03_1975:5` | `overture_action_target` | `high` | `candidate` | [Amend BCO 23-7 to Require Presbytery Approval for Non-Ordained Pastoral Supply](../markdown/ga03_1975.md#ga03-p35) |
| BCO 24-11 | CCB advice | `ccb_advice:inquiries/ga45_2017__ci02.md` | `structured_provision_tag` | `medium` | `contextual` | [Specifying that Only Males May Be Ordained](../inquiries/ga45_2017__ci02.md) |
| BCO 24-11 | CCB advice | `ccb_advice:inquiries/ga46_2018__ci04.md` | `structured_provision_tag` | `medium` | `contextual` | [The Roles and Description of Unordained Deaconesses and Deacon Assistants](../inquiries/ga46_2018__ci04.md) |
| BCO 24-11 | Overture | `overture:ga45_2017:4` | `overture_action_target` | `high` | `candidate` | [Add BCO 24-11 Specifying Males Only May Be Ordained as Elders or Deacons](../markdown/ga45_2017.md#ga45-p651) |
| BCO 24-11 | Overture | `overture:ga46_2018:9` | `overture_action_target` | `high` | `candidate` | [Amend BCO 9-7 and Add BCO 24-11 Regarding Women Serving as Deaconesses](../markdown/ga46_2018.md#ga46-p686) |
| BCO 25-14 | Judicial case | `case:cases/ga52_2025__2023-12.md` | `direct_text` | `high` | `primary` | [Flatgard v. Metro Atlanta Presbytery](../cases/ga52_2025__2023-12.md) |
| BCO 26-11 | Overture | `overture:ga08_1980:15` | `overture_action_target` | `high` | `primary` | [Add BCO 5-4 on calling pastors in new congregations](../markdown/ga08_1980.md#ga08-p40) |
| BCO 26-11 | Overture | `overture:ga08_1980:8` | `overture_action_target` | `high` | `candidate` | [Amend BCO 26-11 on congregations withdrawing from the PCA](../markdown/ga08_1980.md#ga08-p40) |
| BCO 27-11 | Overture | `overture:ga14_1986:37` | `direct_text` | `high` | `candidate` | [Amend BCO 42-4 and 43-2 to Extend Appeal and Complaint Filing Period to Sixty Days](../markdown/ga14_1986.md#ga14-p55) |
| BCO 27-37 | Constitutional inquiry | `inquiry:inquiries/ga12_1984__ci11.md` | `structured_provision_tag` | `medium` | `primary` | [Handling exceptions at ordination and distinctions between BCO and confessional exceptions](../inquiries/ga12_1984__ci11.md) |
| BCO 27-37 | Judicial case | `case:cases/ga27_1999__1998-05.md` | `direct_text` | `high` | `primary` | [Long, et al. v. James River Presbytery](../cases/ga27_1999__1998-05.md) |
| BCO 27-46 | Overture | `overture:ga51_2024:4` | `overture_action_target` | `high` | `candidate` | [Establish Study Committee to Review BCO 27-46 Judicial Rules](../markdown/ga51_2024.md#ga51-p1072) |
| BCO 3-7 | Overture | `overture:ga16_1988:23` | `direct_text` | `high` | `candidate` | [Reject Proposed BCO Amendments on Restructuring Higher and Lower Court Relations](../markdown/ga16_1988.md#ga16-p61) |
| BCO 31-33 | Overture | `overture:ga23_1995:7` | `direct_text` | `high` | `candidate` | [Consider Alternative Amendments to BCO 46-5 on Deleting Names from Rolls](../markdown/ga23_1995.md#ga23-p223) |
| BCO 31-33 | Overture | `overture:ga24_1996:14` | `direct_text` | `high` | `candidate` | [Amend BCO: Strike 46-5 & Add New BCO 38-2 & 46-2](../markdown/ga24_1996.md#ga24-p303) |
| BCO 31-33 | Overture | `overture:ga24_1996:27` | `direct_text` | `high` | `candidate` | [Delete BCO 46-5 & Amend BCO 38 and 46-2](../markdown/ga24_1996.md#ga24-p297) |
| BCO 31-33 | Overture | `overture:ga24_1996:6` | `direct_text` | `high` | `candidate` | [Amend BCO 46-5, 38-2, and 38-3 Regarding Church Discipline](../markdown/ga24_1996.md#ga24-p298) |
| BCO 31-38 | Judicial case | `case:cases/ga42_2014__2011-14.md` | `direct_text` | `high` | `primary` | [Reese and Bech v. Philadelphia Presbytery](../cases/ga42_2014__2011-14.md) |
| BCO 32-21 | CCB advice | `ccb_advice:inquiries/ga41_2013__ci01.md` | `structured_provision_tag` | `medium` | `contextual` | [Defining Supporting Reasons for a Complaint or Appeal](../inquiries/ga41_2013__ci01.md) |
| BCO 32-21 | Overture | `overture:ga41_2013:4` | `overture_action_target` | `high` | `candidate` | [Amend BCO 32 by Adding Section 32-21 on Supporting Reasons for Appeal](../markdown/ga41_2013.md#ga41-p92) |
| BCO 32-30 | Judicial case | `case:cases/ga23_1995__1993-10.md` | `structured_case_metadata` | `medium` | `primary` | [Clark v. Southwest Presbytery](../cases/ga23_1995__1993-10.md) |
| BCO 32-30 | Judicial case | `case:cases/ga23_1995__1993-12_1993-14.md` | `direct_text` | `high` | `primary` | [Grace RPC Session v. Heartland Presbytery](../cases/ga23_1995__1993-12_1993-14.md) |
| BCO 33-5 | CCB advice | `ccb_advice:inquiries/ga52_2025__ci26.md` | `structured_provision_tag` | `medium` | `contextual` | [Process for elevating suspension from office to deposition](../inquiries/ga52_2025__ci26.md) |
| BCO 33-5 | Overture | `overture:ga52_2025:39` | `overture_action_target` | `high` | `candidate` | [Amend BCO 34-8 and Add BCO 33-5 to Clarify Process for Elevating Suspension to Deposition](../markdown/ga52_2025.md#ga52-p1280) |
| BCO 38-31 | Overture | `overture:ga24_1996:6` | `direct_text` | `high` | `candidate` | [Amend BCO 46-5, 38-2, and 38-3 Regarding Church Discipline](../markdown/ga24_1996.md#ga24-p298) |
| BCO 39-4 | Judicial case | `case:cases/ga41_2013__2012-05.md` | `direct_text` | `high` | `primary` | [Hedman v. Pacific Northwest Presbytery](../cases/ga41_2013__2012-05.md) |
| BCO 40-43 | Judicial case | `case:cases/ga23_1995__1993-12_1993-14.md` | `direct_text` | `high` | `primary` | [Grace RPC Session v. Heartland Presbytery](../cases/ga23_1995__1993-12_1993-14.md) |
| BCO 40-52 | Judicial case | `case:cases/ga47_2019__2018-02.md` | `direct_text` | `high` | `primary` | [Anna Lewis v. Presbytery of the Mississippi Valley](../cases/ga47_2019__2018-02.md) |
| BCO 42-13 | CCB advice | `ccb_advice:inquiries/ga41_2013__ci02.md` | `structured_provision_tag` | `medium` | `contextual` | [Defining the Terms Used in BCO 42](../inquiries/ga41_2013__ci02.md) |
| BCO 42-13 | Overture | `overture:ga41_2013:5` | `overture_action_target` | `high` | `candidate` | [Amend BCO 42 by Adding 42-13 to Define Terms in Chapter 42](../markdown/ga41_2013.md#ga41-p92) |
| BCO 43-11 | CCB advice | `ccb_advice:inquiries/ga41_2013__ci03.md` | `structured_provision_tag` | `medium` | `contextual` | [Defining the Terms Used in BCO 43](../inquiries/ga41_2013__ci03.md) |
| BCO 43-11 | Overture | `overture:ga41_2013:6` | `overture_action_target` | `high` | `candidate` | [Amend BCO 43 by Adding 43-11 to Define Terms in Chapter 43](../markdown/ga41_2013.md#ga41-p92) |
| BCO 44-3 | Judicial case | `case:cases/ga14_1986__case7.md` | `direct_text` | `high` | `primary` | [Dye et al. v. Missouri Presbytery](../cases/ga14_1986__case7.md) |
| BCO 45-6 | CCB advice | `ccb_advice:inquiries/ga25_1997__ci03.md` | `structured_provision_tag` | `medium` | `contextual` | [Perfecting amendment language for removing members from the roll](../inquiries/ga25_1997__ci03.md) |
| BCO 46-51 | Overture | `overture:ga24_1996:6` | `direct_text` | `high` | `candidate` | [Amend BCO 46-5, 38-2, and 38-3 Regarding Church Discipline](../markdown/ga24_1996.md#ga24-p298) |
| BCO 46-9 | Overture | `overture:ga21_1993:14` | `direct_text` | `high` | `candidate` | [Amend BCO 38-3 to Clarify Discipline of Members Joining Other Churches](../markdown/ga21_1993.md#ga21-p128) |
| BCO 48-9 | Judicial case | `case:cases/ga24_1996__1995-01.md` | `direct_text` | `high` | `primary` | [David C. Lachman v. Philadelphia Presbytery](../cases/ga24_1996__1995-01.md) |
| BCO 5-11 | Overture | `overture:ga17_1989:42` | `direct_text` | `high` | `candidate` | [Fund Ethnic Ministries](../markdown/ga17_1989.md#ga17-p42) |
| BCO 5-11 | Overture | `overture:ga38_2010:15` | `overture_action_target` | `high` | `primary` | [Revise BCO 5-2 Through 5-11 and Add New BCO 5-5 Regarding Church Organization](../markdown/ga38_2010.md#ga38-p370) |
| BCO 5-11.3 | RPR exception | `rpr_exception:rpr/exc/northern-california__021.html` | `structured_provision_tag` | `medium` | `contextual` | [Northern California: Presbytery approved an invalid call (call was voted on by members of the mission church pr](../rpr/exc/northern-california__021.html) |
| BCO 5-11.3 | RPR exception | `rpr_exception:rpr/exc/pacific-northwest__029.html` | `structured_provision_tag` | `medium` | `contextual` | [Pacific Northwest: Approved TE’s call prior to congregation being particularized. BCO 5-11.3](../rpr/exc/pacific-northwest__029.html) |
| BCO 5-12 | RPR exception | `rpr_exception:rpr/exc/korean-southwest-orange-county__055.html` | `structured_provision_tag` | `medium` | `contextual` | [Korean Southwest Orange County: no record of call to or Presbytery establishment of pastoral relationship.](../rpr/exc/korean-southwest-orange-county__055.html) |
| BCO 5-12 | RPR exception | `rpr_exception:rpr/exc/korean-southwest__177.html` | `structured_provision_tag` | `medium` | `contextual` | [Korean Southwest: no record of call to or Presbytery establishment of pastoral relationship.](../rpr/exc/korean-southwest__177.html) |
| BCO 55-2 | Overture | `overture:ga40_2012:35` | `overture_action_target` | `high` | `candidate` | [Amend BCO 55-1 & Add BCO 55-2 Distinguishing Confession and Catechizing](../markdown/ga40_2012.md#ga40-p91) |
| BCO 56-58 | Overture | `overture:ga13_1985:40` | `overture_action_target` | `high` | `candidate` | [Remove Constitutional Force from BCO 56-58 Directory for Worship Chapters](../markdown/ga13_1985.md#ga13-p62) |
| BCO 56-58 | Overture | `overture:ga13_1985:7` | `direct_text` | `high` | `candidate` | [Remove Constitutional Force from BCO 56-58 Worship Directory Chapters](../markdown/ga13_1985.md#ga13-p47) |
| BCO 56-58 | Overture | `overture:ga14_1986:7` | `direct_text` | `high` | `candidate` | [Require Maximum Budget Amounts for All Requests for GA Study Committees](../markdown/ga14_1986.md#ga14-p69) |
| BCO 56-58 | Overture | `overture:ga15_1987:7` | `direct_text` | `high` | `candidate` | [Amend RAO to Establish Standing Judicial Commissions Between General Assembly Meetings](../markdown/ga15_1987.md#ga15-p63) |
| BCO 57-7.5 | Overture | `overture:ga14_1986:24` | `direct_text` | `high` | `candidate` | [Amend BCO 57-5 Membership Vow Regarding Scripture and Church Government](../markdown/ga14_1986.md#ga14-p52) |
| BCO 57-7.5 | Overture | `overture:ga15_1987:24` | `direct_text` | `high` | `candidate` | [Adopt Mission Support Policy and Distribute It to Presbyteries](../markdown/ga15_1987.md#ga15-p66) |
| BCO 57-7.5 | Overture | `overture:ga16_1988:24` | `direct_text` | `high` | `candidate` | [Prohibit GA Committees and Members from Using Hotels That Provide Pornographic Films](../markdown/ga16_1988.md#ga16-p71) |
| BCO 6-416 | Overture | `overture:ga52_2025:22` | `direct_text` | `high` | `candidate` | [Amend BCO 20-3, 24-3, and 25-1 to Permit Congregational Minimum Voting Age](../markdown/ga52_2025.md#ga52-p1208) |
| BCO 6-5 | CCB advice | `ccb_advice:inquiries/ga49_2022__ci23.md` | `structured_provision_tag` | `medium` | `contextual` | [20-3](../inquiries/ga49_2022__ci23.md) |
| BCO 6-5 | Judicial case | `case:cases/ga50_2023__2022-20.md` | `direct_text` | `high` | `primary` | [Wilson et al. v. Pacific Northwest Presbytery](../cases/ga50_2023__2022-20.md) |
| BCO 6-5 | Judicial case | `case:cases/ga51_2024__2023-11.md` | `direct_text` | `high` | `primary` | [Psiaki v. Pacific Northwest Presbytery](../cases/ga51_2024__2023-11.md) |
| BCO 6-5 | Overture | `overture:ga12_1984:46` | `overture_action_target` | `high` | `candidate` | [Amend BCO 6-5, 20-3, 24-3, and 25-1 to Allow Congregations to Set a Minimum Voting Age](../markdown/ga12_1984.md#ga12-p61) |
| BCO 6-5 | Overture | `overture:ga49_2022:30` | `overture_action_target` | `high` | `candidate` | [Amend BCO 6-5, 20-3, 24-3, and 25-1 Allowing Congregations to Establish Voting Age Restrictions](../markdown/ga49_2022.md#ga49-p1362) |
| BCO 6-5.a | Judicial case | `case:cases/ga51_2024__2023-11.md` | `direct_text` | `high` | `primary` | [Psiaki v. Pacific Northwest Presbytery](../cases/ga51_2024__2023-11.md) |
| BCO 6-7 | Overture | `overture:ga03_1975:2` | `overture_action_target` | `high` | `candidate` | [Affirm Session Authority Over Guest Preachers per BCO 6-7](../markdown/ga03_1975.md#ga03-p42) |
| BCO 60-63 | Overture | `overture:ga52_2025:5` | `overture_action_target` | `high` | `candidate` | [Grant BCO 60-63 Full Constitutional Status](../markdown/ga52_2025.md#ga52-p1172) |
| BCO 7-4 | Overture | `overture:ga23_1995:15` | `direct_text` | `high` | `candidate` | [Amend BCO 7-4 to Confine Doctrinal Requirements to Westminster Standards](../markdown/ga23_1995.md#ga23-p50) |
| BCO 7-4 | Overture | `overture:ga48_2021:16` | `overture_action_target` | `high` | `candidate` | [Amend BCO 7 to Disqualify Self-Identified Same-Sex Attracted Men from Ordination](../markdown/ga48_2021.md#ga48-p999) |
| BCO 7-4 | Overture | `overture:ga49_2022:15` | `overture_action_target` | `high` | `candidate` | [Amend BCO 7-4 to Disqualify Men Describing Themselves as Homosexual](../markdown/ga49_2022.md#ga49-p128) |
| BCO 8-11 | Overture | `overture:ga07_1979:5` | `overture_action_target` | `high` | `primary` | [Amend RAO 8-11 and 10-2 to Allow Assembly to Waive Reading of Reports](../markdown/ga07_1979.md#ga07-p29) |
| BCO 87 | RPR exception | `rpr_exception:rpr/exc/nashville__021.html` | `structured_provision_tag` | `medium` | `contextual` | [Nashville: No record of reports (2001 minutes) from men under care or men laboring out of bounds. BCO](../rpr/exc/nashville__021.html) |
| BCO 87 | RPR exception | `rpr_exception:rpr/exc/philadelphia-metro-west__021.html` | `structured_provision_tag` | `medium` | `contextual` | [Philadelphia Metro West: No indication given that TE laboring out of bounds has “full freedom to maintain and keep ](../rpr/exc/philadelphia-metro-west__021.html) |
| BCO 9-8 | CCB advice | `ccb_advice:inquiries/ga38_2010__ci04.md` | `structured_provision_tag` | `medium` | `contextual` | [Unordained Men and Women Carrying Out Diaconal Ministry](../inquiries/ga38_2010__ci04.md) |
| BCO 9-8 | Overture | `overture:ga38_2010:10` | `overture_action_target` | `high` | `candidate` | [Amend BCO 1-4, 4-2, 5-10, 7-2, 9-2, 9-7 and Add BCO 9-8 for Unordained Diaconal Ministry](../markdown/ga38_2010.md#ga38-p394) |
| RAO 1-6 | CCB advice | `ccb_advice:inquiries/ga47_2019__ci12.md` | `structured_provision_tag` | `medium` | `contextual` | [Addition of RAO 1-6](../inquiries/ga47_2019__ci12.md) |
| RAO 1-7 | CCB advice | `ccb_advice:inquiries/ga47_2019__ci12.md` | `structured_provision_tag` | `medium` | `contextual` | [Addition of RAO 1-6](../inquiries/ga47_2019__ci12.md) |
| RAO 1-8 | CCB advice | `ccb_advice:inquiries/ga47_2019__ci12.md` | `structured_provision_tag` | `medium` | `contextual` | [Addition of RAO 1-6](../inquiries/ga47_2019__ci12.md) |
| RAO 10-14 | RPR exception | `rpr_exception:rpr/exc/grace__003.html` | `structured_provision_tag` | `medium` | `contextual` | [Grace: Page 152 is missing. (BCO § 13-10; RAO § 10-14)](../rpr/exc/grace__003.html) |
| RAO 13-6 | CCB advice | `ccb_advice:inquiries/ga31_2003__ci10.md` | `structured_provision_tag` | `medium` | `contextual` | [Germane Amendments to Overtures and Resolutions by Overtures Committee](../inquiries/ga31_2003__ci10.md) |
| RAO 40-10h | RPR exception | `rpr_exception:rpr/exc/uliana__007.html` | `structured_provision_tag` | `medium` | `contextual` | [Uliana: Missing required directory, rolls, and standing rules. (RAO 40-10h).](../rpr/exc/uliana__007.html) |
| RAO 82.b(2 | RPR exception | `rpr_exception:rpr/exc/highlands__018.html` | `structured_provision_tag` | `medium` | `contextual` | [Highlands: The SJC's injunction should have been followed.](../rpr/exc/highlands__018.html) |
| WCF 10-18 | Judicial case | `case:cases/ga36_2008__2007-08.md` | `direct_text` | `high` | `primary` | [Jones v. Louisiana](../cases/ga36_2008__2007-08.md) |
| WCF 107-109 | RPR exception | `rpr_exception:rpr/exc/heritage__045.html` | `structured_provision_tag` | `medium` | `contextual` | [Heritage: Presbytery judges exception “b” as “not hostile.” The candidate stated in regard to the us](../rpr/exc/heritage__045.html) |
| WCF 22.8 | RPR exception | `rpr_exception:rpr/exc/covenant__018.html` | `direct_text` | `high` | `candidate` | [Covenant: Presbytery approved mission church elders’ relaxed view of the sabbath as “within the boun](../rpr/exc/covenant__018.html) |
| WCF 31-34 | Overture | `overture:ga32_2004:9` | `direct_text` | `high` | `candidate` | [Amend BCO Preface, Chapter 16, and 21-4 Regarding Stricter Doctrinal Subscription](../markdown/ga32_2004.md#ga32-p168) |
| WCF 35 | Judicial case | `case:cases/ga49_2022__2020-05.md` | `direct_text` | `high` | `primary` | [Speck v. Missouri Presbytery](../cases/ga49_2022__2020-05.md) |

## Model-generated relevance assessments

These counts describe the existing automated advisory assessments. They are not human-reviewed findings.

| Record type | Role | Count |
|-------------|------|------:|
| — | — | 0 |

Stored advisory rows by type, role, and fingerprint status:

| Record type | Role | Fingerprint status | Count |
|-------------|------|--------------------|------:|
| CCB advice | `direct_interpretation` | `stale` | 319 |
| CCB advice | `incidental_reference` | `stale` | 27 |
| CCB advice | `material_to_answer` | `stale` | 165 |
| CCB advice | `unrelated_or_mislinked` | `stale` | 31 |
| Constitutional inquiry | `direct_interpretation` | `stale` | 235 |
| Constitutional inquiry | `incidental_reference` | `stale` | 35 |
| Constitutional inquiry | `material_to_answer` | `stale` | 90 |
| Constitutional inquiry | `unrelated_or_mislinked` | `stale` | 60 |
| Judicial case | `applied_by_majority` | `stale` | 942 |
| Judicial case | `incidental_reference` | `stale` | 836 |
| Judicial case | `insufficient_source` | `stale` | 26 |
| Judicial case | `material_to_majority_issue` | `stale` | 114 |
| Judicial case | `substantive_nonmajority_only` | `stale` | 402 |
| Judicial case | `unrelated_or_mislinked` | `stale` | 673 |
| Overture | `amendment_target` | `stale` | 535 |
| Overture | `incidental_reference` | `stale` | 19 |
| Overture | `insufficient_source` | `stale` | 3 |
| Overture | `materially_affected` | `stale` | 9 |
| Overture | `unrelated_or_mislinked` | `stale` | 89 |
| RPR exception | `exception_target` | `stale` | 6705 |
| RPR exception | `incidental_reference` | `stale` | 2 |
| RPR exception | `substantive_treatment` | `stale` | 46 |
| RPR exception | `unrelated_or_mislinked` | `stale` | 118 |

Stored `unrelated_or_mislinked` advisory labels by record type:

- CCB advice: 31
- Constitutional inquiry: 60
- Judicial case: 673
- Overture: 89
- RPR exception: 118

Assessment status: `stale`; applied 0, stale 11481, unassessed 12439.

## Coverage and spot checks

| Recommendation coverage status | Provisions |
|-------------------------------|-----------:|
| `incomplete` | 1172 |

Acree check: PASS — expected only `BCO 43-1`; indexed `BCO 43-1`.

## Limitations

- Machine relevance assessments are model-generated advisory classifications, not human confirmation.
- Recommendation and study relationships are not comprehensively indexed by provision; per-provision coverage remains incomplete.
- Legacy authority_weight is a display/grouping field and does not state the legal force of a record.
- Match confidence describes extraction or tagging confidence, not legal relevance or authority.
