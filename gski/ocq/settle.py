import json
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
from gski.oc_lib.common import cut, sum_tokens
from gski.oc_lib.watch import fmt_dur, notify, run_watcher, spawn_watcher
from gski.ocq.state import append, fold, load_cfg, row, summary


def settle_event(rd, cfg, t):
    msgs = messages(t["session"])
    asst = assistants(msgs)
    last = asst[0] if asst else None
    sent = t.get("sent") or t.get("started") or 0
    if sent and time.time() - sent < 120 and not (last and (last.get("time") or {}).get("created", 0) / 1000 >= sent):
        return None
    if last and pending_input(msgs):
        return None
    result = rd / "results" / f"{t['id']}.json"
    fresh = result.exists() and result.stat().st_mtime >= (sent - 1 if sent else 0)
    if not fresh and shells(t["session"], cfg["dir"]) != []:
        return None
    if not last and active() is None:
        return None
    info = session_info(t["session"])
    if not last:
        if time.time() - (t.get("started") or 0) < 120:
            return None
        err = "no response from agent"
    elif last.get("error"):
        err = err_text(last["error"])
    elif not (last.get("time") or {}).get("completed"):
        return None
    elif info.get("outcome") in ("failed", "interrupted"):
        err = f"session {info['outcome']}"
    else:
        err = None

    reply = cut(turn_text(msgs), 200)
    art = t.get("artifact")
    if fresh:
        try:
            r = json.loads(result.read_text())
            status = "done" if r.get("status") == "done" and not err else "failed"
            art = r.get("artifact")
            note = r.get("note") or err or reply
        except (OSError, json.JSONDecodeError, AttributeError):
            status, note = "failed", err or f"invalid results/{t['id']}.json | {reply}"
    elif err:
        status, note = "failed", err
    elif t.get("prev_status") == "done":
        status, note = "done", reply or t.get("note")
    else:
        status, note = "failed", f"missing results/{t['id']}.json | {reply}"

    cost = round(info.get("cost") or sum(m.get("cost") or 0 for m in asst), 4)
    tokens = sum_tokens([info.get("tokens")] if info.get("tokens") else (m.get("tokens") for m in asst))
    return {
        "id": t["id"],
        "status": status,
        "worker": status,
        "artifact": art,
        "note": note,
        "cost": cost,
        "tokens": tokens,
        "billed": {"cost": cost, "tokens": tokens},
        "finished": int(time.time()),
    }


def preview_tasks(tasks, settled):
    out = {tid: dict(t) for tid, t in tasks.items()}
    for ev in settled:
        t = out[ev["id"]]
        ev_copy = dict(ev)
        t["cost"] = round(t.get("cost", 0) + (ev_copy.pop("cost", 0) or 0), 4)
        tk = ev_copy.pop("tokens", None)
        if tk:
            t["tokens"] = sum_tokens([t.get("tokens"), tk])
        t.update(ev_copy)
    return out


def emit_settled(rd, cfg, settled, final_tasks):
    settled_ids = {ev["id"] for ev in settled}
    wave = [
        final_tasks[tid]
        for tid, t in final_tasks.items()
        if tid in settled_ids or (t["status"] in ("done", "failed") and t.get("notified") is False)
    ]
    orch_sid = cfg.get("orchestrator")
    still_running = [tid for tid, t in final_tasks.items() if t["status"] == "running"]
    if wave and orch_sid:
        lines = [f"[ocq/{rd.name}]"]
        for t in wave:
            lines.append(row(t))
            for d in t.get("denied") or []:
                lines.append(f"  denied: {d}")
        if still_running:
            lines.append(f"still running: {', '.join(still_running)}")
        lines.append(summary(final_tasks))
        try_send_synthetic(orch_sid, "\n".join(lines), f"ocq/{rd.name}")
    for ev in settled:
        append(rd, **ev, notified=True)
    for t in wave:
        if t["id"] not in settled_ids:
            append(rd, id=t["id"], notified=True)
    if wave and not still_running:
        in_ocm = bool(orch_sid and str(session_info(orch_sid).get("title") or "").startswith("ocm/"))
        if not in_ocm:
            bad = any(t["status"] == "failed" for t in final_tasks.values())
            starts = [t["started"] for t in final_tasks.values() if t.get("started")]
            ends = [t["finished"] for t in final_tasks.values() if t.get("finished")]
            took = f" | {fmt_dur(max(ends) - min(starts))}" if starts and ends else ""
            notify(f"{rd.name}: {summary(final_tasks).split(' | ')[0]}{took}", "rgb(fb4934)" if bad else "rgb(d79921)")


def step_run(rd):
    cfg = load_cfg(rd)
    tasks = fold(rd)
    running = {t["session"]: t for t in tasks.values() if t["status"] == "running" and t.get("session")}
    if not running:
        if any(t["status"] in ("done", "failed") and t.get("notified") is False for t in tasks.values()):
            emit_settled(rd, cfg, [], tasks)
        return "empty"
    sweep(rd, {sid: t["id"] for sid, t in running.items()}, append)
    live = active()
    if live is None:
        return "wait"
    candidates = [t for sid, t in running.items() if sid not in live]
    if not candidates:
        return "wait"
    need_pause = any(
        not (
            (rd / "results" / f"{t['id']}.json").exists()
            and (rd / "results" / f"{t['id']}.json").stat().st_mtime >= (t.get("sent") or t.get("started") or 0) - 1
        )
        for t in candidates
    )
    if need_pause:
        time.sleep(1.5)
        cfg = load_cfg(rd)
        tasks = fold(rd)
        running = {t["session"]: t for t in tasks.values() if t["status"] == "running" and t.get("session")}
        sweep(rd, {sid: t["id"] for sid, t in running.items()}, append)
        live = active()
        if live is None:
            return "wait"
    settled = []
    for c in candidates:
        t = running.get(c["session"])
        if t and c["session"] not in live:
            ev = settle_event(rd, cfg, t)
            if ev:
                settled.append(ev)
    if not settled:
        return "wait"
    final_tasks = preview_tasks(fold(rd), settled)
    emit_settled(rd, load_cfg(rd), settled, final_tasks)
    return "wait" if any(t["status"] == "running" for t in final_tasks.values()) else "empty"


def needs_watch(rd):
    return any(
        t["status"] == "running" or (t["status"] in ("done", "failed") and t.get("notified") is False)
        for t in fold(rd).values()
    )


def ensure_watch(rd):
    if needs_watch(rd):
        spawn_watcher(rd, "gski.ocq")


def watch_run(rd):
    rd = Path(rd)
    run_watcher(
        rd,
        has_running=lambda: needs_watch(rd),
        running_sids=lambda: {t["session"]: t["id"] for t in fold(rd).values() if t["status"] == "running" and t.get("session")},
        on_perm=lambda sid, tid: sweep(rd, {sid: tid}, append),
        step=lambda: step_run(rd),
    )
