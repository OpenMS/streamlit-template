"""Restart-orphaned PID files must not block valid UI recovery."""

import importlib
import json
import signal
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest
from streamlit.testing.v1 import AppTest

from src.workflow.process_state import local_workflow_running, process_namespace


@pytest.fixture
def markers(tmp_path):
    folder = tmp_path / "pids"
    folder.mkdir()
    marker = folder / "54321"
    marker.touch()
    return folder, marker


@pytest.mark.parametrize("state,running", [
    (psutil.STATUS_SLEEPING, True),
    (psutil.STATUS_STOPPED, True),
    (psutil.STATUS_ZOMBIE, False),
    (psutil.STATUS_DEAD, False),
    ("gone", False),
    ("not-running", False),
    ("denied", True),
    ("invalid", False),
    ("overflow", False),
])
def test_pid_markers_follow_process_liveness_not_file_existence(markers, monkeypatch, state, running):
    folder, marker = markers
    process = Mock()
    process.create_time.return_value = 0.0  # older than the marker: not a reused pid
    process.is_running.return_value = state != "not-running"
    process.status.return_value = state
    lookup = Mock(return_value=process)
    if state == "gone":
        lookup.side_effect = psutil.NoSuchProcess(54321)
    elif state == "denied":
        process.status.side_effect = psutil.AccessDenied(54321)
    elif state == "invalid":
        lookup.side_effect = ValueError("invalid PID")
    elif state == "overflow":
        lookup.side_effect = OverflowError("PID outside platform range")
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", lookup)
    assert local_workflow_running(folder) is running
    assert marker.exists() is running
    lookup.assert_called_once_with(54321)


def test_live_worker_does_not_prevent_pruning_other_dead_markers(markers, monkeypatch):
    folder, marker = markers
    dead = folder / "54322"
    dead.touch()
    process = Mock()
    process.create_time.return_value = 0.0  # older than the marker: not a reused pid
    process.is_running.return_value = True
    process.status.return_value = psutil.STATUS_SLEEPING

    def lookup(pid):
        if pid == 54321:
            return process
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr("src.workflow.process_state.psutil.Process", lookup)
    assert local_workflow_running(folder)
    assert marker.exists()
    assert not dead.exists()


def test_unrelated_files_numeric_directories_and_symlinks_are_not_pid_markers(tmp_path, monkeypatch):
    folder = tmp_path / "pids"
    folder.mkdir()
    note = folder / "conversion.json"
    note.write_text('{"state":"prepared"}')
    numeric_directory = folder / "54321"
    numeric_directory.mkdir()
    symbolic = folder / "54322"
    symbolic.touch()
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == symbolic or original(path))
    lookup = Mock()
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", lookup)
    assert local_workflow_running(folder) is False
    assert note.read_text() == '{"state":"prepared"}'
    assert numeric_directory.is_dir()
    assert symbolic.exists()
    lookup.assert_not_called()


def test_missing_pid_directory_is_idle(tmp_path):
    assert local_workflow_running(tmp_path / "missing") is False


def test_unreadable_pid_directory_is_conservatively_busy(tmp_path, monkeypatch):
    folder = tmp_path / "pids"
    native = Path.iterdir

    def read(path):
        if path == folder:
            raise PermissionError("temporarily unavailable")
        return native(path)

    monkeypatch.setattr(Path, "iterdir", read)
    assert local_workflow_running(folder) is True


