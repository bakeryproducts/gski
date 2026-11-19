---
name: gski ocq
description: Orchestrate opencode worker sessions - run parallel waves across model tiers, handle results, track state in a ledger
---

# ocq

`gski ocq` dispatches tasks to separate opencode sessions on the shared background service so Orchestrator (O) focuses on thinking, planning, and coordination while workers execute in parallel.

How O runs work with `ocq`:
- O plans the approach, gets go-ahead before the first run (unless already authorized in the prompt), and executes in bounded rounds: launch a wave of parallel tasks -> end turn -> wake automatically on `[ocq/<run>]` once the wave settles -> inspect structured results -> launch the next dependent wave if part of the plan -> stop and report results. Follow-up fixes go into an explicit next round, never ad-hoc mid-run spawning.
- Tasks use model/agent tiers matched to the job (all run at `high` automatically):
  - `worker` (`google/gemini-4-hydrogen`, default): implementation and tasks with a known procedure; executes strictly and reports blockers instead of investigating.
  - `builder` + `google/gemini-4-neon`: check, code review, audit, verification.
  - `builder` + `google/gemini-4-carbon`: architecture, design, hard trade-offs, open-ended investigation.
- Parallelism is the default: combine independent tasks in one wave — edits to disjoint files, `carbon` design on one area, `hydrogen` implementation on another, and `neon` review on finished code run together.
  Separate into sequential waves (or merge into one task) only on real conflicts: editing the same files, reading files another task is modifying, output dependencies, shared mutable state (ports, DB, build artifacts), or heavy compute/benchmarks that contend for resources or skew timings.
- Meaningful tests, benchmarks, or a `neon` review/audit task are fine when requested or warranted; do not run paranoid syntax checks or boilerplate validation.

## State

```
.ocq/runs/<run>/
  brief.md           shared goal, context, conventions (optional; every worker reads it when present)
  run.json           run metadata and permissions (managed by ocq)
  ledger.jsonl       append-only task state: running | done | failed (managed by ocq)
  results/<id>.json  worker output: {"status": "done"|"failed", "artifact": ..., "note": ...}
```

## Commands

```bash
gski ocq spawn <run> "task"... [--file tasks.jsonl|-] [--agent worker|builder] [--model M] [--allow RULE]...
gski ocq ls [<run>] [--status S...]
gski ocq show <run> <id> [--chars 4000]
gski ocq send <run> <id> "text" [--queue] [--allow RULE]...
gski ocq send .. "text"
gski ocq abort <run> [<id>...]
```

- `spawn` creates `<run>` automatically if needed, assigns sequential IDs (`0001`, `0002`, ...), starts all given tasks immediately in parallel, and runs a zero-CPU SSE watcher in the background that wakes O with `[ocq/<run>]` when all running tasks in `<run>` finish.
- For mixed-tier waves or multiline tasks with backticks/`$vars` (avoiding double-quoted shell expansion), pass `--file tasks.jsonl` or `--file - <<'EOF'` via stdin, one JSON object per line:
  `{"task": "...", "id"?: "0001", "agent"?: "worker"|"builder", "model"?: "google/gemini-4-neon", "allow"?: ["shell:ssh host *"]}`
- `/tmp/opencode/**` is allowed by default. Pass `--allow` only for extra user-approved permissions (`shell:git *`, `shell:ssh host *`, `external_directory:/path/**`). Workers cannot spawn subagents.

## Workflow and mechanics

1. Plan: read relevant inputs/docs; unless go-ahead was already given, send a concise plan (goal, wave/task breakdown, tiers, needed `--allow` rules) and wait for approval before first `spawn`.
2. Brief and tasks:
   - Write `.ocq/runs/<run>/brief.md` when multiple tasks share context, architecture, or conventions (skip for a single self-contained task). Workers have no O conversation context.
   - Give `worker` concrete procedure + inputs/outputs; give `builder` scope + constraints (state read-only explicitly for review/audit/design tasks). Stack back-to-back edits to the same file into one task.
3. Dispatch and automatic wakeups:
   - Spawn the wave and end your turn with a short status line (never an empty response; never sleep or poll).
   - `[ocq/<run>]` arrives automatically once all running tasks in `<run>` settle. For an independent fast side-task launched while a slow `<run>` is running, use a separate `<run>` name so it notifies independently.
   - Worker outputs exist only after `[ocq/<run>]` arrives (or `ocq ls <run>` shows `done`/`failed`). When woken mid-wave by an upstream or `[ocq/<run>/<id>]` message while tasks are still `running`, handle what can be done now (`ocq ls`, `spawn`, `send`, `ocm send ..`), then end your turn — `<run>` still notifies when its remaining tasks finish.
4. Results and steering:
   - `[ocq/<run>]` includes each settled task's status, artifact, note, any denied calls, and the run summary (`ocq ls <run>` shows full run state; call `ocq show <run> <id>` only when full reply/details are needed). Never read full worker transcripts.
   - To steer a running worker or ask a finished (`done`/`failed`) worker for a follow-up in the same session, run `ocq send <run> <id> "..."` (`--queue` waits for current turn; `done`/`failed` reopen to `running` and notify automatically when done).
   - Workers can message O mid-run without stopping via `gski ocq send .. "..."`, delivered as `[ocq/<run>/<id>]`.
5. Permissions and stuck workers:
   - `denied: <action>: <what>` means ocq auto-rejected an unapproved permission ask. Ask the user before granting `--allow`.
   - Workers running background shells stay `running` until shells exit and the final turn completes. For stuck outliers, inspect with `show`, then `abort <run> <id>` (kills bg shells -> `failed`).
6. Finish and resume:
   - When the round completes, stop and report outcomes, artifact paths, failures, cost, and a next-round proposal if fixes are needed.
   - A new O session resumes from files: `gski ocq ls [<run>]` (re-attaches O and ensures the watcher if tasks are still `running`) and `brief.md`. If `server not reachable`, ask the user to run `opencode service start`.
