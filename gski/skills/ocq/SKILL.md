---
name: gski ocq
description: Orchestrate opencode worker sessions - run parallel waves across model tiers, handle results, track state in a ledger
---

# ocq

`gski ocq` dispatches tasks to separate opencode sessions on the shared background service so Orchestrator (O) focuses on planning and coordination while workers execute.

- Keep one `<run>` per stage/goal. Later `spawn` calls append sequential task IDs (`0001`, `0002`, ...) and share `brief.md` and `--allow` rules.
- Tiers (all run at `high` automatically):
  - `worker` (`google/gemini-4-hydrogen`, default): known-procedure implementation; executes strictly and reports blockers.
  - `builder` + `google/gemini-4-carbon`: architecture, design
- Parallelism: dispatch independent tasks together; order sequentially only on real conflicts (same files, output dependencies, shared mutable state, or resource-contending compute).

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

- `spawn` creates or appends to `<run>`, starts tasks in parallel, and notifies O automatically with `[ocq/<run>]` as each task finishes (listing any `still running` tasks).
- For mixed-tier batches or multiline tasks with backticks/`$vars`, pass `--file tasks.jsonl` or `--file - <<'EOF'`, one JSON object per line:
  `{"task": "...", "id"?: "0001", "agent"?: "worker"|"builder", "model"?: "google/gemini-4-neon", "allow"?: ["shell:ssh *"]}`
- `/tmp/opencode/**` is allowed by default. Pass `--allow` only for extra user-approved permissions (`shell:git *`, `shell:ssh *`, `external_directory:/path/**`).

## Workflow

1. Plan: read relevant inputs/docs; unless go-ahead was already given, present a concise plan (goal, tasks, tiers, needed `--allow` rules) for approval before first `spawn`.
2. Dispatch:
   - Write `.ocq/runs/<run>/brief.md` when multiple tasks share context or conventions. Workers have no O conversation context.
   - Give `worker` concrete procedure + inputs/outputs; give `builder` scope + constraints (mark review/audit/design read-only). Stack back-to-back edits to the same file into one task.
   - `spawn` and `send` are asynchronous: they only start or deliver to workers in the background and return immediately — end your response (never poll or sleep). The background watcher wakes O later with `[ocq/<run>]` as each task finishes.
3. Results and steering:
   - `[ocq/<run>]` delivers settled task status, artifact, note, denied calls, and `still running` IDs. Never claim a task finished or start dependent work until `[ocq/<run>]` (or `ocq ls <run>`) explicitly shows that task `done`/`failed`; if other tasks are still running and nothing is actionable now, reply with one short line and no tool calls.
   - Use `ocq show <run> <id>` only when full reply details are needed; never read full worker transcripts.
   - `ocq send <run> <id> "..."` steers a running worker or reopens a `done`/`failed` worker in the same session (`--queue` waits for current turn). Workers message O mid-run via `gski ocq send .. "..."` (`[ocq/<run>/<id>]`).
   - `denied: <action>: <what>` (or a worker requesting `--allow`) means an unapproved action was blocked; if already authorized in your scope, resume with `ocq send <run> <id> "continue" --allow '...'`, otherwise ask upstream first. `ocq abort <run> <id>` kills background shells and marks `failed`.
   - When all planned work is complete, report outcomes, artifacts, failures, and cost (`gski ocq ls [<run>]` resumes state in a new session).
