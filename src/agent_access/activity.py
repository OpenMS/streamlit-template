"""What assistants did in a workspace, for the sidebar to show the person.

One JSON line per tool call in ``<workspace>/.agent-activity.jsonl`` (the dot
keeps it out of sync and of the workspace's file lists), the newest
``KEEP`` calls kept.
"""

import json
import time
from pathlib import Path

FILE = ".agent-activity.jsonl"
KEEP = 200


def record(workspace: Path, tool: str, workflow=None, error: str = "") -> None:
    path = Path(workspace, FILE)
    entry = {"t": time.time(), "tool": tool}
    if isinstance(workflow, str):
        entry["workflow"] = workflow[:100]
    if error:
        entry["error"] = error[:300]
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        if path.stat().st_size > KEEP * 400:
            lines = path.read_text(encoding="utf-8").splitlines()[-KEEP:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def recent(workspace: Path, n: int = 5) -> list[dict]:
    try:
        lines = Path(workspace, FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= n:
            break
    return out
