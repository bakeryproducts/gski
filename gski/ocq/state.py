import json
import os
from pathlib import Path

from gski.oc_lib.api import session_info
from gski.oc_lib.common import (
    NAME_RE,
    append_jsonl,
    cut,
    die,
    known_projects,
    parse_allow,
    remember,
    rules_from,
    sum_tokens,
)

PARENT_TARGETS = ("..", "orchestrator", "parent")

BASE_RULES = [
    {"action": "subagent", "resource": "*", "effect": "deny"},
    {"action": "question", "resource": "*", "effect": "deny"},
    {"action": "shell", "resource": "gski ocq*", "effect": "deny"},
    {"action": "shell", "resource": "gski ocq send *", "effect": "allow"},
    {"action": "external_directory", "resource": "/tmp/opencode/**", "effect": "allow"},
]

DEFAULT_CFG = {
    "agent": "worker",
    "model": None,
    "allow": [],
    "permission": {},
    "orchestrator": None,
}


def project_root():
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        if (d / ".ocq").is_dir():
            return d
    return cwd


def append(rd, **ev):
    append_jsonl(rd / "ledger.jsonl", **ev)


def fold(rd):
    tasks = {}
    p = rd / "ledger.jsonl"
    if not p.exists():
        return tasks
    for line in p.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = tasks.setdefault(ev["id"], {"id": ev["id"], "attempts": 0})
        t["updated"] = ev.pop("t", None)
        denied = ev.pop("denied", None)
        if denied == []:
            t.pop("denied", None)
        elif denied:
            t.setdefault("denied", []).append(denied)
        t["cost"] = round(t.get("cost", 0) + (ev.pop("cost", 0) or 0), 4)
        tk = ev.pop("tokens", None)
        if tk:
            t["tokens"] = sum_tokens([t.get("tokens"), tk])
        t.update(ev)
    return tasks


def touch_orchestrator(rd):
    sid = os.environ.get("OPENCODE_SESSION_ID")
    if not sid:
        return
    cfg_path = rd / "run.json"
    if not cfg_path.exists() or any(t.get("session") == sid for t in fold(rd).values()):
        return
    try:
        cfg = json.loads(cfg_path.read_text())
        if cfg.get("orchestrator") != sid:
            cfg["orchestrator"] = sid
            cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    except (OSError, ValueError):
        pass


def ensure_run(run, allow=None):
    if run in PARENT_TARGETS or not NAME_RE.match(run):
        die(f"invalid run name: {run}")
    root = project_root()
    base = root / ".ocq"
    base.mkdir(exist_ok=True)
    gi = base / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n")
    rd = base / "runs" / run
    (rd / "results").mkdir(parents=True, exist_ok=True)
    cfg_path = rd / "run.json"
    cfg = {**DEFAULT_CFG, **(json.loads(cfg_path.read_text()) if cfg_path.exists() else {})}
    cfg["dir"] = str(root)
    sid = os.environ.get("OPENCODE_SESSION_ID")
    if sid and not any(t.get("session") == sid for t in fold(rd).values()):
        cfg["orchestrator"] = sid
    if allow:
        cfg["allow"] = list(dict.fromkeys((cfg.get("allow") or []) + list(allow)))
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    remember(root)
    return rd, cfg


def run_dir(run, must=True):
    rd = project_root() / ".ocq" / "runs" / run
    if must and not (rd / "run.json").exists():
        die(f"run not found: {rd}")
    touch_orchestrator(rd)
    return rd


def load_cfg(rd):
    return {**DEFAULT_CFG, **json.loads((rd / "run.json").read_text())}


def rules_for(cfg, allow=None):
    merged = list(dict.fromkeys((cfg.get("allow") or []) + list(allow or [])))
    return BASE_RULES + rules_from(cfg.get("permission")) + [parse_allow(a) for a in merged], merged


def resolve(tasks, ids):
    out = []
    for i in ids:
        tid = i if i in tasks else i.zfill(4)
        if tid not in tasks:
            die(f"unknown task: {i}")
        out.append(tid)
    return out


def next_id(tasks):
    nums = [int(k) for k in tasks if k.isdigit()]
    return f"{(max(nums) if nums else len(tasks)) + 1:04d}"


def caller_task(sid):
    if not sid:
        return None
    meta = session_info(sid).get("metadata") or {}
    if meta.get("ocq_root") and meta.get("run"):
        rd = Path(meta["ocq_root"]) / ".ocq" / "runs" / meta["run"]
        if (rd / "run.json").exists():
            for t in fold(rd).values():
                if t.get("session") == sid:
                    return rd, meta["run"], t
    roots = [project_root(), *(Path(p) for p in known_projects())]
    seen = set()
    for r in roots:
        try:
            r = r.resolve()
        except OSError:
            continue
        if r in seen:
            continue
        seen.add(r)
        runs = r / ".ocq" / "runs"
        if not runs.is_dir():
            continue
        for rd in runs.iterdir():
            if not (rd / "run.json").exists():
                continue
            for t in fold(rd).values():
                if t.get("session") == sid:
                    return rd, rd.name, t
    return None


def build_prompt(rd, run, t):
    rel = f".ocq/runs/{run}"
    parts = [f"ocq run: {run}  task: {t['id']}"]
    brief = rd / "brief.md"
    if brief.exists() and brief.read_text().strip():
        parts.append(f"Read the brief first: {rel}/brief.md")
    parts += [
        "",
        "Task:",
        t["task"],
        "",
        "No human is available. Stay in scope; if blocked with no background jobs to keep alive, report failed with reason and partial work.",
        "No extra tests, paranoid syntax checks, or validation unless asked in the brief or task. Observe execution errors; done means execution completed.",
        'To message orchestrator while keeping work/background jobs running: gski ocq send .. "..."',
        "",
        f"When finished, write {rel}/results/{t['id']}.json:",
        '{"status": "done" | "failed", "artifact": "<path or short value>", "note": "<one line>"}',
        "Then reply with one line.",
    ]
    return "\n".join(parts)


def short_model(t):
    m = (t.get("model") or "").split("/")[-1].split("#")[0].replace("gemini-4-", "")
    a = t.get("agent")
    if a and a != "worker" and m:
        return f" [{a}/{m}]"
    if m and m != "hydrogen":
        return f" [{m}]"
    if a and a != "worker":
        return f" [{a}]"
    return ""


def summary(tasks):
    counts = {}
    for t in tasks.values():
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    cost = sum(t.get("cost") or 0 for t in tasks.values())
    order = ["running", "done", "failed", "reported", "pending"]
    parts = [f"{s} {counts[s]}" for s in order if counts.get(s)]
    return f"{len(tasks)} tasks: " + (", ".join(parts) or "empty") + f" | cost ${cost:.2f}"


def row(t):
    if t["status"] in ("done", "failed", "reported"):
        prefix = f"{t['worker']} " if t["status"] == "reported" and t.get("worker") else ""
        info = f"{prefix}{t.get('artifact') or '-'} | {t.get('note') or ''}"
    elif t["status"] == "running" and t.get("msg"):
        info = f"msg: {t['msg']}"
    else:
        info = t.get("task", "")
    denied = f" [denied {len(t['denied'])}]" if t.get("denied") else ""
    att = f" a{t['attempts']}" if (t.get("attempts") or 0) > 1 else ""
    return cut(f"{t['id']} {t['status']}{short_model(t)}{att}{denied} {info}")
