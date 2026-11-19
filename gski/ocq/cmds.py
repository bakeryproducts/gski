import json
import os
import sys
import time

from gski.oc_lib.api import (
    active,
    api,
    create_session,
    interrupt,
    kill_shell,
    messages,
    send_prompt,
    send_synthetic,
    shells,
    turn_text,
)
from gski.oc_lib.common import cut, die
from gski.oc_lib.watch import spawn_watcher
from gski.ocq.settle import ensure_watch
from gski.ocq.state import (
    PARENT_TARGETS,
    append,
    build_prompt,
    caller_task,
    ensure_run,
    fold,
    load_cfg,
    next_id,
    project_root,
    resolve,
    row,
    rules_for,
    run_dir,
    summary,
)


def cmd_spawn(args):
    items = [{"task": t} for t in args.text]
    if args.file:
        with (sys.stdin if args.file == "-" else open(args.file)) as src:
            for line in src:
                line = line.strip()
                if line:
                    items.append(json.loads(line) if line.startswith("{") else {"task": line})
    if not items:
        die("no tasks given (pass task strings or --file)")
    rd, cfg = ensure_run(args.run, args.allow)
    tasks = fold(rd)
    for it in items:
        if not it.get("task"):
            die(f"item without task: {it}")
        tid = str(it.get("id") or next_id(tasks))
        if tid in tasks:
            die(f"duplicate id: {tid}")
        agent = it.get("agent") or args.agent or cfg.get("agent") or "worker"
        model = it.get("model") or args.model or cfg.get("model")
        rules, item_allow = rules_for(cfg, list(args.allow or []) + list(it.get("allow") or []))
        (rd / "results" / f"{tid}.json").unlink(missing_ok=True)
        meta = {"ocq_root": str(cfg["dir"]), "run": args.run, "task": tid}
        s, used = create_session(f"ocq/{args.run}/{tid}", agent, model, rules, cfg["dir"], meta)
        now = time.time()
        t = {"id": tid, "task": it["task"]}
        send_prompt(s["id"], build_prompt(rd, args.run, t))
        model_id = used.split(" ")[0]
        tasks[tid] = t
        append(
            rd,
            id=tid,
            task=it["task"],
            agent=agent,
            model=model_id,
            status="running",
            session=s["id"],
            attempts=1,
            started=int(now),
            sent=round(now - 0.5, 3),
            allow=item_allow or None,
            msg=None,
            notified=False,
        )
        print(f"{tid} running {s['id']} [{agent} · {used}]")
    spawn_watcher(rd, "gski.ocq")


def cmd_ls(args):
    if not args.run:
        runs = project_root() / ".ocq" / "runs"
        found = sorted(p for p in runs.glob("*") if (p / "run.json").exists()) if runs.exists() else []
        if not found:
            print("no runs")
        for rd in found:
            ensure_watch(rd)
            print(f"{rd.name}: {summary(fold(rd))}")
        return
    rd = run_dir(args.run)
    ensure_watch(rd)
    tasks = fold(rd)
    print(summary(tasks))
    for t in tasks.values():
        if not args.status or t["status"] in args.status:
            print(row(t))


def cmd_show(args):
    rd = run_dir(args.run)
    ensure_watch(rd)
    tasks = fold(rd)
    t = tasks[resolve(tasks, [args.id])[0]]
    cost = f"  cost: ${t['cost']:.4f}" if t.get("cost") else ""
    print(f"id: {t['id']}  status: {t['status']}  attempts: {t.get('attempts', 0)}  session: {t.get('session', '-')}{cost}")
    if t.get("agent") or t.get("model"):
        print(f"agent: {t.get('agent', 'worker')}  model: {t.get('model', '-')}")
    print(f"task: {t.get('task')}")
    for k in ("artifact", "note", "msg", "tokens"):
        if t.get(k) not in (None, ""):
            print(f"{k}: {t[k]}")
    for d in t.get("denied") or []:
        print(f"denied: {d}")
    if t.get("session"):
        txt = turn_text(messages(t["session"], limit=30))
        if txt:
            print("--- last reply ---")
            print(txt[: args.chars])


