---
name: gski ocm
description: Manage opencode orchestrator sessions - align with the user on high-level goals, then autonomously run multi-stage work across orchestrators
---

# ocm

`gski ocm` runs Orchestrator (O) sessions on the shared opencode background service so Manager (M) can drive multi-stage or long-running goals autonomously.

- After aligning with the user upfront, split work into bounded stages so each stage starts in a fresh O session (`google/gemini-4-carbon` by default).
- Each `ocm start` is pre-approved execution: pass the stage goal, prior-stage context, constraints, and approved `--allow` rules; O runs its `ocq` tasks and reports back when done.
- Never run two O streams concurrently in the same directory; use separate directories or worktrees for parallel streams.

## State

```
.ocm/
  ocm.json      active manager session ID (managed by ocm)
  ledger.jsonl  append-only stream state: running | reported | done | failed (managed by ocm)
```

## Commands

```bash
gski ocm start <name> "task..." [--dir DIR] [--model provider/model] [--allow RULE]...
gski ocm ls [--status S...] [--all]
gski ocm show <name> [--chars 4000] [--full]
gski ocm send <name> "text" [--queue] [--allow RULE]...
gski ocm send .. "text"
gski ocm done <name> [--note "..."]
gski ocm fail <name> [--note "..."]
gski ocm abort [<name>]
```

- Do not pass `--model` on `start` unless the user explicitly asked for another model.
- `/tmp/opencode/**` is allowed by default. Pass `--allow` only for user-approved permissions (`shell:git *`, `shell:ssh *`, `external_directory:/path/**`).

## Workflow

1. `ocm start` and `ocm send` are asynchronous: they only start or deliver to O in the background and return immediately — end your response (never poll or sleep, and never assume completion from the command output). The background watcher wakes M later with `[ocm/<name> reported ...]` once O finishes with no running `ocq` tasks or background shells.
2. Live status & messages: check `ocm ls` / `ocm show <name>` first (shows O and live workers), and steer O via `ocm send <name> "..."` (O sends mid-run updates via `gski ocm send .. "..."` -> `[ocm/<name>]`).
3. On `reported`:
   - Review O's report (`ocm show <name>` if truncated). Send corrections via `ocm send <name> "..."` if anything drifted, or mark `ocm done <name>` and start the next stage.
   - Resolve scope questions from agreed context, escalating to the user only on genuine contradictions or unapproved `denied` permissions (`ocm send <name> "continue" --allow '...'` after user approval).
   - `ocm abort <name>` stops a stuck O session (`-> reported`).
4. When all stages are `done`, report outcomes, key paths, and caveats (`gski ocm ls` resumes state in a new M session).
