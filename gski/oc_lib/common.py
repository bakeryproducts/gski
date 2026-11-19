import json
import os
import re
import sys
import time
from pathlib import Path

WIDTH = 160
NAME_RE = re.compile(r"^[\w.-]+$")
REGISTRY = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "ocq" / "projects"
ACTIONS = {"bash": "shell", "task": "subagent", "write": "edit", "patch": "edit"}


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def cut(s, n=WIDTH):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def known_projects():
    return [line for line in REGISTRY.read_text().splitlines() if line] if REGISTRY.exists() else []


def remember(root):
    root = str(root)
    if root not in known_projects():
        REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        with open(REGISTRY, "a") as f:
            f.write(root + "\n")


def append_jsonl(path, **ev):
    with open(path, "ab+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell():
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write((json.dumps({"t": int(time.time()), **ev}, ensure_ascii=False) + "\n").encode())


def sum_tokens(items):
    out = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}
    for tk in items:
        if not tk:
            continue
        cache = tk.get("cache") or {}
        out["input"] += tk.get("input", 0) or 0
        out["output"] += tk.get("output", 0) or 0
        out["reasoning"] += tk.get("reasoning", 0) or 0
        out["cache_read"] += tk.get("cache_read", cache.get("read", 0)) or 0
        out["cache_write"] += tk.get("cache_write", cache.get("write", 0)) or 0
    return out


def rules_from(perm):
    rules = []
    for key, val in (perm or {}).items():
        act = ACTIONS.get(key, key)
        if isinstance(val, str):
            rules.append({"action": act, "resource": "*", "effect": val})
        else:
            rules += [{"action": act, "resource": pat, "effect": eff} for pat, eff in val.items()]
    return rules


def parse_allow(spec):
    key, _, pat = spec.partition(":")
    key = key.strip()
    return {"action": ACTIONS.get(key, key), "resource": pat.strip() or "*", "effect": "allow"}
