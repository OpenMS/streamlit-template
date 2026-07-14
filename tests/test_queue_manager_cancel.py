"""
Tests for QueueManager.cancel_job - the "stop workflow" path used in online
mode where workflows are executed by RQ workers (the vendor's queue).

Bug being fixed: when a workflow is mid-execution in an RQ worker and the
user clicks "Stop Workflow", QueueManager.cancel_job calls Job.cancel() on
the RQ Job. For a job in the "started" state this only marks the job as
canceled in the Redis registries; the worker keeps executing the workflow
and the user sees inconsistent / "weird" state (worker still appending to
logs, status flipping around, etc.).

To actually stop a running RQ job, RQ exposes
rq.command.send_stop_job_command(connection, job_id) which messages the
worker over Redis pubsub to interrupt the work-horse.
"""

import os
import sys

import pytest

fakeredis = pytest.importorskip("fakeredis")
rq = pytest.importorskip("rq")
from rq import Queue
from rq.job import Job, JobStatus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow.QueueManager import QueueManager


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
    """Move a queued job into the 'started' state with a worker assigned."""
    job.set_status(JobStatus.STARTED)
    job.worker_name = worker_name
    job.save()


def test_cancel_queued_job_marks_it_canceled():
    qm = _make_queue_manager()
    qm._queue.enqueue(os.getcwd, job_id="queued-job")

    assert qm.cancel_job("queued-job") is True

    refreshed = Job.fetch("queued-job", connection=qm._redis)
    assert refreshed.get_status() == JobStatus.CANCELED


def test_cancel_started_job_sends_stop_command_to_worker(monkeypatch):
    """
    Reproduces the vendor-queue stop bug.

    A workflow that is actively running in a worker must be stopped by
    sending a stop-job command to the worker. The previous implementation
    only called Job.cancel(), which left the worker running.
    """
    qm = _make_queue_manager()
    job = qm._queue.enqueue(os.getcwd, job_id="started-job")
    _force_started(job)

    stop_calls: list[str] = []

    def fake_send_stop_job_command(connection, job_id, *args, **kwargs):
        stop_calls.append(job_id)

    import rq.command as rq_command
    monkeypatch.setattr(
        rq_command, "send_stop_job_command", fake_send_stop_job_command
    )

    result = qm.cancel_job("started-job")

    assert result is True, "cancel_job should report success for started jobs"
    assert stop_calls == ["started-job"], (
        "cancel_job must call send_stop_job_command for started jobs - "
        "otherwise the RQ worker keeps running the workflow."
    )


def test_cancel_already_canceled_job_does_not_raise():
    """
    User double-clicks 'Stop Workflow' or stop is invoked twice on rerun.
    The second call must not surface InvalidJobOperation as a 'weird error'.
    """
    qm = _make_queue_manager()
    job = qm._queue.enqueue(os.getcwd, job_id="dup-cancel")
    job.cancel()
    assert Job.fetch("dup-cancel", connection=qm._redis).get_status() == JobStatus.CANCELED

    # Must not raise; intent (job is canceled) is already satisfied.
    assert qm.cancel_job("dup-cancel") is True


def test_cancel_missing_job_returns_false():
    qm = _make_queue_manager()
    assert qm.cancel_job("does-not-exist") is False


def test_started_status_without_worker_is_handled_gracefully(monkeypatch):
    """
    Edge case: job is marked started but has no worker_name yet (race between
    worker pickup and stop click). cancel_job must not raise; it should fall
    back to canceling the job in the registry.
    """
    qm = _make_queue_manager()
    job = qm._queue.enqueue(os.getcwd, job_id="started-no-worker")
    job.set_status(JobStatus.STARTED)
    job.save()

    stop_calls: list[str] = []

    def fake_send_stop_job_command(connection, job_id, *args, **kwargs):
        stop_calls.append(job_id)

    import rq.command as rq_command
    monkeypatch.setattr(
        rq_command, "send_stop_job_command", fake_send_stop_job_command
    )

    result = qm.cancel_job("started-no-worker")

    assert result is True
    # Without a worker_name there is nothing to send the stop command to.
    assert stop_calls == []
    assert (
        Job.fetch("started-no-worker", connection=qm._redis).get_status()
        == JobStatus.CANCELED
    )


def test_stopped_status_is_mapped_in_get_job_info(monkeypatch):
    """
    After send_stop_job_command runs, RQ marks the job 'stopped'. The status
    map in get_job_info must recognise it; otherwise the UI would show the
    job as still 'queued', which is the user-visible 'weird error'.
    """
    qm = _make_queue_manager()
    job = qm._queue.enqueue(os.getcwd, job_id="stopped-job")
    job.set_status(JobStatus.STOPPED)
    job.save()

    info = qm.get_job_info("stopped-job")
    assert info is not None
    assert info.status == __import__(
        "src.workflow.QueueManager", fromlist=["JobStatus"]
    ).JobStatus.CANCELED, (
        "RQ 'stopped' status should be reported as CANCELED to the UI; "
        "otherwise stopped jobs appear stuck in 'queued'."
    )
