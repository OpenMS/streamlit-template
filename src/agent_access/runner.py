"""Start, follow and stop a workflow run for an assistant.

Online, a run goes to the RQ queue exactly as the Run button or the desktop
app puts it there (``src/sync/runs.py``), so the workflow's Run page shows it
too. In the local app it starts through ``src/workflow/start.py``, as the Run
button starts it: the same run folder and workflow process, its pid in
``<workflow>/pids/`` so the Run page shows it running and can stop it, and so
the same processing report.
"""

import os
import shutil
import signal
from pathlib import Path

from src.workflow._log_status import classify_log_outcome

from . import describe



class RunError(RuntimeError):
    """A run that cannot be started or stopped; the message says why."""


def _runs(workflow_dir: Path):
    from src.workflow.RunManager import RunManager
    return RunManager(workflow_dir)


def _queue():
    from src.sync import runs
    return runs.queue_manager()


def _log_text(workflow_dir: Path, name: str = "minimal.log") -> str:
    try:
        return Path(workflow_dir, "logs", name).read_text(errors="replace")
    except OSError:
        return ""


def log_lines(workflow_dir: Path, lines: int = 40, detail: str = "minimal") -> list[str]:
    name = {"minimal": "minimal.log", "commands": "commands-and-run-times.log",
            "all": "all.log"}.get(detail, "minimal.log")
    text = [line for line in _log_text(workflow_dir, name).splitlines() if line.strip()]
    return text[-max(1, min(lines, 2000)):]


# Runs this process started, reaped here so an ended run is no zombie that
# os.kill(pid, 0) still finds.
_children: list = []


def _reap() -> None:
    _children[:] = [p for p in _children if p.poll() is None]


def _local_running(workflow_dir: Path) -> bool:
    _reap()
    pid_dir = Path(workflow_dir, "pids")
    if not pid_dir.is_dir():
        return False
    alive = False
    for pid_file in pid_dir.iterdir():
        try:
            os.kill(int(pid_file.name), 0)
            alive = True
        except (ValueError, ProcessLookupError):
            pid_file.unlink(missing_ok=True)
        except PermissionError:
            alive = True
    return alive


def _outcome(workflow_dir: Path) -> str:
    """finished, failed or cancelled, from the log the run wrote."""
    text = _log_text(workflow_dir)
    if not text:
        return ""
    outcome = classify_log_outcome(text)
    return "failed" if outcome == "error" else outcome


def status(workspace: Path, workflow: str, online: bool) -> dict:
    workflow_dir = Path(workspace, workflow)
    if online:
        qm = _queue()
        if qm is None:
            raise RunError("The run queue cannot be reached right now; try again in a minute.")
        from src.sync import runs
        info = runs.status(qm, workspace, workflow)
        info.pop("log", None)
        state = info["status"]
        running = state in runs.ACTIVE
    else:
        running = _local_running(workflow_dir)
        info = {"workflow": workflow, "status": "running" if running else "idle",
                "progress": None, "current_step": "", "queue_position": None,
                "error": "", "run_id": None, "run_name": ""}
        latest = _runs(workflow_dir).list_runs()
        if latest:
            info.update(run_id=latest[0]["id"], run_name=latest[0].get("name", ""))
    if not running:
        outcome = _outcome(workflow_dir)
        if outcome:
            info["status"] = outcome
    run_id = info.get("run_id")
    if run_id:
        run = _runs(workflow_dir).get(run_id) or {}
        if run.get("status") and not running:
            info["status"] = {"finished": "finished", "failed": "failed",
                              "cancelled": "cancelled"}.get(run["status"], info["status"])
    info["running"] = running
    info["log"] = log_lines(workflow_dir, 8)
    if not running and info["status"] == "failed":
        errors = [line for line in log_lines(workflow_dir, 400, "all") if "error" in line.lower()]
        if errors:
            info["error"] = info.get("error") or errors[-1][:500]
    return info


def start(app_root: Path, workspace: Path, workflow: str, target: str, params: dict,
          name: str, online: bool, multi_run: bool) -> dict:
    workflow_dir = Path(workspace, workflow)
    if online:
        qm = _queue()
        if qm is None:
            raise RunError("The run queue cannot be reached right now; try again in a minute.")
        from src.sync import runs
        try:
            return runs.start(qm, workspace, workflow, target, params, name)
        except LookupError as e:
            raise RunError(f"{e}. Wait for it to end, or stop it with stop_run.") from e
        except FileNotFoundError as e:
            raise RunError(f"Input files are missing: {e}") from e
        except (ValueError, RuntimeError) as e:
            raise RunError(str(e)) from e

    if _local_running(workflow_dir):
        raise RunError(f"{workflow} is already running. Wait for it to end, or stop it with stop_run.")
    # The same start as the Run button's (src/workflow/start.py): the run
    # folder, the run it follows, the workflow process; the processing report
    # then records the run as it records any other.
    from src.workflow.start import launch_local, prepare
    describe.write_params(workflow_dir, params)
    module, _, cls = target.partition(":")
    run_id = prepare(workflow_dir, multi_run, name)
    # Its own session, and no stdout: over stdio, stdout is the protocol
    # stream, and the run outlives the assistant's connection.
    proc = launch_local(workflow_dir, cls, module, run_id,
                        app_root=str(Path(app_root).resolve()), detach=True)
    if proc is not None:
        _children.append(proc)
    return status(workspace, workflow, online)


def stop(workspace: Path, workflow: str, online: bool, multi_run: bool) -> dict:
    workflow_dir = Path(workspace, workflow)
    if online:
        qm = _queue()
        if qm is None:
            raise RunError("The run queue cannot be reached right now; try again in a minute.")
        from src.sync import runs
        runs.stop(qm, workspace, workflow)
        return status(workspace, workflow, online)
    pid_dir = Path(workflow_dir, "pids")
    stopped = False
    if pid_dir.is_dir():
        for pid_file in pid_dir.iterdir():
            try:
                os.kill(int(pid_file.name), signal.SIGTERM)
                stopped = True
            except (ValueError, ProcessLookupError, PermissionError):
                pass
        shutil.rmtree(pid_dir, ignore_errors=True)
    if stopped:
        from src.workflow.Logger import Logger
        Logger(workflow_dir).log("WORKFLOW CANCELLED")
        if multi_run:
            from src.workflow.RunManager import CANCELLED, RUNNING
            runs = _runs(workflow_dir)
            for run in runs.list_runs(RUNNING):
                runs.finish(run["id"], CANCELLED)
    return status(workspace, workflow, online)
