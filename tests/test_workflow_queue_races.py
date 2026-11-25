"""Queue acknowledgement and shared job references remain authoritative."""

import importlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis
import psutil
import pytest
from rq import Queue
from rq.job import Job, JobStatus
from streamlit.testing.v1 import AppTest

from src.workflow.QueueManager import QueueManager, QueueStateUnavailableError


@pytest.fixture
def queue_manager():
    manager = object.__new__(QueueManager)
    manager._redis = fakeredis.FakeStrictRedis()
    manager._queue = Queue(QueueManager.QUEUE_NAME, connection=manager._redis)
    manager._is_online = True
    manager._init_attempted = True
    manager._default_timeout = 7200
    manager._default_result_ttl = manager._default_failure_ttl = 86400
    return manager


def _started(manager, identity="started-job"):
    job = manager._queue.enqueue(os.getcwd, job_id=identity)
    job.set_status(JobStatus.STARTED)
    job.worker_name = "release-test-worker"
    job.save()
    return job


def test_started_stop_waits_for_worker_acknowledgement(queue_manager, monkeypatch):
    job = _started(queue_manager)
    calls = []
    monkeypatch.setattr("rq.command.send_stop_job_command", lambda _connection, identity: calls.append(identity))
    assert queue_manager.cancel_job(job.id)
    assert calls == [job.id]
    assert queue_manager.get_job_info(job.id).status.value == "started"
    job.set_status(JobStatus.STOPPED)
    job.save()
    assert queue_manager.get_job_info(job.id).status.value == "canceled"


def test_failed_stop_delivery_does_not_claim_running_job_cancelled(queue_manager, monkeypatch):
    job = _started(queue_manager)
    monkeypatch.setattr("rq.command.send_stop_job_command", Mock(side_effect=ConnectionError("stop response lost")))
    assert queue_manager.cancel_job(job.id) is False
    assert Job.fetch(job.id, connection=queue_manager._redis).get_status() == JobStatus.STARTED


@pytest.mark.parametrize("state", [JobStatus.FINISHED, JobStatus.FAILED])
def test_late_stop_keeps_completed_outcome(queue_manager, state):
    job = _started(queue_manager)
    job.set_status(state)
    job.save()
    assert queue_manager.cancel_job(job.id) is False
    assert Job.fetch(job.id, connection=queue_manager._redis).get_status() == state


def test_worker_completion_racing_stop_does_not_relabel_finished_job(queue_manager, monkeypatch):
    from rq.exceptions import InvalidJobOperation

    job = _started(queue_manager)

    def finished(_connection, _identity):
        job.set_status(JobStatus.FINISHED)
        job.save()
        raise InvalidJobOperation("worker already finished")

    monkeypatch.setattr("rq.command.send_stop_job_command", finished)
    assert queue_manager.cancel_job(job.id) is False
    assert queue_manager.get_job_info(job.id).status.value == "finished"


def test_queued_cancel_does_not_cross_the_worker_pickup_gap(queue_manager):
    job = queue_manager._queue.enqueue(os.getcwd, job_id="being-picked-up")
    queue_manager._redis.lrem(queue_manager._queue.key, 1, job.id)
    # RQ has claimed it, but has not yet changed queued -> started.
    assert queue_manager.cancel_job(job.id) is False
    assert Job.fetch(job.id, connection=queue_manager._redis).get_status() == JobStatus.QUEUED


def test_queued_cancel_retries_if_another_queue_entry_changes(queue_manager, monkeypatch):
    from redis.exceptions import WatchError

    job = queue_manager._queue.enqueue(os.getcwd, job_id="still-waiting")
    original = queue_manager._redis.pipeline
    attempts = []

    def pipeline(*args, **kwargs):
        pipe = original(*args, **kwargs)
        execute = pipe.execute

        def conflict_once(*execute_args, **execute_kwargs):
            attempts.append(True)
            if len(attempts) == 1:
                raise WatchError("another worker changed the queue")
            return execute(*execute_args, **execute_kwargs)

        pipe.execute = conflict_once
        return pipe

    monkeypatch.setattr(queue_manager._redis, "pipeline", pipeline)
    assert queue_manager.cancel_job(job.id)
    assert Job.fetch(job.id, connection=queue_manager._redis).get_status() == JobStatus.CANCELED
    assert len(attempts) >= 2


def test_unconfirmed_enqueue_is_not_a_definite_failure(queue_manager, monkeypatch):
    enqueue = queue_manager._queue.enqueue

    def committed_but_unacknowledged(*args, **kwargs):
        enqueue(*args, **kwargs)
        raise ConnectionError("enqueue acknowledgement lost")

    monkeypatch.setattr(queue_manager._queue, "enqueue", committed_but_unacknowledged)
    with pytest.raises(QueueStateUnavailableError, match="could not be confirmed"):
        queue_manager.submit_job(os.getcwd, job_id="accepted-once")
    assert Job.fetch("accepted-once", connection=queue_manager._redis).get_status() == JobStatus.QUEUED
    assert queue_manager._queue.job_ids == ["accepted-once"]


