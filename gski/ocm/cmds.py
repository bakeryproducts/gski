import os
import time
from pathlib import Path

from gski.oc_lib.api import (
    active,
    create_session,
    interrupt,
    kill_shell,
    messages,
    send_prompt,
    send_synthetic,
    set_permissions,
    shells,
    try_send_synthetic,
    turn_text,
)
from gski.oc_lib.common import NAME_RE, cut, die, remember
from gski.oc_lib.watch import fmt_dur, spawn_watcher
from gski.ocm.settle import ensure_watch
from gski.ocm.state import (
    PARENT_TARGETS,
    ago,
    append,
    base_dir,
    build_prompt,
    caller_stream,
    ensure_base,
    fold,
    get_stream,
    ocm_root,
    ocq_runs,
    read_manager,
    rules_for,
    stream_dur,
    summary,
    task_dur,
    touch_manager,
    worker_row,
)


def cmd_start(args):
    if args.name in PARENT_TARGETS or not NAME_RE.match(args.name):
        die(f"invalid stream name: {args.name}")
    base = ensure_base()
    streams = fold(base)
    if args.name in streams:
        die(f"stream already exists: {args.name} (use send to continue it, or pick a new name)")
    d = str(Path(args.dir).expanduser().resolve()) if args.dir else str(Path.cwd().resolve())
    if not Path(d).is_dir():
        die(f"directory not found: {d}")
    remember(d)
    mgr = touch_manager(base, streams)
    allow = list(args.allow or [])
    meta = {"ocm_root": str(base.parent), "stream": args.name}
    s, used = create_session(f"ocm/{args.name}", "orchestrator", args.model, rules_for(allow), d, meta)
    now = time.time()
    send_prompt(s["id"], build_prompt(args.name, args.text))
    append(
        base,
        id=args.name,
        status="running",
        session=s["id"],
        dir=d,
        model=used,
        task=args.text,
        allow=allow,
        started=int(now),
        sent=round(now - 0.5, 3),
        **({"manager": mgr} if mgr else {}),
    )
    spawn_watcher(base, "gski.ocm")
    print(f"{args.name} running {s['id']} [{used}] ({d})")


def _worker_tag(t):
    a = t.get("agent") or "worker"
    m = (t.get("model") or "hydrogen").split("/")[-1].split("#")[0].replace("gemini-4-", "")
    return f"[{a}/{m}]"


def _live_session(sid, directory, live, now, limit=15):
    is_active = bool(live and sid in live)
    bg = [] if is_active else (shells(sid, directory) or [] if directory else [])
    msgs = messages(sid, limit=limit) if sid else []
    last_ts = None
    for m in msgs:
        if m.get("type") == "assistant":
            tm = m.get("time") or {}
            ms = tm.get("completed") or tm.get("streamed") or tm.get("created")
            if ms:
                last_ts = ms / 1000
                break
    tool_str = None
    tool_running = False
    for m in msgs:
        for c in reversed(m.get("content") or []):
            if c.get("type") != "tool":
                continue
            tname = c.get("name") or "tool"
            st = c.get("state") or {}
            tstat = st.get("status") or ""
            inp = st.get("input") or {}
            detail = inp.get("command") or inp.get("path") or inp.get("pattern") or inp.get("url") or inp.get("description") or ""
            ctm = c.get("time") or {}
            if tstat == "running" and is_active:
                tool_running = True
                ms = ctm.get("ran") or ctm.get("created")
                tdur = f" ({fmt_dur(now - ms / 1000)})" if ms else ""
                tool_str = f"running {tname}{tdur}: `{cut(detail, 70)}`" if detail else f"running {tname}{tdur}"
            else:
                ms = ctm.get("completed") or ctm.get("ran") or ctm.get("created")
                when = f" {ago(ms / 1000, now)}" if ms else ""
                err = " [error]" if tstat == "error" else ""
                tool_str = f"last tool{when}: {tname}{err} `{cut(detail, 70)}`" if detail else f"last tool{when}: {tname}{err}"
            break
        if tool_str:
            break
    return is_active, bg, last_ts, tool_running, tool_str, turn_text(msgs)


