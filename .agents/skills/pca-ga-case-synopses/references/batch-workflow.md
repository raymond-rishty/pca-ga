# Resumable synopsis batches

Use this mode for a corpus campaign or work spanning sessions. The helper is
standard-library Python, not an automatic synopsis writer. Read the parent skill
and selected benchmarks before editorial work. Do not infer review from the
catalog's existing `audited` labels.

For new structured evaluations or model qualification, also read
[the requirements and trial contract](requirements-and-trial.md). Its evidence
checks supplement the checkpoint helper; they are not automatic semantic validation.

## Start and resume

From the repository root, invoke
`.agents/skills/pca-ga-case-synopses/scripts/batch_synopses.py` with an available
Python 3.10+ interpreter. In the commands below, `batch` means that invocation.
Global options `--root` and `--ledger` precede the subcommand.

```text
batch init
batch status
batch next --stage queued --limit 15
batch sync
```

The default durable artifact is `index/synopsis_workflow/ledger.json`. Keep it
under version control. `init` refuses to overwrite it; `sync` adds new dockets
without resetting existing work. Changed or removed catalog rows, changed
benchmarks, and changed evidence files make existing work `stale`. Repeat
triage and subsequent review for stale cases. History retains earlier payloads.
Use one writer; a leftover `.lock` after a crash may be removed only after
confirming no process is using the ledger. The script does not commit or push.

Start with a pilot of 10–20 cases covering different matter types, merits and
nonmerits dispositions, mixed relief, sparse notices, and source defects. Assess
the pilot before expanding. Thereafter select roughly 15 cases per batch; reduce
the number for lengthy opinions. `next` sorts by source page to make shared
reading convenient, but a shared page does **not** establish consolidation.
Every docket retains its own evidence, synopsis, and disposition. Record related
dockets explicitly in triage notes; read beyond a batch boundary when needed.

## Record the editorial stages

Author a JSON payload in a persistent batch folder, for example
`index/synopsis_workflow/batches/pilot/1975-01-triage.json`, then run:

```text
batch record triage --case 1975-01 --input PATH
batch record draft --case 1975-01 --input PATH
batch record verify --case 1975-01 --input PATH
batch record approve --case 1975-01 --input PATH
```

All payloads require nonempty `reviewer` and `notes` strings. These are factual
attributions, not invented reviewer identities. Additional fields by action:

| Action | Required payload fields | Result |
|---|---|---|
| `triage` | `identity`, `source_limits`, `sources` | ready |
| `draft` | `summary`, `benchmark_examples` | drafted; clears prior verification/approval |
| `verify` | `claim_checks`, `qualifications`, `pass_kind`, `scores`, `passed: true` | verified |
| `approve` | `authorization` | approved for a publication handoff |
| `repair` | Explain the defect and evidence in `notes` | repair_needed |

Each `sources` item contains repository-relative `path`, precise `locator`
(section, printed page, or lines), and `supports` explaining the supported claims.
The helper records file hashes and the benchmark version. Example triage shape:

```json
{
  "reviewer": "actual reviewer identifier",
  "notes": "Record the dispute, adopted answers, reasons, relief and qualifications.",
  "identity": "Explain docket/caption and source-boundary verification.",
  "source_limits": "State actual limitations, or explain that the adopted decision is complete.",
  "sources": [{
    "path": "cases/ga03_1975__case1.md",
    "locator": "Replace with the actual supporting section or printed pages",
    "supports": "Replace with the claims established by those passages"
  }]
}
```

Never submit the instructional example as evidence. Source limits must distinguish
a complete opinion, a sparse final notice, and an unresolved/misidentified record.
A sparse notice can support a short accurate synopsis; a missing holding cannot
support invented reasoning. If catalog metadata contradicts the decision, use
`repair`, with the proposed correction and exact evidence in the notes. Follow
the ingestion skill only when repair is authorized, then re-triage. Other cases
can continue with `next --stage queued` or `next --stage ready`.

Draft from the evidence rather than polishing the old summary. `benchmark_examples`
identifies the actual benchmark entries consulted. Verification is a separate
source-reading pass, not the drafter's score attached automatically. Use
`pass_kind: "separate_pass_same_reviewer"` when the same agent performs a fresh
pass; use `"independent_reviewer"` only for an actual different reviewer. Do not
spawn agents without authorization. `claim_checks` must explain sentence-level
support and adopted-versus-separate-opinion attribution; `qualifications` checks
mixed outcomes, remedies and material limits. The six `scores` keys are:

```json
{
  "concrete_dispute": 2,
  "decision": 2,
  "decisive_reason": 2,
  "distinctive_value": 2,
  "fidelity": 2,
  "economy": 2
}
```

These values illustrate the schema, not an expected score. Score each 0–2 against
the benchmark rubric and explain weaknesses in `notes`. Fidelity must be 2 and
the actual source check must pass; totals never automatically approve a case.
For failed review, revise the draft or record a repair blocker. Approval records
the user's actual publication authorization, including a previously authorized
batch policy if applicable. Do not invent approval or require a fresh user prompt
for each case already covered by that policy.

