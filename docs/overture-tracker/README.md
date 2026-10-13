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
  `research_status` records our evidence-gathering progress.
- [`work-queue.csv`](work-queue.csv): ordered work schedule. It continues the
  agreed backward walk from GA29 through GA1, finishing each Assembly packet
  before advancing. GA30–GA52 are not re-queued. GA52's GA53 amendment audit is
  tracked separately and must be verified against the primary minutes.
- [`assembly-gates.yaml`](assembly-gates.yaml): human-evidenced packet checks;
  counts, statuses, and next steps are generated from the evidence ledgers.

An Assembly is `open` when no packet work has begun, `in_progress` after work
begins and while any required research, candidate review, audit, build, preview,
commit, or push remains, and `closed` only after all those steps are complete.
An overture's `research_status` is `not_researched`, `in_progress`, `complete`,
or `source_unavailable`. `complete` means the available source trail was
researched; a documented historical gap can remain. Neither status describes
the overture's historical disposition.

Regenerate through Gradle with `./gradlew generateOvertureTracker` (on Windows,
`gradlew.bat generateOvertureTracker`). The task refreshes the candidate index
and overture page map through their normal Gradle dependencies before writing
the tracker views.
