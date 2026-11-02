"""Per-file progress of a workflow run, shared between the run and the Run page.

``CommandExecutor.run_topp()`` records each tool call as a *step* with one
entry per command, which usually means one input file. Each entry goes from
"pending" to "running" to "done" or "failed", with start and end times. A
failed entry keeps the exit code and the tail of the tool's output, so the Run
page can say "While running FeatureFinderMetabo on file 2 of 3 (x.mzML)" and
show the raw output under it.

The state is one JSON file, ``<workflow_dir>/logs/progress.json``. The logs
folder is cleared when a run starts and copied into the run folder when a
multi-run workflow ends. It is kept free of Streamlit because the run itself
writes it, either in the local workflow process or in the queue worker.
"""
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import List, Optional

# Lines of tool output kept for a failed file
OUTPUT_TAIL = 200

PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"


def progress_path(workflow_dir) -> Path:
    return Path(workflow_dir, "logs", "progress.json")


def read_progress(workflow_dir) -> Optional[dict]:
    """The recorded progress, or None if nothing was recorded (yet)."""
    try:
        with open(progress_path(workflow_dir), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


class RunProgress:
    """Writes progress.json; one per CommandExecutor, safe across its threads."""

    def __init__(self, workflow_dir) -> None:
        self.workflow_dir = Path(workflow_dir)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        state = read_progress(self.workflow_dir)
        if not state:
            state = {"started": time.time(), "steps": []}
        return state

    def _save(self, state: dict) -> None:
        path = progress_path(self.workflow_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".progress-{os.getpid()}-{threading.get_ident()}.json")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)

    def start_step(self, tool: str, labels: List[str], threads: int = 1, parallel: int = 1) -> int:
        """Record a tool call with one entry per label; returns the step index."""
        with self._lock:
            state = self._load()
            state["steps"].append(
                {
                    "tool": tool,
                    "started": time.time(),
                    "ended": None,
                    "threads": threads,
                    "parallel": parallel,
                    "files": [
                        {"name": label, "status": PENDING, "started": None, "ended": None}
                        for label in labels
                    ],
                }
            )
            self._save(state)
            return len(state["steps"]) - 1

    def file_started(self, step: int, index: int) -> None:
        with self._lock:
            state = self._load()
            entry = state["steps"][step]["files"][index]
            entry["status"] = RUNNING
            entry["started"] = time.time()
            self._save(state)

    def file_finished(
        self,
        step: int,
        index: int,
        ok: bool,
        returncode: int = 0,
        output: Optional[List[str]] = None,
    ) -> None:
        with self._lock:
            state = self._load()
            entry = state["steps"][step]["files"][index]
            entry["status"] = DONE if ok else FAILED
            entry["ended"] = time.time()
            if not ok:
                entry["returncode"] = returncode
                entry["output"] = list(output or [])[-OUTPUT_TAIL:]
            self._save(state)

    def end_step(self, step: int) -> None:
        with self._lock:
            state = self._load()
            state["steps"][step]["ended"] = time.time()
            self._save(state)


def file_position(step: dict, index: int) -> str:
    """'file 2 of 3 (x.mzML)', or '(x.mzML)' alone for a single command."""
    files = step["files"]
    name = files[index]["name"]
    if len(files) == 1:
        return f"({name})" if name else ""
    return f"file {index + 1} of {len(files)}" + (f" ({name})" if name else "")


def failure_context(step: dict, index: int) -> str:
    """'While running CometAdapter on file 2 of 3 (x.mzML)'."""
    where = file_position(step, index)
    return f"While running {step['tool']}" + (f" on {where}" if where else "")


# OpenMS appends the C++ source location to its messages:
# "... (- due to that error of type Parse Error in: /src/.../XMLHandler.cpp@108-void ...)"
_SOURCE_LOCATION = re.compile(r"\s+in:\s+\S*\.(?:cpp|h|hpp)@.*$")


def key_message(output: List[str]) -> str:
    """The line of tool output most likely to say what went wrong."""
    lines = [line.strip() for line in output or [] if line.strip()]
    found = lines[-1] if lines else ""
    for line in reversed(lines):
        low = line.lower()
        if "error" in low or "exception" in low or "fatal" in low:
            found = line
            break
    short = _SOURCE_LOCATION.sub("", found)
    if short != found and short.count("(") > short.count(")"):
        short += ")"
    return short[:300]


def failures(state: Optional[dict]) -> List[dict]:
    """Every failed file: {"context", "message", "returncode", "output"}."""
    found = []
    for step in (state or {}).get("steps", []):
        for i, entry in enumerate(step["files"]):
            if entry["status"] == FAILED:
                output = entry.get("output", [])
                found.append(
                    {
                        "context": failure_context(step, i),
                        "message": key_message(output),
                        "returncode": entry.get("returncode"),
                        "output": output,
                    }
                )
    return found


def format_duration(seconds: float) -> str:
    """'0:42', '12:05' or '1:02:05'."""
    seconds = int(max(0, seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
