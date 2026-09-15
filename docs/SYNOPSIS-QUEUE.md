# Budgeted synopsis calibration

The queue is an orchestration/checkpoint layer, not an automatic approval system.
The existing editorial ledger and production summaries remain untouched. Use
`scripts/synopsis_queue.py` with Python 3.10+. Campaign:
`index/synopsis_workflow/sol-calibration-1`.

## Policy

- Sol, Medium: same setting as the original successful bakeoff. Fresh worker
  context, no inherited conversation, one active worker, at most five dockets
  and 120,000 source bytes per ordinary batch (an oversized single case stands
  alone). Full source pages are numbered and hashed, not summarized away.
- Relevant skill, rubric and taxonomy remain mandatory. Workers follow
  incorporated decisions and report unavailable evidence rather than infer it.
- Three batches / 15 dockets; no automatic expansion or publication. This is a
  purposive efficiency calibration, not a representative corpus sample.
- Reserve at least 20% of both account windows. Before every launch, obtain a
  fresh usage snapshot. Missing/stale/reset-crossing usage fails closed.
- Pause after observed run deltas reach 10 percentage points of the five-hour
  account window. This is a **between-batch launch gate**, not a hard in-flight
  cap: one worker may exceed it. Account deltas include concurrent work and
  rounding; they are not attributable model tokens or billed cost.
- No reset credits, purchases, Fast-mode changes, or background scheduler are
  authorized by this queue. Product subagent service-tier settings may be
  inherited; do not claim the script controls them.

## Automatic runner (recommended)

**Efficiency update:** the multi-case agentic runner is retained for provenance
but is no longer the preferred production path. Its first successful five-case
run made 25 shell calls and 11 file edits and reported 1,851,430 aggregate input
tokens (1,761,920 cached), 21,591 output tokens, and 4,217 reasoning tokens. The
account five-hour window rose 23 percentage points. That is not scalable.

`scripts/run_synopses_compact.py` is the preferred next experiment. For each
case it mechanically assembles the full source, controlled taxonomy, rubric and
two applicable benchmark entries into one prompt. It starts a fresh ephemeral,
read-only Sol process with user/project rules, shell, apps, plugins and web search
disabled; strict JSON is the only requested response. The script then writes
the preserved first/final records, validates them, checkpoints, and rechecks
usage before the next case. Sol does no repository discovery or bookkeeping.

```powershell
.\scripts\run-synopses-compact.ps1 run -MaxCases 1
```

Use one case for the initial measurement. This one-response design records
`first_summary` and an instructed source recheck in the same response; it is not
a temporally separate second model call. Independent acceptance audit remains
mandatory. Do not compare its quality or usage to the agentic path until that
single-case experiment is audited. The compact runner has not yet been launched;
the current campaign budget is exceeded.

Existing Sol drafts are reused, not regenerated. `existing-sol.json` inventories
the recorded Sol runs (including the old trial schema) and source-hash status.
Both preparation and dispatch exclude existing Sol candidates. A newly discovered
candidate moves a queued docket to `existing_draft_requires_review`; this does
not grant approval, erase prior audit results, or silently choose among multiple
drafts. Changed/missing evidence requires review of the existing draft, not an
automatic new model run. Refresh the inventory with `synopsis_queue.py
--campaign index/synopsis_workflow/sol-calibration-1 inventory-sol`.

From the repository in a normal PowerShell terminal:

```powershell
.\scripts\run-synopses.ps1 check
.\scripts\run-synopses.ps1 run -MaxBatches 3
.\scripts\run-synopses.ps1 status
```

`check` performs a live subscription-usage read without a model call. `run`
checks that same budget gate, claims a batch, starts a fresh ephemeral Sol
Medium `codex exec` process, waits, collects outputs, validates and checkpoints,
and advances up to the requested batch count. It stops on the budget gate,
worker errors, malformed/missing outputs, or uncertain interruption. No
supervising model or manual copying of outputs is required. The default is one
batch. `status` reads local state and writes `report.json`; no model or network
call. The script preserves your existing Codex login/configuration, forces
workspace-write sandboxing and never-approve mode, and does not bypass safety.
It does not alter Fast-mode settings or guarantee a particular inherited tier.

Python entry point: `python scripts/run_synopses.py run --max-batches 3`.
The PowerShell wrapper selects the bundled Python runtime where installed.
If running inside another restricted sandbox, Codex may not see its login;
run the command in a normal terminal. Do not copy credentials into the repo.

