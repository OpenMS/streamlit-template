"""Workflow runs in an online workspace, directed from the desktop app.

The sync service queues a run the way the online app's Run button does in
queue mode: it writes the workflow's ``params.json``, submits
``src.workflow.tasks.execute_workflow`` to the RQ queue and records the job
id in ``<workflow>/.job_id``, so the online app's own pages show the run as
if it had been started there. Stopping cancels the job and writes the
``WORKFLOW CANCELLED`` marker, as ``WorkflowManager.stop_workflow`` does.

Which workflows can be run is ``workspace_sync.workflows`` in settings.json,
a map from workflow directory name to ``"module:Class"``. No Streamlit here:
the service runs without it.
"""

import json
import os
import shutil
import time
from pathlib import Path

from . import paths

WORKSPACE_REF = "sync-workspace://"   # kept equal to client.WORKSPACE_REF
LOG_TAIL_LINES = 20
ACTIVE = ("queued", "started", "deferred")

_queue = None


def queue_manager():
    """The RQ queue, or None when Redis cannot be reached."""
    global _queue
    if _queue is None or not _queue.is_available:
        from src.workflow.QueueManager import QueueManager
        _queue = QueueManager()
    return _queue if _queue.is_available else None


def resolve_params(workspace: Path, params: dict) -> tuple[dict, list[str]]:
    """Point the desktop's input paths at this workspace's copies.

    Returns the parameters and every referenced input not (yet) uploaded.
    """
    missing: list[str] = []

    def convert(value):
        if isinstance(value, str) and value.startswith(WORKSPACE_REF):
            rel = value[len(WORKSPACE_REF):]
            if not paths.is_pushable(rel):
                raise ValueError(f"not an input path: {rel!r}")
            target = Path(workspace, rel)
            if not target.exists():
                missing.append(rel)
            return str(target)
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        return value

    return convert(params), missing


def _log_tail(workflow_dir: Path) -> list[str]:
    try:
        lines = Path(workflow_dir, "logs", "minimal.log").read_text(errors="replace").splitlines()
    except OSError:
        return []
    # Logger separates messages by a blank line.
    return [line for line in lines if line.strip()][-LOG_TAIL_LINES:]


def status(qm, workspace: Path, workflow: str) -> dict:
    """The state of the workflow's last run, as the online Run page sees it."""
    workflow_dir = Path(workspace, workflow)
    info = {"workflow": workflow, "status": "idle", "progress": None, "current_step": "",
            "queue_position": None, "error": "", "log": _log_tail(workflow_dir)}
    job_id = qm.load_job_id(workflow_dir) if qm else None
    job = qm.get_job_info(job_id) if job_id else None
    if job is not None:
        # The last line of a traceback names the exception.
        error = (job.error or "").strip().splitlines()
        info.update(status=job.status.value, progress=job.progress,
                    current_step=job.current_step, queue_position=job.queue_position,
                    error=error[-1] if error else "")
    return info


def start(qm, workspace: Path, workflow: str, target: str, params: dict) -> dict:
    """Write the parameters and queue the run. Raises LookupError when the
    workflow is already running, FileNotFoundError for missing inputs."""
    workflow_dir = Path(workspace, workflow)
    current = status(qm, workspace, workflow)
    if current["status"] in ACTIVE:
        raise LookupError(f"{workflow} is already {current['status']}")
    params, missing = resolve_params(workspace, params)
    if missing:
        raise FileNotFoundError(", ".join(missing))
    workflow_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(workflow_dir, "params.json.sync-tmp")
    tmp.write_text(json.dumps(params, indent=4), encoding="utf-8")
    os.replace(tmp, Path(workflow_dir, "params.json"))

    from src.workflow.tasks import execute_workflow
    module, _, cls = target.partition(":")
    job_id = qm.submit_job(
        func=execute_workflow,
        kwargs={"workflow_dir": str(workflow_dir), "workflow_class": cls,
                "workflow_module": module},
        job_id=f"workflow-{workspace.name}-{workflow}-{int(time.time())}",
        description=f"Workflow: {workflow} (from the desktop app)",
    )
    if not job_id:
        raise RuntimeError("the queue did not accept the run")
    qm.store_job_id(workflow_dir, job_id)
    return status(qm, workspace, workflow)


def stop(qm, workspace: Path, workflow: str) -> dict:
    workflow_dir = Path(workspace, workflow)
    job_id = qm.load_job_id(workflow_dir)
    if job_id and qm.cancel_job(job_id):
        from src.workflow.Logger import Logger
        Logger(workflow_dir).log("WORKFLOW CANCELLED")
        shutil.rmtree(Path(workflow_dir, "pids"), ignore_errors=True)
    return status(qm, workspace, workflow)