## Controlled publication handoff

```text
batch next --stage approved --limit 15
batch export --cases 1975-01 --out index/synopsis_workflow/batches/pilot/publication.json
```

Export accepts only fresh approved canonical dockets. Era-only records need an
identity repair before export, not an invented canonical ID. The packet contains
the entire catalog baseline and each selected override's `before` and `after`.
It preserves unrelated override fields and makes **no production edits**.

When publication is authorized:

1. Recheck `status` and regenerate a fresh packet if inputs changed. Compare each
   live override to `before`; investigate conflicts rather than overwriting them.
2. Merge only approved changes into `index/judicial_case_editorial_overrides.json`.
   Inspect the current maintained writers/consumers using the parent skill's
   application instructions. Do not assume one generator updates every surface.
3. Regenerate the authorized surfaces. Compare resulting catalog rows to the
   packet's `catalog_before`: allow the intended summary/audit changes only.
   In particular, summary wording can change automatically derived dispositions,
   BCO provisions or topics. Investigate those changes as metadata work; do not
   silently accept them as incidental publication effects.
4. Verify selected summaries in each requested surface (including legacy index,
   judicial index, app/search if in scope), source links and rendered formatting.
   Check unselected cases for unintended changes and preserve unrelated dirty work.
5. Save `publication-receipt.json` beside the packet with case IDs, packet path,
   actual changed files, commands/checks and results, unresolved limitations, and
   the commit ID if committed. Do not claim publication before these checks pass.

Publication receipts are intentionally manual: the helper's `approved` state
means editorial approval, **not** that all consumer outputs were published.
On resume, consult receipts before re-exporting approved cases. Report separately
the counts approved, published with checked receipts, stale, and repair-needed.
A drained drafting queue does not mean the corpus is complete. Close the campaign
only when all in-scope cases have verified published results or explicit,
user-accepted exceptions. Never mark an unresolved case complete merely to reach
100 percent.

## OpenAI Batch API generation

For the repository's Sol API campaign, use `scripts/synopsis_batch_api.py`. It
builds Responses API JSONL from the compact runtime contract, omits every case
with a discoverable existing Sol candidate, records source/reference hashes, and
splits the queue into conservative shards. Building and validating are local;
only `submit` calls the API. Submit shards deliberately rather than launching all
of them at once, because the account's active Batch token limit applies across
queued jobs.

```text
python scripts/synopsis_batch_api.py build
python scripts/synopsis_batch_api.py validate
python scripts/synopsis_batch_api.py submit --shard 1
python scripts/synopsis_batch_api.py status --shard 1
python scripts/synopsis_batch_api.py download --shard 1
python scripts/synopsis_batch_api.py ingest
```

Set `OPENAI_API_KEY` only in the environment. Each request uses `/v1/responses`,
strict structured output, and an explicit cache breakpoint after the stable
developer contract; case text remains in the user input. A submission receipt is
written before and after batch creation so an interrupted call is visible.
Existing receipts prevent accidental paid resubmission unless the operator passes
`--allow-resubmit` intentionally. Downloaded candidates remain in the campaign's
`first-drafts/` and `final/` audit directories and are never publication approval.

Run `ingest` after downloading one or more shards. It verifies campaign hashes,
request IDs, the full local schema, source path/hash evidence, benchmark-example
claims, matter types, and dispositions, then reports malformed, failed, missing,
and accepted candidates. Its accepted status is only `awaiting_source_audit`;
perform the separate source-reading review required above before approval.

## DeepSeek V4.1 Flash API generation

DeepSeek does not currently document a file-based Batch API. Use
`scripts/synopsis_deepseek_api.py` for the equivalent resumable workflow over
its stateless Responses API. The official V4.1 Flash model slug is
`deepseek-flash`. The runner preserves the same case selection, source and
reference hashes, JSON schema, shards, candidate validation, and no-publication
boundary as the OpenAI campaign. It replaces remote batch creation with bounded
local concurrency and a checkpoint file for every completed response.

```text
python scripts/synopsis_deepseek_api.py build
python scripts/synopsis_deepseek_api.py validate
python scripts/synopsis_deepseek_api.py run --shard 1 --concurrency 8
python scripts/synopsis_deepseek_api.py ingest
```

Set `DEEPSEEK_API_KEY` only in the environment. Run is idempotent for completed
cases: it skips existing raw checkpoints, retries transient API failures, retains
terminal errors separately, and rebuilds the shard output JSONL in manifest
order. DeepSeek manages context caching automatically, so the stable compact
contract is supplied first as `instructions` and the changing case packet follows
as `input`; do not add unsupported OpenAI cache controls. Re-running `ingest`
does not authorize publication or replace the required source-reading audit.
