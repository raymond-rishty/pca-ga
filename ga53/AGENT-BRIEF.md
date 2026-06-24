# GA53 (2026) Overture Research — Agent Brief

You research a batch of overtures to the **53rd PCA General Assembly (2026)**. For each assigned
overture, find **past actions that bear on it** and write a findings file.

"Past actions" = four categories, all in the local corpus (covers PCA GAs 1973–2025, i.e. GA1–GA52):
1. **Judicial cases** — SJC (Standing Judicial Commission) & predecessor CJB (Committee on Judicial Business).
2. **Constitutional inquiries / CCB advice** — questions of constitutional meaning answered by the CCB (or pre-1990 CJB), and CCB advice on whether prior overtures/amendments conflict with the Constitution.
3. **Prior overtures** — earlier proposals on the same provision or subject, with their outcome (adopted/ratified, defeated, etc.). **Recent ones (GA48–52, 2021–2025) are especially valuable** — the user explicitly wants to know when a recent overture *expanded/contracted/changed* what the new one now addresses.
4. **RPR exceptions** — Review-of-Presbytery-Records exceptions of substance citing the provision (shows real-world friction with the rule).

## The corpus (all under /workspace)

| File | What | How to search |
|---|---|---|
| `index/CASES.md` | 647 SJC/CJB cases, by Assembly: number, parties, disposition, link | grep by topic/party |
| `index/cases.jsonl` | per-case JSON incl. `bco_cited_as_s` (provisions a case construed) | grep provision here to find cases by BCO section |
| `cases/*.md` | full verbatim case text | read when a case looks relevant |
| `index/INQUIRIES.md` | CCB/CJB constitutional inquiries; **Provisions** column | grep by provision token & topic |
| `index/CCB-OVERTURE-ADVICE.md` | CCB advice on proposed overtures/amendments; **Provisions** column | grep by provision token & topic |
| `index/OVERTURES.md` | ~2,028 prior overtures, by Assembly: number, Subject, Outcome, Source, page | grep by topic keywords AND provision |
| `index/RPR-BY-PROVISION.md` | RPR exceptions grouped under `## BCO X-Y` provision headers | grep the provision header + nearby rows |
| `index/pca_minutes.db` | SQLite FTS over everything (pages_fts, cases_fts, overtures table) | use for full-text when grep misses |

### SQLite recipes (use when grep of the .md is insufficient)
```bash
sqlite3 /workspace/index/pca_minutes.db "SELECT ga_ordinal,year,number,title,final_disposition FROM overtures WHERE title LIKE '%deacon%' ORDER BY ga_ordinal;"
sqlite3 /workspace/index/pca_minutes.db "SELECT p.vol,p.pdf_page,snippet(pages_fts,0,'[',']','…',15) FROM pages_fts f JOIN pages p ON p.page_id=f.rowid WHERE pages_fts MATCH '\"original jurisdiction\"' LIMIT 15;"
```

## CRITICAL methodology

1. **Read the overture's own PDF first.** Each overture's URL is given. Fetch it (WebFetch). PCA
   overtures state their grounds in "Whereas" clauses that **frequently cite the exact prior
   overtures, SJC cases, or CCB rulings** that bear on them. Capture every such citation — these are
   the highest-value bearing actions. Also note what the overture *changes* and *why*.
2. **Search by BOTH the provision number AND the concept.** A grep for "BCO 32-19" alone misses
   actions that used the topic words ("representation", "counsel", "judicial process") or an older
   BCO number. **BCO sections were renumbered over the years** — if a chapter was renumbered, older
   actions cite the old number. When unsure, search the topic words too, and check
   `/workspace/index/bco_renumberings.jsonl` (or `scripts/bco_concordance.py`) if a chapter looks renumbered.
3. **Distinguish bearing vs. incidental.** Include an action only if it genuinely informs the
   overture (construes the same provision, decided the same question, is a prior attempt at the same
   change, or is real-world friction with the rule). For each, say *how* it bears in one phrase.
4. **Be honest.** If a category has nothing, write "None found." Do not invent case numbers or
   overture numbers — every citation must come from the corpus or the overture PDF.

## Output — one file per overture: `/workspace/ga53/findings/O<NN>.md`

Use exactly this template (omit nothing; "None found." where empty):

```
## O<NN> — <Title>
**Targets:** <BCO/RAO provisions> · **Source:** <presbytery> · **PDF:** <url>
**What it does:** <1–2 sentences: the change and its purpose, from the PDF>
**Cites in its own grounds:** <prior actions the overture itself cites, or "None">

### Judicial cases (SJC/CJB)
- **<case # — parties>** (<GA/year>, <disposition>) — <how it bears>. [link or CASES.md row]
(or: None found.)

### Constitutional inquiries / CCB advice
- **<inquiry id>** (<GA/year>) — <subject; how it bears>. [INQUIRIES.md or CCB-OVERTURE-ADVICE.md]
(or: None found.)

### Prior overtures
- **GA<N> O<n>** (<year>, <outcome>) — <subject; how it bears>. ⭐ if GA48–52 (recent).
(or: None found.)

### RPR exceptions
- **BCO X-Y** — <N citations; example presbytery/year; how it bears>. [RPR-BY-PROVISION.md]
(or: None found.)

### Note
<Any cross-overture link (e.g. "companion to O37/O38 on women deacons"), renumbering caveat, or judgment call.>
```

Keep each finding tight and cited. Quality over volume: a few well-targeted, correctly-cited bearing
actions beat a long list of weak matches.
