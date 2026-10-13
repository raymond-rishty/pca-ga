# Overture action tracker

The main view is [`../overture-action-tracker.yaml`](../overture-action-tracker.yaml).
It groups every distinct overture record under its GA and shows the GA packet
status, gates, next step, and per-overture research status in one place.

Spreadsheet exports are in this directory:

- [`assemblies.csv`](assemblies.csv): one row per GA with record/candidate
  counts, packet gates, and blockers.
- [`overtures.csv`](overtures.csv): one row per distinct overture record for
  sorting and filtering. Use `record_id` as the unique key because numbers can
  recur; `disposition` records the historical result while
  `research_status` records our evidence-gathering progress. Rows are sorted by
  GA, numeric overture number, source page, then full record ID.
- [`work-queue.csv`](work-queue.csv): ordered work schedule. It continues the
  agreed backward walk from GA29 through GA1, finishing each Assembly packet
  before advancing. The generated queue is the source of truth for the current
  next packet and its outstanding work. GA30–GA50 and GA52 have a later
  post-walk verification pass, so their remaining candidate reviews and packet
  gates stay visible without interrupting the backward walk. GA51 remains
  visible in the status tables but is excluded from future work queues by
  project direction. GA52's GA53 amendment audit is a separate follow-up and
  must be verified against the primary minutes.
- [`assembly-gates.yaml`](assembly-gates.yaml): human-evidenced packet checks;
  counts, statuses, and next steps are generated from the evidence ledgers.

An Assembly is `open` when no packet work has begun, `in_progress` after work
begins and while any required research, candidate review, audit, build, preview,
commit, or push remains, and `closed` only after all those steps are complete.
This is a strict evidence-based status: a prior note that work was researched
does not close a packet without verified gates and a pushed packet commit.
Read current status from the generated GA rows; packets in the post-walk queue
are unfinished until their listed research and closure gates are complete.
An overture's `research_status` is `not_researched`, `in_progress`, `complete`,
or `source_unavailable`. `complete` means the available source trail was
researched; a documented historical gap can remain. Neither status describes
the overture's historical disposition.

Regenerate through Gradle with `./gradlew generateOvertureTracker` (on Windows,
`gradlew.bat generateOvertureTracker`). The task refreshes the candidate index
and overture page map through their normal Gradle dependencies before writing
the tracker views.
