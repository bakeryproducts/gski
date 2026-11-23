import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
from pathlib import Path

from gski.oc_lib.api import EVENT_TYPES, open_events, reset_conn, session_info, set_daemon


def fmt_dur(s):
    h, rem = divmod(max(int(s), 0), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def notify(text, color):
    if not (shutil.which("hyprctl") and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")):
        return
    try:
        subprocess.Popen(
            ["hyprctl", "notify", "-1", "6000", color, f"fontsize:20 {text}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def spawn_watcher(lock_dir, module):
    lock_path = Path(lock_dir) / ".watch.lock"
    with open(lock_path, "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        fcntl.flock(f, fcntl.LOCK_UN)
    env = {k: v for k, v in os.environ.items() if k != "OPENCODE_SESSION_ID"}
    subprocess.Popen(
        [sys.executable, "-m", module, str(Path(lock_dir).resolve())],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )


def run_watcher(lock_dir, has_running, running_sids, on_perm, step):
    set_daemon()
    lock_dir = Path(lock_dir)
    if not lock_dir.is_dir():
        return
    f = open(lock_dir / ".watch.lock", "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return

    def write_pid():
        f.seek(0)
        f.truncate()
        f.write(f"{os.getpid()}\n")
        f.flush()

    def release_or_recheck():
        f.seek(0)
        f.truncate()
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)
        if not has_running():
            return True
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        write_pid()
        return False

    write_pid()
    down_since = None
    try:
        while True:
            try:
                if step() == "empty" and release_or_recheck():
                    return
                with open_events(60.0) as resp:
                    down_since = None
                    if step() == "empty" and release_or_recheck():
                        return
                    last_check = time.time()
                    while True:
                        raw = resp.readline()
                        if not raw:
                            break
                        line = raw.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            if time.time() - last_check >= 15:
                                last_check = time.time()
                                if step() == "empty" and release_or_recheck():
                                    return
                            continue
                        try:
                            ev = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        etype = ev.get("type")
                        sid = (ev.get("data") or {}).get("sessionID")
                        by_sid = running_sids()
                        if not by_sid:
                            if step() == "empty" and release_or_recheck():
                                return
                            continue
                        if etype == "permission.asked":
                            if sid in by_sid:
                                on_perm(sid, by_sid[sid])
                            elif sid:
                                parent = session_info(sid).get("parentID")
                                if parent in by_sid:
                                    on_perm(sid, by_sid[parent])
                        elif etype == "shell.exited" or (sid in by_sid and etype in EVENT_TYPES):
                            last_check = time.time()
                            if step() == "empty" and release_or_recheck():
                                return
            except TimeoutError:
                down_since = None
                if step() == "empty" and release_or_recheck():
                    return
            except (urllib.error.URLError, OSError):
                reset_conn()
                if not has_running() and release_or_recheck():
                    return
                down_since = down_since or time.time()
                if time.time() - down_since > 600:
                    f.seek(0)
                    f.truncate()
                    f.flush()
                    return
                time.sleep(2)
            except Exception:
                try:
                    (lock_dir / ".watch.err").write_text(traceback.format_exc())
                except OSError:
                    pass
                time.sleep(2)
    finally:
        f.close()
