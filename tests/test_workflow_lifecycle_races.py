"""Force start, registration and cancellation races without timing sleeps."""

import json
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from src.workflow.file_lock import file_lock
from src.workflow.process_state import process_namespace, register_process_marker
from src.workflow.RunManager import RunManager
from src.workflow.WorkflowManager import WorkflowManager


@pytest.fixture
def manager(tmp_path):
    instance = object.__new__(WorkflowManager)
    instance.name = "Test Workflow"
    instance.workflow_dir = tmp_path / "test-workflow"
    instance.workflow_dir.mkdir()
    instance.executor = SimpleNamespace(pid_dir=instance.workflow_dir / "pids")
    instance.parameter_manager = Mock()
    instance.parameter_manager.save_parameters.return_value = True
    instance.parameter_manager.get_parameters_from_json.return_value = {}
    instance.logger = Mock()
    instance._queue_manager = None
    instance.run_id = None
    instance.multi_run = False
    return instance


def owned_process(marker, monkeypatch):
    """Use an explicit birth token rather than trusting a numeric filename."""
    pid = int(marker.name)
    marker.write_text(json.dumps({"schema": 1, "pid": pid, "create_time": 100.0, "namespace": process_namespace()}))
    process = Mock()
    process.pid = pid
    process.create_time.return_value = 100.0
    process.is_running.return_value = True
    process.status.return_value = psutil.STATUS_SLEEPING
    lookup = Mock(return_value=process)
    monkeypatch.setattr(psutil, "Process", lookup)
    return process, lookup


def test_simultaneous_start_and_stop_cannot_enter_launch_in_another_session(manager):
    other = object.__new__(WorkflowManager)
    other.__dict__ = manager.__dict__.copy()
    other.parameter_manager = Mock()
    other._start_workflow_local = Mock()
    other._stop_local_workflow = Mock(return_value=True)
    entered, release = Event(), Event()

    def launch():
        entered.set()
        assert release.wait(10)

    manager._start_workflow_local = launch
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(manager.start_workflow)
        try:
            assert entered.wait(10)
            with pytest.raises(ValueError, match="Another session"):
                other.start_workflow()
            assert other.stop_workflow() is False
            other.parameter_manager.save_parameters.assert_not_called()
            other._start_workflow_local.assert_not_called()
            other._stop_local_workflow.assert_not_called()
        finally:
            release.set()
        first.result(timeout=10)


def test_stale_start_button_does_not_create_run_or_save_settings_while_worker_is_active(manager):
    manager.multi_run = True
    manager._new_run = Mock()
    manager._start_workflow_local = Mock()
    manager.get_workflow_status = lambda: {"running": True}
    with pytest.raises(ValueError, match="already running"):
        manager.start_workflow()
    manager._new_run.assert_not_called()
    manager._start_workflow_local.assert_not_called()
    manager.parameter_manager.save_parameters.assert_not_called()


def test_failed_parameter_save_never_dispatches_or_consumes_run(manager):
    manager.multi_run = True
    manager._new_run = Mock()
    manager._start_workflow_local = Mock()
    manager.parameter_manager.save_parameters.return_value = False
    with pytest.raises(ValueError, match="could not be saved"):
        manager.start_workflow()
    manager._new_run.assert_not_called()
    manager._start_workflow_local.assert_not_called()


@pytest.mark.parametrize("error", [FileNotFoundError("missing interpreter"), BlockingIOError("process limit")])
def test_spawn_failure_finalizes_the_created_run_and_releases_start_lock(manager, monkeypatch, error):
    manager.multi_run = True
    manager.runs = RunManager(manager.workflow_dir)

    def new_run():
        manager.run_id = manager.runs.new_run("Could not launch")

    def launch(*_args, **_kwargs):
        raise error

    manager._new_run = new_run
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(type(error), match=str(error)):
        manager.start_workflow()
    assert manager.runs.get(manager.run_id)["status"] == "failed"
    with file_lock(manager.workflow_dir / ".locks/execution.lock", blocking=False):
        pass


def test_registration_failure_terminates_and_reaps_the_real_untracked_worker(manager, monkeypatch):
    popen = subprocess.Popen
    children = []

    def launch(*_args, **_kwargs):
        child = popen([sys.executable, "-c", "import time; time.sleep(30)"])
        children.append(child)
        return child

    def cannot_track(_marker, _pid):
        raise PermissionError("PID storage unavailable")

    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setitem(WorkflowManager._start_workflow_local.__globals__, "register_process_marker", cannot_track)
    try:
        with pytest.raises(PermissionError, match="PID storage unavailable"):
            manager._start_workflow_local()
        assert len(children) == 1 and children[0].poll() is not None
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_fast_worker_cleanup_retains_other_tracking_files(manager, monkeypatch):
    folder = manager.executor.pid_dir
    folder.mkdir()
    other = folder / "54322"
    other.touch()
    note = folder / "conversion.json"
    note.write_text("keep")
    process = SimpleNamespace(pid=54321, poll=lambda: 0)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: process)
    manager._start_workflow_local()
    assert not (folder / "54321").exists()
    assert other.is_file() and note.read_text() == "keep"