def cmd_ls(args):
    base = ocm_root() / ".ocm"
    streams = fold(base) if (base / "ledger.jsonl").exists() else {}
    if streams:
        touch_manager(base, streams)
        ensure_watch(base)
    if not streams:
        print("no streams")
        return
    now = time.time()
    print(summary(streams))
    visible = [s for s in streams.values() if not args.status or s["status"] in args.status]
    if visible:
        print()
    w = max((len(s["id"]) for s in visible), default=0)
    for s in visible:
        denied = f" [denied {len(s['denied'])}]" if s.get("denied") else ""
        if s["status"] in ("reported", "done", "failed") and s.get("note"):
            info = s["note"]
        elif s["status"] == "running" and s.get("msg"):
            when = f" {ago(s['msg_at'], now)}" if s.get("msg_at") else ""
            info = f"msg{when}: {s['msg']}"
        else:
            info = s.get("task", "")
        print(f"{s['id']:<{w}}  {s['status']:<8}  {stream_dur(s, now):<6}{denied} | {cut(info, 110)}")
        if s["status"] in ("running", "reported") or args.all:
            for rname, rsum, tasks, _ in ocq_runs(s, now):
                print("  " + cut(f"ocq/{rname}: {rsum}", 140))
                for t in tasks.values():
                    print("    " + worker_row(t, now))


def cmd_show(args):
    base = base_dir()
    streams = fold(base)
    touch_manager(base, streams)
    ensure_watch(base)
    s = get_stream(streams, args.name)
    now = time.time()
    runs = ocq_runs(s, now)
    need_live = s["status"] == "running" or any(nrun for _, _, _, nrun in runs)
    live = active() if need_live else None
    sid = s.get("session")
    o_active, o_bg, o_last_ts, o_tool_run, o_tool, o_reply = (
        _live_session(sid, s.get("dir"), live, now, limit=30) if sid else (False, [], None, False, None, "")
    )
    model = (s.get("model") or "-").split(" ")[0].replace("google/", "")
    if s["status"] == "running":
        if o_active:
            ostate = f"active ({o_tool})" if o_tool_run and o_tool else "active"
        elif o_bg:
            ms = (o_bg[0].get("time") or {}).get("started")
            sdur = f" ({fmt_dur(now - ms / 1000)})" if ms else ""
            ostate = f"bg shell{sdur}: `{cut(o_bg[0].get('command', ''), 60)}`"
        else:
            wait = "waiting on ocq" if any(nrun for _, _, _, nrun in runs) else "idle"
            turn = f", last turn {ago(o_last_ts, now)}" if o_last_ts else ""
            ostate = f"idle ({wait}{turn})" if wait != "idle" or turn else "idle"
    else:
        fin = s.get("finished") or s.get("updated")
        ostate = f"{s['status']} ({ago(fin, now)})" if fin else s["status"]

    print(f"{s['id']}  {s['status']}  {stream_dur(s, now)}")
    print(f"orchestrator: {ostate}  model: {model}")
    if args.full:
        print(f"session: {s.get('session', '-')}  dir: {s.get('dir')}")
        if s.get("allow"):
            print(f"allow: {', '.join(s['allow'])}")
        print(f"task: {s.get('task')}")
    if s.get("error"):
        print(f"error: {s['error']}")
    if s.get("msg"):
        when = f" ({ago(s['msg_at'], now)})" if s.get("msg_at") else ""
        print(f"msg{when}: {s['msg']}")
    if s.get("note") and s["status"] in ("done", "failed"):
        print(f"note: {s['note']}")
    for d in s.get("denied") or []:
        print(f"denied: {d}")

    for rname, rsum, tasks, _ in runs:
        print(f"\nocq/{rname} ({rsum}):")
        for t in tasks.values():
            if t["status"] != "running":
                print("  " + worker_row(t, now))
                for d in t.get("denied") or []:
                    print(f"    denied: {d}")
                continue
            att = f" a{t['attempts']}" if (t.get("attempts") or 0) > 1 else ""
            denied = f" [denied {len(t['denied'])}]" if t.get("denied") else ""
            print(f"  {t['id']} running  {task_dur(t, now):<6}  {_worker_tag(t)}{att}{denied}")
            print(f"    task: {cut(t.get('task', ''), 130)}")
            for d in t.get("denied") or []:
                print(f"    denied: {d}")
            wsid = t.get("session")
            if wsid:
                w_active, w_bg, w_last_ts, w_tool_run, w_tool, w_reply = _live_session(wsid, s.get("dir"), live, now, limit=10)
                parts = []
                if w_active:
                    parts.append(f"active, {w_tool}" if w_tool_run and w_tool else "active")
                    if w_tool and not w_tool_run:
                        parts.append(w_tool)
                elif w_bg:
                    ms = (w_bg[0].get("time") or {}).get("started")
                    sdur = f" ({fmt_dur(now - ms / 1000)})" if ms else ""
                    parts.append(f"bg shell{sdur}: `{cut(w_bg[0].get('command', ''), 65)}`")
                    if w_tool:
                        parts.append(w_tool)
                else:
                    parts.append(f"idle (last turn {ago(w_last_ts, now)})" if w_last_ts else "idle")
                    if w_tool:
                        parts.append(w_tool)
                print("    live: " + " | ".join(parts))
                if t.get("msg"):
                    when = f" ({ago(t['msg_at'], now)})" if t.get("msg_at") else ""
                    print(f"    msg{when}: {cut(t['msg'], 130)}")
                if w_reply:
                    print(f"    last: {cut(w_reply, 130)}")

    if o_reply:
        if s["status"] == "running":
            hdr = f"--- O last reply ({ago(o_last_ts, now)}) ---" if o_last_ts else "--- O last reply ---"
        else:
            hdr = "--- O report ---"
        print(f"\n{hdr}")
        print(o_reply[: args.chars])


