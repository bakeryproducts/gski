import base64
import itertools
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from gski.oc_lib.common import die

DEFAULT_PORT = 4096
DEFAULT_VARIANT = "high"

EVENT_TYPES = (
    "session.execution.succeeded",
    "session.execution.failed",
    "session.execution.interrupted",
    "permission.asked",
    "shell.exited",
)

DENY_MSG = "This specific call is not permitted in this session. Do not retry it; continue without it or stop and report the missing permission."

_conn = {}
_daemon = False


def set_daemon():
    global _daemon
    _daemon = True


def reset_conn():
    _conn.clear()


def _service_file():
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "opencode" / "service.json"


def _read_service():
    try:
        d = json.loads(_service_file().read_text())
        return d["url"].rstrip("/"), d.get("password")
    except (OSError, ValueError, KeyError):
        return None


def _headers(password):
    h = {"content-type": "application/json"}
    if password:
        h["authorization"] = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()
    return h


def _alive(url, password):
    req = urllib.request.Request(url + "/api/session/active", headers=_headers(password))
    try:
        urllib.request.urlopen(req, timeout=3).read()
        return True
    except (urllib.error.URLError, OSError):
        return False


def connect():
    if _conn:
        return _conn["url"], _conn["password"]
    env = os.environ.get("OCQ_URL")
    if env:
        url, pw = env.rstrip("/"), os.environ.get("OCQ_PASSWORD")
        if not _alive(url, pw):
            if _daemon:
                raise OSError(f"server not reachable at {url}")
            die(f"server not reachable at {url}")
    else:
        found = _read_service()
        if not found or not _alive(*found):
            if _daemon:
                raise OSError("opencode background service not reachable")
            subprocess.run(["opencode", "service", "start"], capture_output=True)
            for _ in range(20):
                found = _read_service()
                if found and _alive(*found):
                    break
                time.sleep(0.5)
            else:
                die("opencode background service not reachable (try: opencode service start)")
        url, pw = found
    _conn.update(url=url, password=pw)
    return url, pw


def open_events(timeout):
    url, pw = connect()
    q = "&".join(f"types={urllib.parse.quote(t)}" for t in EVENT_TYPES)
    req = urllib.request.Request(f"{url}/api/event?{q}", headers={**_headers(pw), "accept": "text/event-stream"})
    return urllib.request.urlopen(req, timeout=timeout)


def _call(method, path, body=None, timeout=60):
    url, pw = connect()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method, headers=_headers(pw))
    with urllib.request.urlopen(req, timeout=timeout) as f:
        raw = f.read()
    return json.loads(raw) if raw else None


def api(method, path, body=None):
    try:
        out = _call(method, path, body)
    except urllib.error.HTTPError as e:
        die(f"http {e.code} {method} {path}: {e.read().decode(errors='replace')[:300]}")
    except (urllib.error.URLError, OSError):
        die("server not reachable (start it: opencode service start)")
    return out.get("data") if isinstance(out, dict) and "data" in out else out


def fetch(path, timeout=5):
    try:
        out = _call("GET", path, timeout=timeout)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return out.get("data") if isinstance(out, dict) and "data" in out else out


def parse_model(model):
    if not model:
        return None, None, None
    model, _, variant = model.partition("#")
    prov, _, mid = model.partition("/")
    return prov, mid, variant or None


def _retry(fn, tries=20):
    for _ in range(tries):
        out = fn()
        if out:
            return out
        time.sleep(0.5)
    return None


def agent_info(agent, directory=None):
    q = f"?{_loc(directory)}" if directory else ""
    agents = _retry(lambda: fetch(f"/api/agent{q}")) or []
    info = next((a for a in agents if a.get("id") == agent), None)
    if not info:
        die(f"unknown agent: {agent}")
    return info


def headless_rules(agent, rules, directory=None, info=None):
    perms = (info or agent_info(agent, directory)).get("permissions") or []
    base = [
        {"action": r["action"], "resource": r["resource"], "effect": "deny" if r["effect"] == "ask" else r["effect"]}
        for r in perms
    ]
    return base + list(rules or [])


def resolve_model(agent, model, directory=None, info=None):
    prov, mid, var = parse_model(model)
    src = "run"
    if not mid:
        src = "agent"
        info = info or agent_info(agent, directory)
        m = info.get("model") or {}
        prov, mid, var = m.get("providerID"), m.get("id"), m.get("variant")
    if not mid:
        src = "default"
        d = _retry(lambda: fetch("/api/model/default")) or {}
        prov, mid = d.get("providerID"), d.get("modelID") or d.get("id")
    if not mid:
        die("cannot resolve a model: set --model or a default model")
    return {"providerID": prov, "id": mid, "variant": var or DEFAULT_VARIANT}, src


def fmt_model(ref):
    return f"{ref['providerID']}/{ref['id']}" + (f"#{ref['variant']}" if ref.get("variant") else "")


