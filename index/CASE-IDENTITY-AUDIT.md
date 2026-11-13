# Judicial Case Identity Audit

This report identifies candidates for source review. It does not establish that every
canonical/era mismatch is erroneous and does not modify the corpus.

- Findings: 17
- High confidence: 15
- Medium confidence: 0
- Roster rows checked: 480

| Confidence | Roster/current ID | Suggested ID | Caption | Signals | Evidence |
|---|---|---|---|---|---|
| high | `1995-10` | `1995-10` | ). P then sought to Reference the trial to the SJC, which the SJC declined (Case 1996-07). P declined | same id caption conflict | — |
| high | `1997-07` | `1997-07` | Black v. Eastern Carolina — M29GA, 2001 Dallas, p. 98. Not sustained 13-3. D-Op Summary: Alleged P failed to consider C, and erred by ruling the licentiate had "not taken an exception to WCF regarding creation." Issues: 1. At its October 1999 meeting, by failing to either sustain or deny TE Black's | same id caption conflict | cases/ga46_2018__2017-01.md:295; markdown/ga28_2000.md:5282; markdown/ga29_2001.md:3177 |
| high | `1997-15` | `1997-15` | George v. Central Florida [ M26GA (1998): 148. This case was deemed abandoned due to death of Complainant without heirs | same id caption conflict | — |
| high | `2001-01` | `2001-01` | Morrison v. Philadelphia — M29GA, 2001 Dallas, p. 114. Not sustained 18-0 Summary: Alleged P failed to constitutionally handle a "Memorial" alleging a S was guilty of a "grossly unconstitutional proceeding" involving a dispute between two REs not on the S. Issue: Did P act in an unconstitutional man | same id caption conflict | cases/ga32_2004__2002-18.md:23; markdown/ga28_2000.md:5283; markdown/ga28_2000.md:14091 |
| high | `2002-02` | `2002-02` | ; Complaint 16-01, Judicial Case 2002-03; Complaint 18-01, Judicial Case 2002-03; Complaint 19-01, | same id caption conflict | cases/ga33_2005__2001-34_2002-02_2002-03.md:364; markdown/ga33_2005.md:1560; markdown/ga40_2012.md:10029 |
| high | `2002-15` | `2002-15` | Bjork v. Philadelphia | same id caption conflict | — |
| high | `2002-26` | `2002-06` | Appeal of Wright v. Northern California | no same id extracted case, strong cross id caption match, explicit citation disagrees with roster | cases/ga31_2003__2002-06.md:19; cases/ga39_2011__2009-25_2009-26.md:23; cases/ga39_2011__2009-25_2009-26.md:23 |
| high | `2002-27` | `2001-34` | Nichols v. James River | no same id extracted case, strong cross id caption match, explicit citation disagrees with roster | cases/ga30_2002__2002-02_2002-03.md:28; cases/ga30_2002__2002-02_2002-03.md:29; cases/ga31_2003__2002-07.md:19 |
| high | `2005-14` | `—` | Judicial Case 2005-14 | substantive extracted case absent from canonical catalog | — |
| high | `2010-14` | `2010-14` | Sartorius v. Siouxlands Presbytery — M39GA, 2011 Virginia Beach, p. 578. Not sustained 19-1. C-Op 8. D-Op. Summary: Alleged P erred in BCO 31-2 investigation of a TE and in failing to find a strong presumption of guilt. Issue: 1. With respect to certain reports concerning TE Joshua Moon, was Siouxla | same id caption conflict | cases/ga39_2011__2010-16.md:68; cases/ga42_2014__2011-11_2011-12_2011-15_2011-16.md:393; cases/ga43_2015__2012-08.md:30 |
| high | `2010-17` | `2010-17` | Sarafolean Letter — M39GA, 2011 Virginia Beach, p. 594. AOO Summary: TE Sarafolean (a minister in Great Lakes Presbytery) requested GA to cite Siouxlands for alleged failures. TE Sarafolean believed he could do this via a BCO 40-5 letter. | same id caption conflict | — |
| high | `2012-13` | `2012-03` | Appeal of Tarter v. Evangel — M42GA, 2014 Houston, p. 539. Sustained 15-0. Summary: TE was laboring out of bounds in Ireland. P instructed him on accountability, but he declined requests. Eventually indicted for failure to submit to P authority, found guilty of two charges at trial, and deposed. He | no same id extracted case, possible cross id caption match, explicit citation disagrees with roster | cases/ga42_2014__2012-03.md:28; markdown/ga42_2014.md:10244 |
| high | `2015-06` | `2015-06` | PCA v. South Florida | same id caption conflict | cases/ga25_1997__1995-10.md:89; markdown/ga25_1997.md:3021 |
| high | `2020-09` | `2020-09` | Oxbalt et al. v. Pacific Presbytery | same id caption conflict | — |
| high | `2022-10` | `2022-10` | PCA v. Herron (trial). Decided 04/05/23. Not Guilty | same id caption conflict | cases/ga50_2023__2021-14.md:30; cases/ga50_2023__2021-14.md:30; cases/ga50_2023__2021-15.md:32 |
| review | `2009-26` | `—` | Session of Grace Presbyterian Church v. Northern California Presbytery | substantive extracted case absent from canonical catalog | — |
| review | `2019-12` | `—` | Pitts et al. v. Arizona Presbytery | substantive extracted case absent from canonical catalog | — |

## Review procedure

1. Confirm a proposed ID against the decision heading and any explicit later citation.
2. Treat `Case #N` as an era ID; do not force it to equal the canonical suffix.
3. Review the whole collision chain before approving one mapping.
4. Move approved entries into the durable identity-override file used by the taxonomy builder.
5. Regenerate the case indexes and verify that no substantive extracted case disappeared.
