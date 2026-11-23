import json
import os
import time
from pathlib import Path

from gski.oc_lib.api import session_info
from gski.oc_lib.common import append_jsonl, cut, die, known_projects, parse_allow, remember
from gski.oc_lib.watch import fmt_dur
from gski.ocq.state import fold as fold_ocq, short_model

PARENT_TARGETS = ("..", "manager", "parent")

OCM_RULES = [
    {"action": "question", "resource": "*", "effect": "deny"},
    {"action": "shell", "resource": "gski ocm*", "effect": "deny"},
    {"action": "shell", "resource": "gski ocm send *", "effect": "allow"},
    {"action": "external_directory", "resource": "/tmp/opencode/**", "effect": "allow"},
]


def ocm_root():
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        if (d / ".ocm").is_dir():
            return d
    return cwd


def ensure_base():
    root = ocm_root()
    base = root / ".ocm"
    base.mkdir(exist_ok=True)
    gi = base / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n")
    remember(root)
    return base


def base_dir(must=True):
    base = ocm_root() / ".ocm"
    if must and not (base / "ledger.jsonl").exists():
        die("no ocm streams in this project")
    return base


def append(base, **ev):
    append_jsonl(base / "ledger.jsonl", **ev)


def fold(base):
    streams = {}
    p = base / "ledger.jsonl"
    if not p.exists():
        return streams
    for line in p.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        s = streams.setdefault(ev["id"], {"id": ev["id"], "cost": 0})
        ts = ev.pop("t", None)
        s["updated"] = ts
        if "msg" in ev:
            if ev["msg"]:
                s["msg_at"] = ts
            else:
                s.pop("msg_at", None)
        denied = ev.pop("denied", None)
        if denied == []:
            s.pop("denied", None)
        elif denied:
            s.setdefault("denied", []).append(denied)
        s.update(ev)
    return streams


def get_stream(streams, name):
    if name not in streams:
        die(f"unknown stream: {name}")
    return streams[name]


def manager_sid(streams=None):
    sid = os.environ.get("OPENCODE_SESSION_ID")
    if not sid:
        return None
    if streams and any(s.get("session") == sid for s in streams.values()):
        return None
    return sid


def touch_manager(base, streams=None):
    remember(base.parent)
    sid = manager_sid(streams if streams is not None else fold(base))
    if not sid:
        return None
    p = base / "ocm.json"
    try:
        cfg = json.loads(p.read_text()) if p.exists() else {}
    except (OSError, ValueError):
        cfg = {}
    if cfg.get("manager") != sid:
        cfg["manager"] = sid
        p.write_text(json.dumps(cfg, indent=2) + "\n")
    return sid


def read_manager(base, s):
    p = base / "ocm.json"
    try:
        mgr = json.loads(p.read_text()).get("manager") if p.exists() else None
    except (OSError, ValueError):
        mgr = None
    return mgr or s.get("manager")


def caller_stream(sid):
    if not sid:
        return None
    roots = []
    local = ocm_root()
    if (local / ".ocm" / "ledger.jsonl").exists():
        roots.append(local)
    meta = session_info(sid).get("metadata") or {}
    if meta.get("ocm_root"):
        roots.append(Path(meta["ocm_root"]))
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
        streams = fold(base)
        for s in streams.values():
            if s.get("session") == sid:
                return base, streams, s
    return None


def rules_for(allow):
    return OCM_RULES + [parse_allow(a) for a in allow or []]


def build_prompt(name, text):
    return (
        f"ocm stream: {name}\n"
        "Upstream is a Manager session. Execution is pre-approved within the goal, constraints, and permissions below: "
        "plan and run Round 1 directly, then report concrete results "
        "(stop early only on a genuine scope contradiction or missing permission, naming the needed --allow rule so Manager can grant it and resume).\n"
        "The question tool is disabled; upstream receives your final report automatically when all work finishes, "
        'or mid-run messages via: gski ocm send .. "..."\n\n'
        f"Task:\n{text}"
    )


def ocq_run_dirs(s):
    d = Path(s["dir"])
    roots = [d, *d.parents, *(Path(p) for p in known_projects())]
    seen = set()
    out = []
    for root in roots:
        try:
            root = root.resolve()
        except OSError:
            continue
        if root in seen:
            continue
        seen.add(root)
        runs_dir = root / ".ocq" / "runs"
        if not runs_dir.is_dir():
            continue
        for rd in sorted(runs_dir.iterdir()):
            cfg_p = rd / "run.json"
            if not cfg_p.exists():
                continue
            try:
                cfg = json.loads(cfg_p.read_text())
            except (OSError, ValueError):
                continue
            if cfg.get("orchestrator") == s.get("session"):
                out.append(rd)
    return out


def ago(ts, now=None):
    return f"{fmt_dur((now or time.time()) - ts)} ago" if ts else ""


def stream_dur(s, now=None):
    if not s.get("started"):
        return "-"
    now = now or time.time()
    end = now if s["status"] == "running" else (s.get("finished") or s.get("updated") or now)
    return fmt_dur(end - s["started"])


def task_dur(t, now=None):
    if not t.get("started"):
        return "-"
    now = now or time.time()
    end = now if t["status"] == "running" else (t.get("finished") or t.get("updated") or now)
    return fmt_dur(end - t["started"])


def run_summary(tasks, now=None):
    now = now or time.time()
    counts = {}
    for t in tasks.values():
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    order = ["running", "done", "failed", "reported", "pending"]
    if tasks and counts == {"done": len(tasks)}:
        stat = f"{len(tasks)}/{len(tasks)} done"
    else:
        stat = ", ".join(f"{counts[k]} {k}" for k in order if counts.get(k)) or "empty"
    starts = [t["started"] for t in tasks.values() if t.get("started")]
    if not starts:
        return stat
    end = now if counts.get("running") else max(t.get("finished") or t.get("updated") or now for t in tasks.values())
    return f"{stat} | {fmt_dur(end - min(starts))}"


def worker_row(t, now=None):
    now = now or time.time()
    dur = f"{task_dur(t, now):<6}"
    st = f"{t['status']:<8}"
    tier = short_model(t)
    att = f" a{t['attempts']}" if (t.get("attempts") or 0) > 1 else ""
    denied = f" [denied {len(t['denied'])}]" if t.get("denied") else ""
    if t["status"] in ("done", "failed", "reported"):
        art = t.get("artifact") or "-"
        note = t.get("note") or ""
        info = f"{art} | {note}" if note else str(art)
    elif t["status"] == "running" and t.get("msg"):
        when = f" {ago(t['msg_at'], now)}" if t.get("msg_at") else ""
        info = f"msg{when}: {t['msg']} | {t.get('task', '')}"
    else:
        info = t.get("task", "")
    return f"{t['id']} {st} {dur}{tier}{att}{denied}  {cut(info, 115)}"


def ocq_runs(s, now=None):
    out = []
    for rd in ocq_run_dirs(s):
        tasks = fold_ocq(rd)
        running = sum(1 for t in tasks.values() if t.get("status") == "running")
        out.append((rd.name, run_summary(tasks, now), tasks, running))
    return out


def summary(streams):
    counts = {}
    for s in streams.values():
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    order = ["running", "reported", "done", "failed"]
    parts = [f"{k} {counts[k]}" for k in order if counts.get(k)]
    return f"{len(streams)} streams: " + (", ".join(parts) or "empty")