def cmd_send(args):
    pos = [args.first, args.second] + ([args.third] if args.third is not None else [])
    caller = os.environ.get("OPENCODE_SESSION_ID")
    mine = caller_task(caller) if caller else None
    if mine:
        rd, run_name, t = mine
        if args.allow:
            die("--allow is only for orchestrator -> worker")
        if len(pos) == 2:
            dst, text = pos
        elif len(pos) == 3 and pos[0] == run_name:
            _, dst, text = pos
        else:
            die("usage from worker: gski ocq send .. <text>")
        if dst not in PARENT_TARGETS:
            die("worker can only send to ..")
        orch = load_cfg(rd).get("orchestrator")
        if not orch:
            die("no orchestrator session recorded in run.json")
        send_synthetic(orch, f"[ocq/{run_name}/{t['id']}]\n{text}", f"ocq/{run_name}/{t['id']}")
        append(rd, id=t["id"], msg=cut(text, 300))
        print(f"{t['id']} -> .. sent")
        return
    if len(pos) == 2 and pos[0] in PARENT_TARGETS:
        die("not in a worker session")
    if len(pos) != 3 or pos[1] in PARENT_TARGETS:
        die("usage: gski ocq send <run> <id> <text>")
    run_name, tid_arg, text = pos
    rd = run_dir(run_name)
    cfg = load_cfg(rd)
    tasks = fold(rd)
    t = tasks[resolve(tasks, [tid_arg])[0]]
    if not t.get("session"):
        die(f"{t['id']} has no session")
    extra = list(dict.fromkeys((t.get("allow") or []) + list(args.allow or [])))
    rules, merged_allow = rules_for(cfg, extra)
    api("PATCH", f"/api/session/{t['session']}", {"permissions": rules})
    rel = f".ocq/runs/{run_name}/results/{t['id']}.json"
    prompt = (
        f'[ocq orchestrator — reply mid-run via `gski ocq send .. "..."` while keeping work/bg jobs running; '
        f'when finished, write {rel}: {{"status": "done" | "failed", "artifact": "<path or short value>", "note": "<one line>"}}]\n{text}'
    )
    delivery = "queue" if args.queue else "steer"
    now = time.time()
    send_prompt(t["session"], prompt, delivery)
    reopen = t["status"] != "running"
    ev = {
        "id": t["id"],
        "sent": round(now - 0.5, 3),
        "message": cut(text, 300),
        "allow": merged_allow or None,
        "denied": [],
        "notified": False,
    }
    if reopen:
        b = t.get("billed") or {}
        neg = {k: -v for k, v in (b.get("tokens") or {}).items()}
        ev.update(
            status="running",
            prev_status=t["status"],
            attempts=(t.get("attempts") or 1) + 1,
            cost=-(b.get("cost") or 0),
            tokens=neg or None,
            billed=None,
        )
    append(rd, **ev)
    spawn_watcher(rd, "gski.ocq")
    print(f"{t['id']} sent ({delivery}){' -> running' if reopen else ''}")


def cmd_abort(args):
    rd = run_dir(args.run)
    cfg = load_cfg(rd)
    tasks = fold(rd)
    by_orch = bool(cfg.get("orchestrator") and os.environ.get("OPENCODE_SESSION_ID") == cfg.get("orchestrator"))
    ids = resolve(tasks, args.ids) if args.ids else [t["id"] for t in tasks.values() if t["status"] == "running"]
    for tid in ids:
        t = tasks[tid]
        if t["status"] != "running":
            print(f"{tid} not running")
            continue
        bg = shells(t["session"], cfg["dir"]) or []
        for s in bg:
            kill_shell(s["id"], cfg["dir"])
        interrupt(t["session"])
        for _ in range(10 if bg else 0):
            time.sleep(0.5)
            if t["session"] in (active() or {}):
                interrupt(t["session"])
        append(rd, id=tid, status="failed", worker="failed", note="aborted", finished=int(time.time()), notified=by_orch)
        print(f"{tid} aborted -> failed")
    ensure_watch(rd)


def cmd_serve(args):
    print(f"run workers against it with: OCQ_URL=http://127.0.0.1:{args.port} (set OCQ_PASSWORD if the server needs one)", file=sys.stderr)
    os.execvp("opencode", ["opencode", "serve", "--port", str(args.port), "--hostname", "127.0.0.1"])
