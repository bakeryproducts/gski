import os
import time
from pathlib import Path

from gski.oc_lib.api import (
    active,
    api,
    create_session,
    interrupt,
    kill_shell,
    messages,
    send_prompt,
    send_synthetic,
    session_info,
    shells,
    try_send_synthetic,
    turn_text,
)
from gski.oc_lib.common import NAME_RE, cut, die, remember
from gski.oc_lib.watch import spawn_watcher
from gski.ocm.settle import ensure_watch
from gski.ocm.state import (
    PARENT_TARGETS,
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
    summary,
    touch_manager,
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


def cmd_ls(args):
    base = ocm_root() / ".ocm"
    streams = fold(base) if (base / "ledger.jsonl").exists() else {}
    if streams:
        touch_manager(base, streams)
        ensure_watch(base)
    if not streams:
        print("no streams")
        return
    print(summary(streams))
    for s in streams.values():
        if args.status and s["status"] not in args.status:
            continue
        cost = s.get("cost") or 0
        if s["status"] == "running" and s.get("session"):
            cost = max(cost, session_info(s["session"]).get("cost") or 0)
        denied = f" [denied {len(s['denied'])}]" if s.get("denied") else ""
        if s["status"] in ("reported", "done", "failed") and s.get("note"):
            info = s["note"]
        elif s["status"] == "running" and s.get("msg"):
            info = f"msg: {s['msg']}"
        else:
            info = s.get("task", "")
        print(cut(f"{s['id']} {s['status']} ${cost:.2f}{denied} | {info}"))
        for rname, rsum, _, _ in ocq_runs(s):
            print(cut(f"  ocq/{rname}: {rsum}"))


def cmd_show(args):
    base = base_dir()
    streams = fold(base)
    touch_manager(base, streams)
    ensure_watch(base)
    s = get_stream(streams, args.name)
    cost = s.get("cost") or 0
    if s["status"] == "running" and s.get("session"):
        cost = max(cost, session_info(s["session"]).get("cost") or 0)
    print(f"id: {s['id']}  status: {s['status']}  session: {s.get('session', '-')}  cost: ${cost:.4f}")
    print(f"dir: {s.get('dir')}  model: {s.get('model', '-')}")
    if s.get("allow"):
        print(f"allow: {', '.join(s['allow'])}")
    print(f"task: {s.get('task')}")
    if s.get("note"):
        print(f"note: {s['note']}")
    if s.get("msg"):
        print(f"msg: {s['msg']}")
    for d in s.get("denied") or []:
        print(f"denied: {d}")
    for rname, rsum, _, _ in ocq_runs(s):
        print(f"ocq/{rname}: {rsum}")
    if s.get("session"):
        txt = turn_text(messages(s["session"], limit=30))
        if txt:
            print("--- last reply ---")
            print(txt[: args.chars])


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
    api("PATCH", f"/api/session/{s['session']}", {"permissions": rules_for(allow)})
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
