"""What an assistant asked the open app to show (the ``show_in_app`` tool).

The tool writes one request to ``<workspace>/.agent-show.json``; every page of
a session that follows the assistant checks it (``ui.follow``) and, when a new
one arrives, opens that page with that run picked and shows the note. The
file holds the newest request only: the app shows what the assistant shows
now, not a queue of it.
"""

import json
import os
import time
import uuid
from pathlib import Path

FILE = ".agent-show.json"


def write(workspace: Path, request: dict) -> dict:
    request = {**request, "id": uuid.uuid4().hex, "t": time.time()}
    path = Path(workspace, FILE)
    tmp = path.with_name(f"{FILE}.{request['id']}.tmp")
    try:
        tmp.write_text(json.dumps(request), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return request


def latest(workspace: Path) -> dict | None:
    try:
        request = json.loads(Path(workspace, FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return request if isinstance(request, dict) and request.get("id") else None
