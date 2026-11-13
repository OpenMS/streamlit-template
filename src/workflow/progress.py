"""Per-file progress of a workflow run, shared between the run and the Run page.

``CommandExecutor.run_topp()`` records each tool call as a *step* with one
entry per command, which usually means one input file. Each entry goes from
"pending" to "running" to "done" or "failed", with start and end times. A
failed entry keeps the exit code and the tail of the tool's output, so the Run
page can say "While running FeatureFinderMetabo on file 2 of 3 (x.mzML)" and
show the raw output under it.

A workflow that takes its samples one after another, running several tools
on each, also records the *samples* (``start_samples()`` and the ``sample()``
context): the Run page then lists every sample as waiting, running (with the
tool it is in), done or failed, instead of only the file of the current tool.

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
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

# Lines of tool output kept for a failed file
OUTPUT_TAIL = 200
# Tries at replacing progress.json while a reader holds it open (Windows)
REPLACE_ATTEMPTS = 20

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
    """Writes progress.json; one per CommandExecutor, safe across its threads.

    run_multiple_commands() runs several files at once, each in its own
    thread, so every update is a read-modify-write under one lock: two files
    finishing together both land. The file is replaced atomically, so the Run
    page never reads half of it. Progress is only for display: an update that
    cannot be written is dropped, never raised into the run.
    """

    def __init__(self, workflow_dir) -> None:
        self.workflow_dir = Path(workflow_dir)
        self._lock = threading.Lock()

    # The local Run button starts the workflow with multiprocessing, which
    # pickles the workflow and with it this object under the "spawn" start
    # method (Windows, macOS, and apps that choose it). A lock can not be
    # pickled, so the child process gets a new one of its own.
    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        state.pop("_lock", None)
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        state = read_progress(self.workflow_dir)
        if not state:
            state = {"started": time.time(), "steps": [], "environment": _environment()}
        return state

    def _save(self, state: dict) -> None:
        path = progress_path(self.workflow_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".progress-{os.getpid()}-{threading.get_ident()}.json")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        # On Windows the replace fails while the Run page has the file open
        # for reading; that read takes milliseconds, so try again briefly.
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    tmp.unlink(missing_ok=True)
                    raise
                time.sleep(0.05)

    def _update(self, change) -> Optional[int]:
        """Apply change(state) under the lock and save; None if that failed."""
        with self._lock:
            try:
                state = self._load()
                result = change(state)
                self._save(state)
                return result
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                return None

    def start_step(
        self,
        tool: str,
        labels: List[str],
        threads: int = 1,
        parallel: int = 1,
        provenance: Optional[dict] = None,
        allow_failed: bool = False,
    ) -> int:
        """Record a tool call with one entry per label; returns the step index.

        ``provenance`` is what the processing report needs to say how each
        input file was processed (``src/workflow/processing_report.py``):
        ``{"kind": "topp"|"python", "program", "version", "params",
        "io": [{"inputs": [...], "outputs": [...]}, one per label]}``.
        """

        def change(state):
            step = {
                "tool": tool,
                "started": time.time(),
                "ended": None,
                "threads": threads,
                "parallel": parallel,
                "sample": _running_sample(state),
                "files": [
                    {"name": label, "status": PENDING, "started": None, "ended": None}
                    for label in labels
                ],
            }
            if provenance:
                step["provenance"] = provenance
            if allow_failed:
                step["allow_failed"] = True
            state["steps"].append(step)
            return len(state["steps"]) - 1

        step = self._update(change)
        # Not recorded: later updates of this step find no entry and are dropped
        return -1 if step is None else step

    def file_started(self, step: int, index: int) -> None:
        def change(state):
            entry = state["steps"][step]["files"][index]
            entry["status"] = RUNNING
            entry["started"] = time.time()

        if step >= 0:
            self._update(change)

    def file_finished(
        self,
        step: int,
        index: int,
        ok: bool,
        returncode: int = 0,
        output: Optional[List[str]] = None,
    ) -> None:
        def change(state):
            entry = state["steps"][step]["files"][index]
            entry["status"] = DONE if ok else FAILED
            entry["ended"] = time.time()
            if entry["started"] is None:
                entry["started"] = entry["ended"]
            if not ok:
                entry["returncode"] = returncode
                entry["output"] = list(output or [])[-OUTPUT_TAIL:]

        if step >= 0:
            self._update(change)

    def record_alias(self, path: str, source: str, note: str = "") -> None:
        """``path`` is ``source`` under another name (a renamed or reused file),
        so the processing report traces files made from it back to ``source``."""

        def change(state):
            state.setdefault("aliases", {})[str(path)] = {"source": str(source), "note": note}

        self._update(change)

    def end_step(self, step: int) -> None:
        def change(state):
            state["steps"][step]["ended"] = time.time()

        if step >= 0:
            self._update(change)

    # Samples: a workflow that runs its tools on one sample after another

    def start_samples(self, labels: List[str]) -> None:
        """Record the samples of this run, all waiting."""

        def change(state):
            state["samples"] = [
                {"name": label, "status": PENDING, "started": None, "ended": None}
                for label in labels
            ]

        self._update(change)

    def sample_started(self, index: int) -> None:
        def change(state):
            entry = state["samples"][index]
            entry["status"] = RUNNING
            entry["started"] = time.time()

        self._update(change)

    def sample_finished(self, index: int, ok: bool) -> None:
        def change(state):
            entry = state["samples"][index]
            entry["status"] = DONE if ok else FAILED
            entry["ended"] = time.time()
            if entry["started"] is None:
                entry["started"] = entry["ended"]

        self._update(change)

    @contextmanager
    def sample(self, index: int):
        """Mark sample `index` running for the block: done when it ends, failed
        when it raises (the exception goes on). Mark it failed yourself with
        sample_finished(index, ok=False) for a failure that does not raise;
        the block's end then leaves it so.
        """
        self.sample_started(index)
        try:
            yield
        except BaseException:
            self.sample_finished(index, ok=False)
            raise
        state = read_progress(self.workflow_dir) or {}
        samples = state.get("samples") or []
        if index < len(samples) and samples[index]["status"] == RUNNING:
            self.sample_finished(index, ok=True)


def _environment() -> dict:
    """Versions the processing report names: Python, pyOpenMS, the platform."""
    import platform  # pylint: disable=import-outside-toplevel
    from importlib import metadata  # pylint: disable=import-outside-toplevel

    env = {"python": platform.python_version(), "platform": platform.platform(terse=True)}
    try:
        env["pyopenms"] = metadata.version("pyopenms")
    except metadata.PackageNotFoundError:
        pass
    return env


def _running_sample(state: dict) -> Optional[str]:
    """The name of the sample being processed, if the run records samples."""
    for entry in state.get("samples") or []:
        if entry["status"] == RUNNING:
            return entry["name"]
    return None


def file_counts(step: dict) -> dict:
    """How many files of a step are pending, running, done and failed."""
    counts = {PENDING: 0, RUNNING: 0, DONE: 0, FAILED: 0}
    for entry in step["files"]:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return counts


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
    context = f"While running {step['tool']}" + (f" on {where}" if where else "")
    sample = step.get("sample")
    if sample and sample != step["files"][index]["name"]:
        context += f" for sample {sample}"
    return context


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


def failures(state: Optional[dict], left_out: Optional[bool] = None) -> List[dict]:
    """Every failed file: {"context", "message", "returncode", "output"}.

    ``left_out=True`` gives only the files of steps the run went on without
    (``allow_failed``), ``False`` only the others, ``None`` all of them.
    """
    found = []
    for step in (state or {}).get("steps", []):
        if left_out is not None and bool(step.get("allow_failed")) != left_out:
            continue
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


def sample_counts(state: Optional[dict]) -> dict:
    """How many samples are pending, running, done and failed."""
    counts = {PENDING: 0, RUNNING: 0, DONE: 0, FAILED: 0}
    for entry in (state or {}).get("samples") or []:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return counts


def current_step(state: dict, sample: str) -> Optional[dict]:
    """The latest step run for `sample`, or None before its first tool."""
    for step in reversed(state.get("steps") or []):
        if step.get("sample") == sample:
            return step
    return None


# TOPP tools report their own progress: "Progress of 'loading spectra':",
# then lines ending in "42.17 %". The run writes tool output to logs/all.log.
_PROGRESS_LABEL = re.compile(r"Progress of\s+'([^']+)'")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# Bytes read from the end of all.log; a tool's latest progress lines are there
_LOG_TAIL = 65536


def tool_progress(log_path) -> Optional[tuple]:
    """(label, fraction) of the running tool's own progress, from the end of
    all.log, or None if the tool has reported none since it started."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - _LOG_TAIL))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    fraction = None
    for line in reversed(lines):
        if "Process finished:" in line or "Running command:" in line:
            break
        if fraction is None:
            match = _PERCENT.search(line)
            if match:
                fraction = float(match.group(1)) / 100
        match = _PROGRESS_LABEL.search(line)
        if match:
            if fraction is None or not 0 <= fraction <= 1:
                return None
            return match.group(1), fraction
    return None


def format_duration(seconds: float) -> str:
    """'0:42', '12:05' or '1:02:05'."""
    seconds = int(max(0, seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