def cmd_send(args):
    caller = os.environ.get("OPENCODE_SESSION_ID")
    mine = caller_stream(caller) if caller else None
    if mine:
        base, _, s = mine
        if args.name not in PARENT_TARGETS:
            die("orchestrator can only send to ..")
        if args.allow:
            die("--allow is only for manager -> stream")
        mgr = read_manager(base, s)
        if not mgr:
            die("no manager session recorded in .ocm/ocm.json")
        send_synthetic(mgr, f"[ocm/{s['id']}]\n{args.text}", f"ocm/{s['id']}")
        append(base, id=s["id"], msg=cut(args.text, 300))
        print(f"{s['id']} -> .. sent")
        return
    if args.name in PARENT_TARGETS:
        die("not in an orchestrator session")
    base = base_dir()
    streams = fold(base)
    s = get_stream(streams, args.name)
    if s["status"] == "failed" or not s.get("session"):
        die(f"{s['id']} is {s['status']}: cannot send (start a new stream)")
    mgr = touch_manager(base, streams)
    allow = list(dict.fromkeys((s.get("allow") or []) + list(args.allow or [])))
    set_permissions(s["session"], "orchestrator", rules_for(allow), s.get("dir"))
    was = s["status"]
    delivery = "queue" if args.queue else "steer"
    head = '[ocm manager — mid-run reply via `gski ocm send .. "..."`]' if was == "running" else "[ocm manager]"
    now = time.time()
    send_prompt(s["session"], f"{head}\n{args.text}", delivery)
    append(
        base,
        id=s["id"],
        status="running",
        sent=round(now - 0.5, 3),
        message=cut(args.text, 300),
        allow=allow,
        denied=[],
        error=None,
        **({"manager": mgr} if mgr else {}),
    )
    spawn_watcher(base, "gski.ocm")
    arrow = " -> running" if was != "running" else ""
    print(f"{s['id']} sent ({delivery}){arrow}")


def cmd_mark(args, status):
    base = base_dir()
    streams = fold(base)
    s = get_stream(streams, args.name)
    if s["status"] == "running":
        die(f"{s['id']} is running, abort first")
    touch_manager(base, streams)
    ev = {"id": s["id"], "status": status}
    if args.note:
        ev["note"] = args.note
    append(base, **ev)
    print(f"{s['id']} {status}")


def cmd_abort(args):
    base = base_dir()
    streams = fold(base)
    touch_manager(base, streams)
    targets = [get_stream(streams, args.name)] if args.name else [s for s in streams.values() if s["status"] == "running"]
    for s in targets:
        if s["status"] != "running":
            print(f"{s['id']} not running")
            continue
        sid, d = s["session"], s["dir"]
        bg = shells(sid, d) or []
        for sh in bg:
            kill_shell(sh["id"], d)
        interrupt(sid)
        for _ in range(10 if bg else 0):
            time.sleep(0.5)
            if sid in (active() or {}):
                interrupt(sid)
        mgr = read_manager(base, s)
        if mgr and os.environ.get("OPENCODE_SESSION_ID") != mgr:
            try_send_synthetic(mgr, f"[ocm/{s['id']} aborted]\naborted externally", f"ocm/{s['id']}")
        append(base, id=s["id"], status="reported", note="aborted")
        print(f"{s['id']} aborted -> reported")
        for rname, _, _, nrun in ocq_runs(s):
            if nrun:
                print(f"  note: ocq/{rname} in {d} still has {nrun} running worker(s) (gski ocq abort {rname})")
