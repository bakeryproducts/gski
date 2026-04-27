import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path


STATE_DIR = (
    Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    / "gski"
    / "deepresearch"
)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def new_job_id():
    return secrets.token_hex(4)


def job_path(job_id):
    return STATE_DIR / f"{job_id}.json"


def report_path_for(job_id):
    return STATE_DIR / f"{job_id}.md"


def resolve_job_id(prefix):
    ensure_state_dir()
    matches = sorted(p for p in STATE_DIR.glob("*.json") if p.stem.startswith(prefix))
    if not matches:
        print(f"error: no job matching '{prefix}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        ids = ", ".join(p.stem for p in matches)
        print(f"error: ambiguous job id '{prefix}' matches: {ids}", file=sys.stderr)
        sys.exit(1)
    return matches[0].stem


def load_job(prefix):
    job_id = resolve_job_id(prefix)
    return json.loads(job_path(job_id).read_text())


def save_job(job):
    ensure_state_dir()
    job["updated_at"] = now_iso()
    job_path(job["job_id"]).write_text(json.dumps(job, indent=2))


def all_jobs():
    ensure_state_dir()
    jobs = []
    for p in sorted(
        STATE_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
    ):
        try:
            jobs.append(json.loads(p.read_text()))
        except Exception:
            continue
    return jobs


def new_job(query, model, mode, files):
    job_id = new_job_id()
    ts = now_iso()
    return {
        "job_id": job_id,
        "created_at": ts,
        "updated_at": ts,
        "query": query,
        "model": model,
        "mode": mode,
        "state": "planning" if mode == "plan" else "running",
        "interactions": [],
        "current_interaction_id": None,
        "files": list(files),
        "report_path": None,
    }


def record_interaction(job, interaction_id, kind, user_input):
    job["interactions"].append(
        {
            "id": interaction_id,
            "kind": kind,
            "input": user_input if isinstance(user_input, str) else "<multimodal>",
            "created_at": now_iso(),
        }
    )
    job["current_interaction_id"] = interaction_id


def save_report(job, text):
    path = report_path_for(job["job_id"])
    path.write_text(text)
    job["report_path"] = str(path)
    return path


def remove_job(job, keep_report=False):
    jp = job_path(job["job_id"])
    rp = report_path_for(job["job_id"])
    if jp.exists():
        jp.unlink()
    if rp.exists() and not keep_report:
        rp.unlink()
