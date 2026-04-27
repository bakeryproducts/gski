from datetime import datetime, timezone


def fmt_age(iso):
    try:
        t = datetime.fromisoformat(iso)
    except Exception:
        return "?"
    delta = datetime.now(timezone.utc) - t
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def truncate(text, width):
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def print_job_row(job, widths=(10, 10, 7, 6)):
    q = truncate(job.get("query", ""), 60)
    jw, sw, mw, aw = widths
    print(
        f"{job['job_id']:<{jw}}  "
        f"{job.get('state', '?'):<{sw}}  "
        f"{job.get('mode', '?'):<{mw}}  "
        f"{fmt_age(job.get('updated_at', '')):<{aw}}  "
        f"{q}"
    )


def print_job_header(widths=(10, 10, 7, 6)):
    jw, sw, mw, aw = widths
    print(
        f"{'JOB':<{jw}}  {'STATE':<{sw}}  {'MODE':<{mw}}  {'AGE':<{aw}}  QUERY"
    )
