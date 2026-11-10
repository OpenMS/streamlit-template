"""
The pid files of a workflow (`<workflow_dir>/pids/<pid>`), checked against the
processes that are actually running.

A local run writes one file for its own process and one for each tool it
starts, and removes the folder when it ends. A process that is killed (the app
force-closed, the computer shut down) cannot remove it, so the workflow showed
as running forever and its Start button did nothing. `reap()` removes the
files of processes that are gone.

Only for pid files written on this machine: online, the files belong to a
queue worker that may run in another container.

Streamlit-free, so the queue worker and the tests can use it.
"""

import time
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is in requirements.txt
    psutil = None

# A pid file is touched right after its process started; a process created
# later than this after the file is another one that got the same pid.
_PID_REUSE_SLACK = 5.0
# A start makes the folder just before it writes the first pid file; an empty
# folder younger than this is a start in progress, not a leftover.
_EMPTY_DIR_GRACE = 30.0


def is_alive(pid: int, since: float | None = None) -> bool:
    """Whether process `pid` runs, and was started no later than `since`."""
    if psutil is None:
        return True  # cannot tell: keep the file, as before
    try:
        process = psutil.Process(pid)
        if process.status() == psutil.STATUS_ZOMBIE:
            return False
        if since is not None and process.create_time() > since + _PID_REUSE_SLACK:
            return False
    except (psutil.NoSuchProcess, ValueError):
        return False
    except psutil.Error:
        return True  # e.g. access denied: it exists
    return True


def reap(pid_dir: Path) -> tuple[bool, int]:
    """Remove the pid files of ended processes.

    Returns whether a process still runs, and how many files were removed. The
    folder itself goes when no file is left, so an empty folder from a run
    that was stopped halfway does not block the next start either.
    """
    pid_dir = Path(pid_dir)
    try:
        files = list(pid_dir.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return False, 0
    running = False
    removed = 0
    for pid_file in files:
        try:
            pid = int(pid_file.name)
            since = pid_file.stat().st_mtime
        except (ValueError, OSError):
            running = True  # not a pid file: leave the folder as it is
            continue
        if is_alive(pid, since):
            running = True
        else:
            pid_file.unlink(missing_ok=True)
            removed += 1
    if not running:
        try:
            if not any(pid_dir.iterdir()) and (
                removed or time.time() - pid_dir.stat().st_mtime > _EMPTY_DIR_GRACE
            ):
                pid_dir.rmdir()
        except OSError:
            pass
    return running, removed
