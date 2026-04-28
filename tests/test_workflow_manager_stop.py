"""
Tests for WorkflowManager.stop_workflow / get_workflow_status interaction.

Bug being fixed (follow-up to PR #383): the RQ worker actually terminates when
the user clicks "Stop Workflow", but the Streamlit UI still shows
"workflow is running" and pressing Stop a second time produces an
"error has occurred" message instead of "workflow has been cancelled".

Root causes:
  1. stop_workflow clears .job_id on success, so the next get_workflow_status
     poll falls through to the local-mode pid_dir fallback. The killed worker
     left stale child PID files in pid_dir, so the fallback wrongly returns
     running=True.
  2. The worker never wrote 'WORKFLOW FINISHED' to the log because it was
     killed mid-execution. The UI's static-display branch only knows two
     outcomes (FINISHED -> success, else -> error), so a cancelled run is
     misreported as an error.

These tests pin both behaviours.
"""

import os
import sys
import types

import pytest

fakeredis = pytest.importorskip("fakeredis")
rq = pytest.importorskip("rq")
streamlit = pytest.importorskip("streamlit")
pyopenms = pytest.importorskip("pyopenms")

from rq import Queue
from rq.job import Job, JobStatus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow.Logger import Logger
from src.workflow.QueueManager import QueueManager
from src.workflow.WorkflowManager import WorkflowManager


def _make_queue_manager() -> QueueManager:
    """Build a QueueManager wired to fake Redis, bypassing __init__."""
    qm = QueueManager.__new__(QueueManager)
    qm._redis = fakeredis.FakeStrictRedis()
    qm._queue = Queue(QueueManager.QUEUE_NAME, connection=qm._redis)
    qm._is_online = True
    qm._init_attempted = True
    qm._default_timeout = 7200
    qm._default_result_ttl = 86400
    return qm


def _force_started(job: Job, worker_name: str = "rq:worker:test-worker") -> None:
    job.set_status(JobStatus.STARTED)
    job.worker_name = worker_name
    job.save()


def _make_workflow_manager(tmp_path, monkeypatch) -> WorkflowManager:
    """
    Build a minimal WorkflowManager wired to a fakeredis-backed QueueManager.

    Bypasses __init__ (which constructs a StreamlitUI and reads session
    state). Only the attributes used by stop_workflow / get_workflow_status
    are populated:
        - workflow_dir  (real tmp dir)
        - logger        (real Logger; streamlit-free)
        - executor      (SimpleNamespace exposing pid_dir; CommandExecutor
                         itself imports streamlit so we cannot instantiate it)
        - _queue_manager (fakeredis-backed QueueManager)

    A stale child PID file is dropped in pid_dir to simulate the state the
    worker leaves behind when it is force-killed mid-execution.
    """
    workflow_dir = tmp_path / "wf"
    workflow_dir.mkdir()

    pid_dir = workflow_dir / "pids"
    pid_dir.mkdir()
    (pid_dir / "12345").touch()

    qm = _make_queue_manager()
    job = qm._queue.enqueue(os.getcwd, job_id="wf-job")
    _force_started(job)
    qm.store_job_id(workflow_dir, "wf-job")

    monkeypatch.setattr(
        "rq.command.send_stop_job_command",
        lambda *a, **kw: None,
    )

    wm = WorkflowManager.__new__(WorkflowManager)
    wm.workflow_dir = workflow_dir
    wm.logger = Logger(workflow_dir)
    wm.executor = types.SimpleNamespace(pid_dir=pid_dir)
    wm._queue_manager = qm
    return wm


def test_stop_workflow_clears_running_state_in_queue_mode(tmp_path, monkeypatch):
    """
    Bug #1: after a successful queue cancel, get_workflow_status must report
    running=False. Currently the stale pid_dir keeps the local-mode fallback
    returning running=True.
    """
    wm = _make_workflow_manager(tmp_path, monkeypatch)

    assert wm.stop_workflow() is True

    status = wm.get_workflow_status()
    assert status["running"] is False, (
        "After cancel, get_workflow_status must not report the workflow as "
        "still running."
    )

    pid_dir = wm.executor.pid_dir
    assert not (pid_dir.exists() and any(pid_dir.iterdir())), (
        "stop_workflow must clean up the stale pid_dir left behind by the "
        "killed worker; otherwise the local-mode fallback in "
        "get_workflow_status flips running back to True."
    )


def test_stop_workflow_writes_cancellation_marker_to_log(tmp_path, monkeypatch):
    """
    Bug #2: the static log-display branch needs a way to tell 'cancelled'
    apart from 'crashed'. stop_workflow must drop a 'WORKFLOW CANCELLED'
    marker into the log so the UI can render the right message.
    """
    wm = _make_workflow_manager(tmp_path, monkeypatch)
    wm.logger.log("STARTING WORKFLOW")  # mimic a partial run

    assert wm.stop_workflow() is True

    logs_dir = wm.workflow_dir / "logs"
    for log_name in ("minimal.log", "commands-and-run-times.log", "all.log"):
        content = (logs_dir / log_name).read_text(encoding="utf-8")
        assert "WORKFLOW CANCELLED" in content, (
            f"{log_name} should contain the WORKFLOW CANCELLED marker."
        )
        assert "WORKFLOW FINISHED" not in content, (
            f"{log_name} must not claim the workflow finished."
        )


def test_stop_workflow_is_idempotent(tmp_path, monkeypatch):
    """
    Pressing Stop a second time (or stop firing twice on Streamlit rerun)
    must not raise and must keep running=False. The first call's user intent
    has already been satisfied; subsequent calls should be safe no-ops.
    """
    wm = _make_workflow_manager(tmp_path, monkeypatch)

    assert wm.stop_workflow() is True

    # Second call: must not raise, get_workflow_status must remain not-running.
    wm.stop_workflow()
    assert wm.get_workflow_status()["running"] is False