def test_dead_marker_cleanup_failure_does_not_invent_a_live_worker(markers, monkeypatch):
    folder, marker = markers
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", Mock(side_effect=psutil.NoSuchProcess(54321)))
    native = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == marker:
            raise PermissionError("read-only marker")
        return native(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    assert local_workflow_running(folder) is False
    assert marker.exists()


@pytest.fixture
def manager(markers):
    cls = importlib.import_module("src.workflow.WorkflowManager").WorkflowManager
    instance = object.__new__(cls)
    instance.workflow_dir = markers[0].parent
    instance.executor = SimpleNamespace(pid_dir=markers[0])
    instance._queue_manager = None
    instance.logger = Mock()
    return instance


def test_manager_status_cleans_only_dead_pids_preserving_run_metadata_and_logs(manager, markers, monkeypatch):
    folder, marker = markers
    log = folder.parent / "run.log"
    record = folder.parent / "run.json"
    log.write_text("native partial output\n")
    record.write_text('{"status":"running"}')
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", Mock(side_effect=psutil.NoSuchProcess(54321)))
    assert manager.get_workflow_status()["running"] is False
    assert not marker.exists()
    assert log.read_text() == "native partial output\n"
    assert record.read_text() == '{"status":"running"}'


def test_manager_status_keeps_live_workers_running(manager, monkeypatch):
    process = Mock()
    process.create_time.return_value = 0.0  # older than the marker: not a reused pid
    process.is_running.return_value = True
    process.status.return_value = psutil.STATUS_SLEEPING
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", Mock(return_value=process))
    assert manager.get_workflow_status()["running"] is True


@pytest.mark.parametrize("state,expected", [("started", True), ("queued", True), ("finished", False), ("canceled", False)])
def test_queue_status_remains_authoritative(manager, markers, monkeypatch, state, expected):
    job = SimpleNamespace(
        status=SimpleNamespace(value=state), progress=0, current_step=None,
        queue_position=None, queue_length=0, enqueued_at=None, started_at=None, result=None, error=None,
    )
    queue = Mock()
    queue.is_available = True
    queue.load_job_id.return_value = "test-job"
    queue.get_job_info.return_value = job
    manager._queue_manager = queue
    lookup = Mock(side_effect=psutil.NoSuchProcess(54321))
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", lookup)
    assert manager.get_workflow_status()["running"] is expected
    assert markers[1].exists()
    if expected:
        lookup.assert_not_called()
    else:
        lookup.assert_called_once_with(54321)


HARNESS = """
from pathlib import Path
from types import SimpleNamespace
import streamlit as st
from src.workflow.StreamlitUI import StreamlitUI

ui = object.__new__(StreamlitUI)
ui.workflow_dir = Path(st.session_state.folder)
ui.executor = SimpleNamespace(pid_dir=ui.workflow_dir / 'pids')
ui.export_parameters_markdown = lambda: 'Saved test settings'
def start():
    st.session_state.start_count = st.session_state.get('start_count', 0) + 1
provider = None if st.session_state.status is None else lambda: st.session_state.status
ui.execution_section(start, get_status_function=provider)
"""


@pytest.mark.parametrize("status", [None, {}, {"running": False, "status": "idle"}])
def test_dead_pid_files_do_not_block_start_button(markers, monkeypatch, status):
    folder, marker = markers
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", Mock(side_effect=psutil.NoSuchProcess(54321)))
    app = AppTest.from_string(HARNESS)
    app.session_state.folder = str(folder.parent)
    app.session_state.status = status
    app.run(timeout=30)
    assert not app.exception
    assert any(button.label == "Start Workflow" for button in app.button)
    assert not any(button.label == "Stop Workflow" for button in app.button)
    next(button for button in app.button if button.label == "Start Workflow").click().run(timeout=30)
    assert not app.exception
    assert app.session_state.start_count == 1
    if status is None or "running" not in status:
        assert not marker.exists()


def test_ui_does_not_override_explicit_idle_status_with_a_pid_marker(markers, monkeypatch):
    folder, marker = markers
    lookup = Mock()
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", lookup)
    app = AppTest.from_string(HARNESS)
    app.session_state.folder = str(folder.parent)
    app.session_state.status = {"running": False, "status": "finished"}
    app.run(timeout=30)
    assert not app.exception
    assert any(button.label == "Start Workflow" for button in app.button)
    assert not any(button.label == "Stop Workflow" for button in app.button)
    lookup.assert_not_called()
    assert marker.exists()


@pytest.mark.parametrize("returncode", [0, 3])
@pytest.mark.parametrize("remove_directory", [False, True])
def test_polling_finished_child_before_executor_cleanup_preserves_native_outcome(
    tmp_path, monkeypatch, returncode, remove_directory
):
    """Poll a real exited child at the exact race boundary, without sleeps."""
    cls = importlib.import_module("src.workflow.CommandExecutor").CommandExecutor
    logger_cls = importlib.import_module("src.workflow.Logger").Logger
    progress_module = importlib.import_module("src.workflow.progress")
    executor = cls(tmp_path, logger_cls(tmp_path), SimpleNamespace())
    executor.pid_dir.mkdir()
    step = executor.progress.start_step("NativeChild", ["sample.mzML"])
    stream_output = executor._stream_output
    polls = []

    def stream_then_poll(process, stderr_buffer, stdout_tail):
        stream_output(process, stderr_buffer, stdout_tail)
        assert process.wait(timeout=10) == returncode
        marker = executor.pid_dir / str(process.pid)
        assert marker.is_file()
        # This is the same liveness check performed by the Run page. The
        # child has exited but run_command has not reached its cleanup yet.
        polls.append(local_workflow_running(executor.pid_dir))
        assert not marker.exists()
        if remove_directory:
            executor.pid_dir.rmdir()

    monkeypatch.setattr(executor, "_stream_output", stream_then_poll)
    script = (
        "import sys; print('native stdout', flush=True); "
        "print('native diagnostic', file=sys.stderr, flush=True); "
        f"sys.exit({returncode})"
    )
    assert executor.run_command([sys.executable, "-c", script], task=(step, 0)) is (returncode == 0)
    assert polls == [False]
    assert not list(executor.pid_dir.glob("*"))
    state = progress_module.read_progress(tmp_path)
    entry = state["steps"][step]["files"][0]
    assert entry["status"] == ("done" if returncode == 0 else "failed")
    assert entry["ended"] >= entry["started"]
    errors = progress_module.failures(state)
    if returncode == 0:
        assert errors == []
    else:
        assert len(errors) == 1
        assert errors[0]["returncode"] == returncode
        assert errors[0]["context"] == "While running NativeChild on (sample.mzML)"
        assert set(errors[0]["output"]) == {"native stdout", "native diagnostic"}
        log = (tmp_path / "logs/minimal.log").read_text()
        assert "ERROR: Command failed with exit code 3:" in log
        assert "While running NativeChild on (sample.mzML) (exit code 3)" in log
        assert "native diagnostic" in log


@pytest.mark.parametrize("already_exited", [False, True])
def test_stop_tolerates_marker_pruned_after_listing(
    manager, markers, monkeypatch, already_exited
):
    """Cancellation can race the same UI poll in either kill outcome."""
    folder, marker = markers
    manager.logger = Mock()
    evidence = folder.parent / "result.txt"
    evidence.write_text("saved sample evidence")
    kills = []
    marker.write_text(json.dumps({"schema": 1, "pid": 54321, "create_time": 100.0, "namespace": process_namespace()}))
    process = Mock()
    process.create_time.return_value = 100.0
    process.is_running.return_value = True
    process.status.return_value = psutil.STATUS_SLEEPING

    def kill_and_prune(sig):
        kills.append((54321, sig))
        marker.unlink()
        if already_exited:
            raise psutil.NoSuchProcess(54321)

    process.send_signal.side_effect = kill_and_prune
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", Mock(return_value=process))
    assert manager._stop_local_workflow() is (not already_exited)
    assert kills == [(54321, signal.SIGTERM)]
    assert not folder.exists()
    assert evidence.read_text() == "saved sample evidence"
    if already_exited:
        manager.logger.log.assert_not_called()
    else:
        manager.logger.log.assert_called_once_with("WORKFLOW CANCELLED")


def test_a_legacy_marker_older_than_its_process_names_a_reused_pid(markers, monkeypatch):
    """An empty marker is touched right after its process started: a process
    started well after the marker got the same pid later and is not the run's."""
    folder, marker = markers
    process = Mock()
    process.is_running.return_value = True
    process.status.return_value = psutil.STATUS_SLEEPING
    process.create_time.return_value = marker.stat().st_mtime + 3600
    monkeypatch.setattr("src.workflow.process_state.psutil.Process", Mock(return_value=process))
    assert local_workflow_running(folder) is False
    assert not marker.exists()
