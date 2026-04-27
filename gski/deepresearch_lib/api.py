import mimetypes
import os
import re
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore", message=r".*Interactions usage is experimental.*"
)

from google import genai


AGENT_MODELS = {
    "default": "deep-research-preview-04-2026",
    "max": "deep-research-max-preview-04-2026",
}

POLL_INTERVAL = 10


def make_client():
    if not os.environ.get("GEMINI_API_KEY"):
        print("error: GEMINI_API_KEY env var required", file=sys.stderr)
        sys.exit(1)
    return genai.Client()


def _interactions(client):
    api = getattr(client, "interactions", None)
    if api is None:
        print(
            "error: this google-genai version has no `interactions` API.\n"
            "  try: pip install -U google-genai",
            file=sys.stderr,
        )
        sys.exit(1)
    return api


def interactions_create(client, **kwargs):
    return _interactions(client).create(**kwargs)


def interactions_get(client, interaction_id):
    return _interactions(client).get(interaction_id)


def upload_file(client, path):
    p = Path(path)
    if not p.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    f = client.files.upload(file=str(p))
    uri = getattr(f, "uri", None) or getattr(f, "name", None)
    if not uri:
        print(f"error: upload of {path} returned no uri", file=sys.stderr)
        sys.exit(1)
    mime = getattr(f, "mime_type", None)
    if not mime:
        mime, _ = mimetypes.guess_type(str(p))
    return uri, mime


def build_input(prompt, files, client):
    if not files:
        return prompt

    parts = [{"type": "text", "text": prompt}]
    for item in files:
        if re.match(r"^https?://", item):
            mime, _ = mimetypes.guess_type(item)
            uri = item
        else:
            uri, mime = upload_file(client, item)
        kind = "image" if (mime and mime.startswith("image/")) else "document"
        part = {"type": kind, "uri": uri}
        if mime:
            part["mime_type"] = mime
        parts.append(part)
    return parts


def extract_text(interaction):
    outputs = getattr(interaction, "outputs", None) or []
    chunks = []
    for out in outputs:
        text = getattr(out, "text", None)
        otype = getattr(out, "type", None)
        if text is None and isinstance(out, dict):
            text = out.get("text")
            otype = out.get("type")
        if text and (otype is None or otype == "text"):
            chunks.append(text)
    if chunks:
        return "".join(chunks)
    return getattr(interaction, "text", "") or ""


def poll(client, interaction_id, interval=POLL_INTERVAL):
    start = time.time()
    last_status = None
    while True:
        interaction = interactions_get(client, interaction_id)
        status = getattr(interaction, "status", None)
        if status != last_status:
            elapsed = int(time.time() - start)
            print(f"[{elapsed}s] {status}", file=sys.stderr)
            last_status = status
        if status == "completed":
            return interaction
        if status == "failed":
            err = getattr(interaction, "error", "unknown error")
            print(f"error: research failed: {err}", file=sys.stderr)
            sys.exit(2)
        time.sleep(interval)


def new_interaction_id(interaction):
    iid = getattr(interaction, "id", None)
    if not iid:
        print("error: api returned no interaction id", file=sys.stderr)
        sys.exit(1)
    return iid