def test_status_read_outage_is_distinct_from_missing_job(queue_manager, monkeypatch):
    assert queue_manager.get_job_info("not-created") is None
    monkeypatch.setattr(Job, "fetch", Mock(side_effect=ConnectionError("Redis unavailable")))
    with pytest.raises(QueueStateUnavailableError, match="temporarily unavailable"):
        queue_manager.get_job_info("potentially-still-running")


def test_old_status_poll_cannot_clear_a_new_job_reference(queue_manager, tmp_path):
    queue_manager.store_job_id(tmp_path, "old-job")
    observed = queue_manager.load_job_id(tmp_path)
    queue_manager.store_job_id(tmp_path, "new-job")
    queue_manager.clear_job_id(tmp_path, expected_job_id=observed)
    assert queue_manager.load_job_id(tmp_path) == "new-job"
    queue_manager.clear_job_id(tmp_path, expected_job_id="new-job")
    assert queue_manager.load_job_id(tmp_path) is None


def test_job_reference_reads_keep_previous_complete_value_until_atomic_publish(queue_manager, tmp_path, monkeypatch):
    queue_manager.store_job_id(tmp_path, "previous-job")
    entered, release = Event(), Event()
    replace = Path.replace

    def pause(path, target):
        if Path(target) == tmp_path / ".job_id":
            entered.set()
            assert release.wait(10)
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", pause)
    with ThreadPoolExecutor(1) as pool:
        write = pool.submit(queue_manager.store_job_id, tmp_path, "new-complete-job")
        try:
            assert entered.wait(10)
            assert queue_manager.load_job_id(tmp_path) == "previous-job"
        finally:
            release.set()
        write.result(timeout=10)
    assert queue_manager.load_job_id(tmp_path) == "new-complete-job"
    assert not list(tmp_path.glob(".job-id-*.tmp"))


def test_disappearing_job_reference_and_repeated_clear_are_safe(queue_manager, tmp_path, monkeypatch):
    queue_manager.store_job_id(tmp_path, "completed-job")
    read = Path.read_text

    def removed(path, *args, **kwargs):
        if path == tmp_path / ".job_id":
            path.unlink(missing_ok=True)
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", removed)
    assert queue_manager.load_job_id(tmp_path) is None
    queue_manager.clear_job_id(tmp_path)
    queue_manager.clear_job_id(tmp_path, expected_job_id="completed-job")


def test_reference_publication_error_keeps_previous_reference(queue_manager, tmp_path, monkeypatch):
    queue_manager.store_job_id(tmp_path, "previous-job")
    replace = Path.replace

    def denied(path, target):
        if Path(target) == tmp_path / ".job_id":
            raise PermissionError("job reference directory is read-only")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", denied)
    with pytest.raises(PermissionError, match="read-only"):
        queue_manager.store_job_id(tmp_path, "new-job")
    assert queue_manager.load_job_id(tmp_path) == "previous-job"
    assert not list(tmp_path.glob(".job-id-*.tmp"))


class MarkerInspectingWorkflow:
    def execution(self):
        marker = self.executor.pid_dir / str(os.getpid())
        record = json.loads(marker.read_text())
        assert record["pid"] == os.getpid()
        assert record["create_time"] == psutil.Process().create_time()
        (self.results_dir / "worker-registration.json").write_text(json.dumps(record))
        return True


def test_queued_workhorse_has_owned_tracking_before_first_native_command(tmp_path, monkeypatch):
    tasks = importlib.import_module("src.workflow.tasks")
    job = SimpleNamespace(meta={}, save_meta=Mock())
    monkeypatch.setattr("rq.get_current_job", lambda: job)
    directory = tmp_path / "test-workflow"
    directory.mkdir()
    (directory / "params.json").write_text("{}")
    result = tasks.execute_workflow(str(directory), "MarkerInspectingWorkflow", __name__)
    assert result["success"] is True
    assert (directory / "results/worker-registration.json").is_file()
    assert not directory.joinpath("pids").exists()


@pytest.mark.parametrize("state", ["unknown", "stopping"])
def test_queue_recovery_status_is_visible_without_claiming_completion(state):
    script = """
import streamlit as st
from src.workflow.StreamlitUI import StreamlitUI
ui=object.__new__(StreamlitUI)
ui._show_queue_status({'status':st.session_state.state,'job_id':'existing-job','error':'Wait for confirmation before starting another analysis.'})
"""
    app = AppTest.from_string(script)
    app.session_state.state = state
    app.run(timeout=30)
    assert not app.exception
    assert any("Wait for confirmation" in warning.value for warning in app.warning)
    assert not app.success
