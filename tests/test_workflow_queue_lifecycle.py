"""Queue acknowledgement and PID ownership jointly guard workflow admission."""

import importlib
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.workflow.process_state import register_process_marker
from src.workflow.WorkflowManager import WorkflowManager


def job(state):
    return SimpleNamespace(
        status=SimpleNamespace(value=state), progress=0.5, current_step="Native tool",
        queue_position=None, queue_length=0, enqueued_at=None, started_at=None,
        result=None, error=None,
    )


@pytest.fixture
def manager(tmp_path):
    manager = object.__new__(WorkflowManager)
    manager.name = "Test Workflow"
    manager.workflow_dir = tmp_path
    manager.executor = SimpleNamespace(pid_dir=tmp_path / "pids")
    manager.executor.pid_dir.mkdir()
    manager.parameter_manager = Mock()
    manager.parameter_manager.get_parameters_from_json.return_value = {}
    manager.logger = Mock()
    manager.multi_run = False
    manager.queue_error = importlib.import_module("src.workflow.QueueManager").QueueStateUnavailableError
    manager._queue_manager = Mock()
    manager._queue_manager.is_available = True
    manager._queue_manager.load_job_id.return_value = "existing-job"
    manager._queue_manager.get_job_info.return_value = job("started")
    manager._queue_manager.cancel_job.return_value = True
    return manager


@pytest.fixture
def owned_child(manager):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    marker = manager.executor.pid_dir / str(child.pid)
    register_process_marker(marker, child.pid)
    try:
        yield child, marker
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def test_cancel_request_does_not_signal_workhorse_before_queue_ack(manager, owned_child):
    child, marker = owned_child
    manager._stop_local_workflow = Mock()
    assert manager.stop_workflow() is True
    manager._stop_local_workflow.assert_not_called()
    assert child.poll() is None and marker.exists()
    assert manager.get_workflow_status()["status"] == "started"
    assert manager.get_workflow_status()["running"] is True


def test_terminal_ack_with_owned_live_process_remains_busy_until_exit(manager, owned_child):
    child, marker = owned_child
    manager._queue_manager.get_job_info.return_value = job("canceled")
    manager._start_workflow_local = Mock()
    assert manager.get_workflow_status()["status"] == "stopping"
    with pytest.raises(ValueError, match="already running"):
        manager.start_workflow()
    manager.parameter_manager.save_parameters.assert_not_called()
    manager._start_workflow_local.assert_not_called()
    assert marker.is_file() and child.poll() is None
    child.kill()
    child.wait(timeout=5)
    assert manager.get_workflow_status()["running"] is False


def test_post_ack_stop_signals_only_known_local_leftovers(manager, owned_child):
    child, _marker = owned_child
    manager._queue_manager.get_job_info.return_value = job("canceled")
    assert manager.stop_workflow() is True
    child.wait(timeout=5)
    assert manager.get_workflow_status()["running"] is False


@pytest.mark.parametrize("queue_available", [False, True])
def test_unavailable_queue_retains_job_reference_and_blocks_admission(manager, queue_available):
    manager._queue_manager.is_available = queue_available
    if queue_available:
        manager._queue_manager.get_job_info.side_effect = manager.queue_error("Redis is unavailable")
    manager._start_workflow_local = Mock()
    status = manager.get_workflow_status()
    assert status["running"] and status["status"] == "unknown"
    assert status["job_id"] == "existing-job"
    with pytest.raises(ValueError, match="already running"):
        manager.start_workflow()
    manager._queue_manager.clear_job_id.assert_not_called()
    manager._start_workflow_local.assert_not_called()


def test_unconfirmed_queue_cancellation_never_falls_back_to_local_signals(manager, owned_child):
    child, marker = owned_child
    manager._queue_manager.cancel_job.return_value = False
    manager._stop_local_workflow = Mock()
    assert manager.stop_workflow() is False
    manager._stop_local_workflow.assert_not_called()
    assert marker.is_file() and child.poll() is None


def test_no_such_job_clears_only_the_reference_that_was_queried(manager):
    manager._queue_manager.get_job_info.return_value = None
    assert manager.get_workflow_status()["running"] is False
    manager._queue_manager.clear_job_id.assert_called_once_with(
        manager.workflow_dir, expected_job_id="existing-job"
    )


def test_uncertain_submission_retains_uuid_without_running_duplicate_locally(manager):
    manager.run_id = None
    manager._start_workflow_local = Mock()
    manager._queue_manager.submit_job.side_effect = manager.queue_error("Queue acknowledgement lost")
    with pytest.raises(manager.queue_error, match="acknowledgement lost"):
        manager._start_workflow_queued()
    proposed_id = manager._queue_manager.submit_job.call_args.kwargs["job_id"]
    manager._queue_manager.store_job_id.assert_called_once_with(manager.workflow_dir, proposed_id)
    manager._start_workflow_local.assert_not_called()