def test_worker_ending_before_marker_registration_is_a_safe_noop(manager, monkeypatch):
    process = SimpleNamespace(pid=54321, poll=lambda: 0)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: process)

    def already_cleaned(*_args, **_kwargs):
        manager.executor.pid_dir.rmdir()
        raise FileNotFoundError("worker cleaned up")

    monkeypatch.setitem(WorkflowManager._start_workflow_local.__globals__, "register_process_marker", already_cleaned)
    manager._start_workflow_local()
    assert not manager.executor.pid_dir.exists()


def test_cancellation_tolerates_tracking_directory_disappearing_before_listing(manager, monkeypatch):
    folder = manager.executor.pid_dir
    folder.mkdir()
    listing = Path.iterdir

    def removed(path):
        if path == folder:
            folder.rmdir()
        return listing(path)

    monkeypatch.setattr(Path, "iterdir", removed)
    kill = Mock()
    monkeypatch.setattr(os, "kill", kill)
    assert manager._stop_local_workflow() is False
    kill.assert_not_called()


def test_cancellation_ignores_unowned_files_and_process_group_zero(manager, monkeypatch):
    folder = manager.executor.pid_dir
    folder.mkdir()
    files = [folder / name for name in ["0", "notes.json", "５４３２１"]]
    for path in files:
        path.write_text("keep")
    directory = folder / "54322"
    directory.mkdir()
    symbolic = folder / "54323"
    symbolic.symlink_to(files[1])
    valid = folder / "54321"
    process, lookup = owned_process(valid, monkeypatch)

    def kill(_sig):
        process.is_running.return_value = False

    process.send_signal.side_effect = kill
    assert manager._stop_local_workflow() is True
    process.send_signal.assert_called_once_with(signal.SIGTERM)
    assert all(call.args == (54321,) for call in lookup.call_args_list)
    assert all(path.read_text() == "keep" for path in files)
    assert directory.is_dir() and symbolic.is_symlink()
    assert not valid.exists()


def test_permission_denied_on_stop_keeps_process_tracking_and_does_not_cancel_run(manager, monkeypatch):
    folder = manager.executor.pid_dir
    folder.mkdir()
    marker = folder / "54321"
    process, _lookup = owned_process(marker, monkeypatch)
    manager.multi_run = True
    manager._mark_running_runs_cancelled = Mock()
    process.send_signal.side_effect = PermissionError("denied")
    assert manager.stop_workflow() is False
    assert marker.is_file()
    manager._mark_running_runs_cancelled.assert_not_called()
    assert any("tracking marker was retained" in call.args[0] for call in manager.logger.log.call_args_list)


def test_cancellation_does_not_remove_child_registered_after_snapshot(manager, monkeypatch):
    folder = manager.executor.pid_dir
    folder.mkdir()
    process, _lookup = owned_process(folder / "54321", monkeypatch)
    late_child = folder / "54322"

    def signal_parent(*_args):
        late_child.touch()
        process.is_running.return_value = False

    process.send_signal.side_effect = signal_parent
    assert manager._stop_local_workflow() is True
    assert late_child.is_file()


def test_delayed_process_exit_keeps_start_blocked_until_shutdown_finishes(manager, monkeypatch):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    folder = manager.executor.pid_dir
    folder.mkdir()
    marker = folder / str(child.pid)
    register_process_marker(marker, child.pid)
    manager._start_workflow_local = Mock()
    try:
        # Deliberately delay delivery: the OS can accept a termination request
        # before the child has exited. Its real liveness must stay authoritative.
        with monkeypatch.context() as delayed:
            kill = Mock()
            delayed.setattr(os, "kill", kill)
            assert manager.stop_workflow() is True
            kill.assert_called_once_with(child.pid, signal.SIGTERM)
            assert child.poll() is None and marker.is_file()
            assert manager.get_workflow_status()["running"] is True
            with pytest.raises(ValueError, match="already running"):
                manager.start_workflow()
            manager._start_workflow_local.assert_not_called()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
    assert manager.get_workflow_status()["running"] is False
    assert not marker.exists()


def test_same_named_workspaces_submitted_together_have_distinct_queue_job_ids(manager, tmp_path):
    submitted = []

    def submit(**kwargs):
        submitted.append(kwargs)
        return kwargs["job_id"]

    queue = Mock()
    queue.submit_job.side_effect = submit
    manager._queue_manager = queue
    manager._start_workflow_queued()
    manager.workflow_dir = tmp_path / "other-workspace/test-workflow"
    manager._start_workflow_queued()
    assert len(submitted) == 2
    assert submitted[0]["job_id"] != submitted[1]["job_id"]
    assert submitted[0]["kwargs"]["workflow_dir"] != submitted[1]["kwargs"]["workflow_dir"]


def test_distinct_workspaces_do_not_share_start_operation_lock(manager, tmp_path):
    other = object.__new__(WorkflowManager)
    other.__dict__ = manager.__dict__.copy()
    other.workflow_dir = tmp_path / "other-workspace/test-workflow"
    other.executor = SimpleNamespace(pid_dir=other.workflow_dir / "pids")
    other._start_workflow_local = Mock()
    with file_lock(manager.workflow_dir / ".locks/execution.lock", blocking=False):
        other.start_workflow()
    other._start_workflow_local.assert_called_once()