Worker receipts, timestamped usage snapshots and CLI event logs are stored in
`attempts/run-NNN/`. Reported CLI token counts are retained when present; missing
counts and monetary cost remain unknown. These logs may include case text and
local command output; keep them local unless intentionally sharing them.

For an externally completed worker or an interrupted run, first confirm the
worker AND its tool subprocesses have stopped, then use:

```powershell
.\scripts\run-synopses.ps1 collect -ConfirmWorkerStopped
```

Collection does not generate, approve or publish anything. A delayed collection
snapshot includes intervening account activity and cannot isolate worker cost.
Malformed records are retained as `validation_failed`, not automatically sent
back to a model. Audit/repair is a separate deliberate step.

The five original calibration candidates have been collected and structurally
validated; they await source audit. The remaining ten stay queued. The existing
10-percentage-point campaign cap is already exceeded by observed account usage,
so `run` currently pauses. Changing that budget requires an explicit decision;
the runner does not reset it on each invocation.

Implementation references: [Codex noninteractive execution](https://learn.chatgpt.com/docs/non-interactive-mode)
and [App Server usage reads](https://learn.chatgpt.com/docs/app-server).

## Manual orchestration / recovery

1. Call the product usage tool. Save only `captured_at` (UTC) and
   `rateLimitsByLimitId` from its actual response in a unique snapshot JSON.
2. Run `python scripts/synopsis_queue.py --campaign
   index/synopsis_workflow/sol-calibration-1 claim --snapshot PATH`.
   A paused result means **do not dispatch**. A claim marks the selected dockets
   running under an exclusive file lock. Claim once, not once per poll.
3. Spawn one fresh Sol Medium worker with the returned prompt path and EXACT
   returned case IDs. On retries, the claim's IDs override the original batch
   prompt. Record the actual agent ID separately in the campaign. The script
   itself does not launch models, so a human/product orchestrator must honor it.
4. Once that worker has stopped, capture another usage snapshot and run the
   same command with `finish` instead of `claim`. Never finish an active worker.
   Preserve its raw first/final drafts. Missing outputs are requeued; explicit
   blockers and structural failures are retained for attention, not repeatedly
   redrafted. A failed dispatch also uses `finish` after confirming no worker
   started. An unknown dispatch outcome requires investigation before retry.
5. Audit ALL calibration candidates against source text independently of their
   self-scores. Preserve audit corrections separately. Structural validation
   and `awaiting_audit` do not mean verified or approved. Then use the existing
   skill's triage/draft/verify ledger steps for genuinely verified records.

`status` prints durable queue state. Source, catalog, instruction, or packet
changes prevent a new claim; investigate and prepare a new version instead of
silently overwriting prior work. A crashed lock requires confirming no writer
is active before removal. There is no automatic background resumption.

Acceptance remains the trial contract: zero material errors; at most one minor
factual correction across 15; valid metadata throughout; reasoned synopses at
least 10/12; sparse notices judged on fidelity to their limits. Record generation,
verification, audit and repair costs separately when measurable. Until then,
no credible cases-per-window or 500-case completion forecast is available.

## Experimental light-model route

Do not route by confidence, word count, or matter type alone. A candidate narrow
route is a **self-contained final status notice** with an explicit withdrawal
or abandonment, unambiguous docket/caption/actor, no incorporated decision,
no later unresolved stage, no merits reasoning, no mixed or conditional relief,
and no material procedural qualification. Shared notices require verified
per-docket mapping first. Abandonment with a stated reason must preserve it.

A preliminary catalog/size screen found 31 records whose sole catalog outcome
is withdrawal/abandonment and whose source file is under 1,600 bytes. This is
an upper-bound candidate list, NOT 31 eligible cases or a validated route.
Examples show why: three 1997 withdrawals share one sentence and need separate
docket mapping; 1997-11 is short but explains a restriction on appeal, while
1985-04 includes an alternative procedure for removing censure. Those latter
two are excluded from this narrow route even though they are short.

For genuinely bare notices, deterministic text such as “The complainant
withdrew the complaint” may be safer and cheaper than any model—but only after
source identity, vehicle, and action are established. A template is not a way
to infer those facts from unverified catalog labels.

Before allowing Flash Lite on this category, freeze source-only eligibility
rules and a held-out selection; have it produce only supported status prose,
then audit every trial result, including boundary cases. Require zero material
errors and test whether eligibility can be established cheaply and reliably.
Include screening/mapping cost in the saving. Keep this route experimental;
do not silently classify previous Gemini responses as approved or represent
the 3.8 Flash rerun as evidence about 3.5 Flash Lite. No external API run has
been launched for this routing investigation.