def create_session(title, agent, model, rules, directory, metadata=None):
    info = agent_info(agent, directory)
    ref, src = resolve_model(agent, model, directory, info=info)
    body = {
        "title": title,
        "agent": agent,
        "permissions": headless_rules(agent, rules, directory, info=info),
        "location": {"directory": directory},
        "model": ref,
        **({"metadata": metadata} if metadata else {}),
    }
    s = api("POST", "/api/session", body)
    got = s.get("model") or {}
    if (got.get("providerID"), got.get("id")) != (ref["providerID"], ref["id"]):
        die(f"server did not apply model {fmt_model(ref)} (got {fmt_model(got) if got else 'none'})")
    return s, f"{fmt_model(ref)} ({src})"


def set_permissions(sid, agent, rules, directory=None):
    return api("PATCH", f"/api/session/{sid}", {"permissions": headless_rules(agent, rules, directory)})


def send_prompt(sid, text, delivery=None):
    body = {"text": text, **({"delivery": delivery} if delivery else {})}
    return api("POST", f"/api/session/{sid}/prompt", body)


def send_synthetic(sid, text, description=None, delivery="queue"):
    body = {
        "text": text,
        **({"description": description} if description else {}),
        **({"delivery": delivery} if delivery else {}),
    }
    return api("POST", f"/api/session/{sid}/synthetic", body)


def try_send_synthetic(sid, text, description=None, delivery="queue"):
    if not sid:
        return False
    body = {
        "text": text,
        **({"description": description} if description else {}),
        **({"delivery": delivery} if delivery else {}),
    }
    for i in range(3):
        try:
            _call("POST", f"/api/session/{sid}/synthetic", body, timeout=15)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            if e.code == 401:
                reset_conn()
        except (urllib.error.URLError, OSError, ValueError):
            reset_conn()
        if i < 2:
            time.sleep(1)
    return False


def _loc(directory):
    return "location[directory]=" + urllib.parse.quote(str(directory))


def shells(sid, directory):
    out = fetch(f"/api/shell?{_loc(directory)}")
    if out is None:
        return None
    return [s for s in out if s.get("status") == "running" and (s.get("metadata") or {}).get("sessionID") == sid]


def kill_shell(shell_id, directory):
    api("DELETE", f"/api/shell/{shell_id}?{_loc(directory)}")


def pending_input(msgs):
    last = next((m for m in msgs if m.get("type") in ("assistant", "user", "synthetic")), None)
    return bool(last and last["type"] != "assistant")


def messages(sid, limit=None, timeout=60):
    q = f"?limit={limit}" if limit else ""
    return fetch(f"/api/session/{sid}/message{q}", timeout=timeout) or []


def session_info(sid):
    return fetch(f"/api/session/{sid}") or {}


def active():
    return fetch("/api/session/active")


def interrupt(sid):
    api("POST", f"/api/session/{sid}/interrupt")


def assistants(msgs):
    return [m for m in msgs if m.get("type") == "assistant"]


def last_text(msgs):
    for m in assistants(msgs):
        txt = "\n".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text").strip()
        if txt:
            return txt
    return ""


def turn_text(msgs):
    turn = list(itertools.takewhile(lambda m: m.get("type") not in ("user", "synthetic"), msgs))
    parts = []
    for m in reversed(turn):
        if m.get("type") == "assistant":
            txt = "\n".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text").strip()
            if txt:
                parts.append(txt)
    return "\n\n".join(parts) if parts else last_text(msgs)


def err_text(err):
    if not isinstance(err, dict):
        return str(err)
    return f"{err.get('type') or err.get('name') or 'error'}: {err.get('message', '')}".strip(": ")


def denied_calls(msgs, since=0):
    out = []
    cutoff = (since or 0) * 1000
    for m in reversed(msgs):
        if cutoff and (m.get("time") or {}).get("created", 0) < cutoff:
            continue
        for c in m.get("content") or []:
            if c.get("type") != "tool":
                continue
            st = c.get("state") or {}
            err = st.get("error") or {}
            if not isinstance(err, dict) or err.get("type") != "permission.rejected" or err.get("message") == DENY_MSG:
                continue
            msg = err.get("message") or ""
            act = msg.removeprefix("Permission denied:").strip() if msg.startswith("Permission denied:") else (c.get("name") or "tool")
            inp = st.get("input") or {}
            res = (
                inp.get("command")
                or inp.get("path")
                or inp.get("pattern")
                or inp.get("url")
                or inp.get("query")
                or inp.get("id")
                or inp.get("agent")
                or ""
            )
            what = " ".join(f"{act}: {res}".strip(": ").split())[:120]
            if what and what not in out:
                out.append(what)
    return out


def sweep(target_dir, by_session, append_fn):
    for sid, tid in by_session.items():
        for p in fetch(f"/api/session/{sid}/permission") or []:
            try:
                _call("POST", f"/api/session/{sid}/permission/{p['id']}/reply", {"decision": "reject", "message": DENY_MSG}, timeout=15)
            except (urllib.error.URLError, OSError, ValueError):
                continue
            what = f"{p.get('action')}: {' '.join(p.get('resources') or [])}"[:120]
            append_fn(target_dir, id=tid, denied=what)
