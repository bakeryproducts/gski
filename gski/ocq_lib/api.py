import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ.get("OCQ_URL", "http://127.0.0.1:4096").rstrip("/")
DEFAULT_PORT = 4096
DEFAULT_DASH_PORT = 4097

BASE_RULES = [
    {"permission": "task", "pattern": "*", "action": "deny"},
    {"permission": "question", "pattern": "*", "action": "deny"},
    {"permission": "bash", "pattern": "gski ocq*", "action": "deny"},
]

DEFAULT_CFG = {
    "agent": "worker",
    "model": None,
    "variant": None,
    "concurrency": 1,
    "max_attempts": 3,
    "permission": {},
}

DENY_MSG = "ocq: this specific call is not permitted. Do not retry it; continue without it or write status failed."


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def api(method, path, body=None, directory=None):
    url = URL + path
    if directory:
        url += ("&" if "?" in path else "?") + "directory=" + urllib.parse.quote(directory)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as f:
            raw = f.read()
    except urllib.error.HTTPError as e:
        die(f"http {e.code} {method} {path}: {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError:
        die(f"server not reachable at {URL} (start it: gski ocq serve)")
    return json.loads(raw) if raw else None


def fetch(path, directory=None, timeout=5):
    url = URL + path
    if directory:
        url += ("&" if "?" in path else "?") + "directory=" + urllib.parse.quote(directory)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as f:
            raw = f.read()
        return json.loads(raw) if raw else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def last_text(msgs):
    for m in reversed(msgs):
        if m["info"]["role"] != "assistant":
            continue
        txt = "\n".join(p.get("text", "") for p in m["parts"] if p["type"] == "text").strip()
        if txt:
            return txt
    return ""


def err_text(err):
    data = err.get("data") or {}
    return f"{err.get('name', 'error')}: {data.get('message', '')}".strip(": ")


def sweep(rd, cfg, by_session, append_fn):
    for p in api("GET", "/permission", directory=cfg["dir"]) or []:
        tid = by_session.get(p.get("sessionID"))
        if not tid:
            continue
        api("POST", f"/permission/{p['id']}/reply", {"reply": "reject", "message": DENY_MSG}, cfg["dir"])
        what = f"{p.get('permission')}: {' '.join(p.get('patterns') or [])}"[:120]
        append_fn(rd, id=tid, denied=what)
        print(f"{tid} denied {what}")
    for q in api("GET", "/question", directory=cfg["dir"]) or []:
        tid = by_session.get(q.get("sessionID"))
        if tid:
            api("POST", f"/question/{q['id']}/reject", directory=cfg["dir"])
            append_fn(rd, id=tid, denied="question")
            print(f"{tid} denied question")


def activity(msgs):
    for m in reversed(msgs):
        for p in reversed(m.get("parts", [])):
            if p["type"] == "tool":
                s = p.get("state") or {}
                inp = s.get("input") or {}
                what = s.get("title") or inp.get("command") or inp.get("filePath") or inp.get("pattern") or ""
                return f"{p.get('tool')}: {what}"[:200]
            if p["type"] == "text" and p.get("text", "").strip():
                return p["text"][:200]
    return ""
