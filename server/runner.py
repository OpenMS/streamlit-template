"""
Start, stop and watch workflow runs on this machine.

A run is a separate Python process (``python -m server.run_workflow``)
executing ``src.workflow.tasks.execute_workflow``,
the same Streamlit-free entry point the RQ worker uses online. It rebuilds the
WorkflowManager subclass without its Streamlit ``__init__`` and calls the
unchanged ``execution()``, writes the WORKFLOW FINISHED marker only on
success, and removes ``pids/`` when done. Status follows the local-mode rules
of WorkflowManager: running while ``pids/`` holds a live PID, and the outcome
is read from the log markers by ``classify_log_outcome``.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from src.workflow._log_status import classify_log_outcome
from src.workflow.Logger import Logger

from .workflow_spec import WorkflowSpec

LOG_LEVELS = {
    "minimal": "minimal.log",
    "commands and run times": "commands-and-run-times.log",
    "all": "all.log",
}

# Processes started by this server, so finished children are reaped (a
# zombie would still answer os.kill(pid, 0) and look like a running workflow).
_processes: dict[str, subprocess.Popen] = {}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def _pid_dir(workflow_dir: Path) -> Path:
    return Path(workflow_dir, "pids")


def is_running(workflow_dir: Path) -> bool:
    proc = _processes.get(str(workflow_dir))
    if proc is not None and proc.poll() is not None:
        _processes.pop(str(workflow_dir), None)
    pid_dir = _pid_dir(workflow_dir)
    if not pid_dir.exists():
        return False
    live = False
    for f in list(pid_dir.iterdir()):
        try:
            pid = int(f.name)
        except ValueError:
            continue
        if _alive(pid):
            live = True
        else:
            f.unlink(missing_ok=True)
    if not live:
        shutil.rmtree(pid_dir, ignore_errors=True)
    return live


def start(spec: WorkflowSpec, workflow_dir: Path) -> bool:
    if is_running(workflow_dir):
        return False
    shutil.rmtree(Path(workflow_dir, "logs"), ignore_errors=True)
    # A fresh interpreter rather than multiprocessing: it does not depend on
    # how the server itself was started, and the run outlives a closed app.
    from .core import ROOT

    proc = subprocess.Popen(
        [sys.executable, "-m", "server.run_workflow", str(workflow_dir), spec.cls, spec.module],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pid_dir = _pid_dir(workflow_dir)
    pid_dir.mkdir(parents=True, exist_ok=True)
    Path(pid_dir, str(proc.pid)).touch()
    _processes[str(workflow_dir)] = proc
    return True


def stop(workflow_dir: Path) -> bool:
    """SIGTERM every PID, then mark the log cancelled (as _stop_local_workflow)."""
    pid_dir = _pid_dir(workflow_dir)
    if not pid_dir.exists():
        return False
    stopped = False
    for f in list(pid_dir.iterdir()):
        try:
            os.kill(int(f.name), signal.SIGTERM)
            stopped = True
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        f.unlink(missing_ok=True)
    shutil.rmtree(pid_dir, ignore_errors=True)
    if stopped:
        Logger(workflow_dir).log("WORKFLOW CANCELLED")
    return stopped


def status(workflow_dir: Path, level: str = "minimal", lines: int | None = 100) -> dict:
    running = is_running(workflow_dir)
    log_path = Path(workflow_dir, "logs", LOG_LEVELS.get(level, "minimal.log"))
    content = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    all_lines = content.splitlines(keepends=True)
    shown = all_lines if not lines else all_lines[-lines:]
    outcome = None
    if content and not running:
        outcome = classify_log_outcome(content)
    return {
        "running": running,
        "status": "running" if running else (outcome or "idle"),
        "outcome": outcome,
        "log": "".join(shown),
        "log_lines": len(all_lines),
        "log_time": datetime.fromtimestamp(log_path.stat().st_mtime).isoformat(timespec="seconds")
        if log_path.exists()
        else None,
    }
