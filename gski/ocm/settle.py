import time
from pathlib import Path

from gski.oc_lib.api import (
    active,
    assistants,
    err_text,
    messages,
    pending_input,
    session_info,
    shells,
    sweep,
    try_send_synthetic,
    turn_text,
)
from gski.oc_lib.common import cut, known_projects, sum_tokens
from gski.oc_lib.watch import notify, run_watcher, spawn_watcher
from gski.ocm.state import append, fold, ocq_runs, read_manager, summary


def has_child_work(s, live):
    sid, d = s["session"], s["dir"]
    if shells(sid, d) != []:
        return True
    if any(nrun > 0 for _, _, _, nrun in ocq_runs(s)):
        return True
    if any(aid != sid and session_info(aid).get("parentID") == sid for aid in (live or {})):
        return True
    return False


def settle_event(s, live):
    sid = s["session"]
    msgs = messages(sid, limit=20)
    asst = assistants(msgs)
    last = asst[0] if asst else None
    sent = s.get("sent") or s.get("started") or 0
    if sent and time.time() - sent < 120 and not (last and (last.get("time") or {}).get("created", 0) / 1000 >= sent):
        return None
    if last and pending_input(msgs):
        return None
    if has_child_work(s, live):
        return None
    if not last and active() is None:
        return None
    info = session_info(sid)
    if not last:
        if time.time() - (s.get("started") or 0) < 120:
            return None
        err = "no response from orchestrator"
    elif last.get("error"):
        err = err_text(last["error"])
    elif not (last.get("time") or {}).get("completed"):
        return None
    elif info.get("outcome") in ("failed", "interrupted"):
        err = f"session {info['outcome']}"
    else:
        err = None
    full_reply = err or turn_text(msgs).strip() or "(no text reply)"
    cost = round(info.get("cost") or 0, 4)
    tokens = sum_tokens([info.get("tokens")]) if info.get("tokens") else None
    ev = {
        "id": s["id"],
        "status": "reported",
        "note": cut(full_reply, 240),
        "error": err,
        "cost": cost,
        "tokens": tokens,
        "finished": int(time.time()),
    }
    return ev, full_reply


def format_report(s, full_reply, runs, streams):
    tag = "error" if s.get("error") else "reported"
    w_cost = sum(r[2] for r in runs)
    ocq_part = f" (+ ${w_cost:.2f} ocq)" if w_cost else ""
    head = [f"[ocm/{s['id']} {tag} | cost ${s.get('cost', 0):.2f}{ocq_part}]"]
    for d in s.get("denied") or []:
        head.append(f"denied: {d}")
    for rname, rsum, _, _ in runs:
        head.append(f"ocq/{rname}: {rsum}")
    body = full_reply if len(full_reply) <= 4000 else full_reply[:4000] + f"\n… (truncated; run `gski ocm show {s['id']}`)"
    return "\n".join(head) + "\n\n" + body + "\n\n" + summary(streams)


def step_ocm(base):
    streams = fold(base)
    running = {s["session"]: s for s in streams.values() if s["status"] == "running" and s.get("session")}
    if not running:
        return "empty"
    sweep(base, {sid: s["id"] for sid, s in running.items()}, append)
    live = active()
    if live is None:
        return "wait"
    candidates = [s for sid, s in running.items() if sid not in live and not has_child_work(s, live)]
    if not candidates:
        return "wait"
    time.sleep(2)
    streams = fold(base)
    running = {s["session"]: s for s in streams.values() if s["status"] == "running" and s.get("session")}
    sweep(base, {sid: s["id"] for sid, s in running.items()}, append)
    live = active()
    if live is None:
        return "wait"
    for c in candidates:
        s = running.get(c["session"])
        if not s or c["session"] in live:
            continue
        res = settle_event(s, live)
        if not res:
            continue
        ev, full_reply = res
        preview = {k: dict(v) for k, v in fold(base).items()}
        preview[s["id"]].update(ev)
        runs = ocq_runs(s)
        mgr = read_manager(base, s)
        if mgr:
            try_send_synthetic(mgr, format_report(preview[s["id"]], full_reply, runs, preview), f"ocm/{s['id']}")
        append(base, **ev)
        if not mgr:
            tag = "error" if ev["error"] else "reported"
            notify(f"ocm/{s['id']}: {tag} | {cut(ev['note'], 80)}", "rgb(fb4934)" if ev["error"] else "rgb(d79921)")
    return "wait" if any(s["status"] == "running" for s in fold(base).values()) else "empty"


def ensure_watch(base):
    if (base / "ledger.jsonl").exists() and any(s["status"] == "running" for s in fold(base).values()):
        spawn_watcher(base, "gski.ocm")


def manager_waiting(sid, directory=None):
    if not sid:
        return False
    roots = []
    if directory:
        d = Path(directory)
        roots.extend([d, *d.parents])
    roots.extend(Path(p) for p in known_projects())
    seen = set()
    for r in roots:
        try:
            r = r.resolve()
        except OSError:
            continue
        if r in seen:
            continue
        seen.add(r)
        base = r / ".ocm"
        if not (base / "ledger.jsonl").exists():
            continue
        for s in fold(base).values():
            if s.get("status") == "running" and read_manager(base, s) == sid:
                ensure_watch(base)
                return True
    return False


def watch_ocm(base):
    base = Path(base)
    run_watcher(
        base,
        has_running=lambda: any(s["status"] == "running" for s in fold(base).values()),
        running_sids=lambda: {s["session"]: s["id"] for s in fold(base).values() if s["status"] == "running" and s.get("session")},
        on_perm=lambda sid, name: sweep(base, {sid: name}, append),
        step=lambda: step_ocm(base),
    )
