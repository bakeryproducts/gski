---
name: gski ocm
description: Manage opencode orchestrator sessions - align with the user on high-level goals, then autonomously run multi-stage work across orchestrators
---

# ocm

`gski ocm` runs Orchestrator (O) sessions on the shared opencode background service so Manager (M) can drive multi-stage or long-running campaigns autonomously.

How M runs work with `ocm`:
- After aligning with the user upfront, M splits the campaign into bounded O-sized stages so each stage starts in a fresh O context (`google/gemini-4-carbon` by default).
- Each `ocm start` is pre-approved execution for O: M passes high-level goal, context from prior stages, constraints, and approved `--allow` rules; O owns task breakdown, worker/model choices, and `ocq` waves, runs Round 1 directly, and stops with results.
- Inside a stage, M reviews O's report and either steers another round in the same O session (`send`) or marks the stage `done` and starts the next O stream with a clean handoff.
- Never run two O streams concurrently in the same directory; run O streams in parallel only across separate directories or worktrees.

## State

```
.ocm/
  ocm.json      active manager session ID (managed by ocm)
  ledger.jsonl  append-only stream state: running | reported | done | failed (managed by ocm)
```

## Commands

```bash
gski ocm start <name> "task..." [--dir DIR] [--model provider/model] [--allow RULE]...
gski ocm ls [--status S...]
gski ocm show <name> [--chars 4000]
gski ocm send <name> "text" [--queue] [--allow RULE]...
gski ocm send .. "text"
gski ocm done <name> [--note "..."]
gski ocm fail <name> [--note "..."]
gski ocm abort [<name>]
```

- Do not pass `--model` on `start` unless the user explicitly asked for another model.
- `/tmp/opencode/**` is allowed by default. Pass `--allow` only for user-approved permissions (`shell:git *`, `shell:ssh host *`, `external_directory:/path/**`); O can pass those same approved rules down to `ocq spawn --allow`.

## Workflow and mechanics

1. Start and automatic wakeups:
   - Launch the stage with `ocm start <name> "..."` and end your turn with a short one-liner (e.g. `01-core started`), never an empty response; never sleep or poll.
   - `start` and `send` automatically run a zero-CPU SSE watcher in the background that wakes M with `[ocm/<name> reported ...]` (including O's report, child `ocq` summary, cost, and any denied calls) once O stops with no background shells or running `ocq` tasks.
2. Live messages:
   - A running O can message M mid-run via `gski ocm send .. "..."`, delivered as `[ocm/<name>]`.
   - When woken mid-run (by the user or `[ocm/<name>]`), handle what is actionable now (`ocm ls`, `ocm send`, user reply) and end your turn — the running stream continues and still reports automatically when finished.
3. Handling `reported` streams:
   - Round/stage completion: review O's report (call `ocm show <name>` if truncated) against the stage goal and constraints. If something was missed or drifted, send high-level corrections (`ocm send <name> "..."`) for another round in that O session. When complete, mark `ocm done <name>` and start the next stage in a fresh O session.
   - Scope question or blocker from O: resolve from what was agreed with the user (`ocm send`), or escalate to the user only if it contradicts agreed assumptions.
   - `denied: <action>: <resource>`: ocm auto-rejected an unapproved permission ask. If genuinely needed and not pre-approved, ask the user, then resume with `ocm send <name> "continue" --allow '...'`.
   - Stuck stream: `ocm abort <name>` kills O's background shells and interrupts O (`-> reported`); if child `ocq` workers remain running, `abort` prints the `gski ocq abort` command.
4. Finish and resume:
   - When all stages are `done`, report accomplished outcomes across stages, key paths, caveats, and total cost (O + child `ocq` runs from `ocm ls`).
   - A new M session resumes from files: `gski ocm ls` (re-attaches M and ensures the watcher if streams are `running`) and `gski ocm show <name>`.
