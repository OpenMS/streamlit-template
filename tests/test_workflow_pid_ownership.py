"""PID reuse and incomplete legacy records never authorize signalling strangers."""

import importlib
import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from src.workflow.process_state import (
    local_workflow_running,
    owned_workflow_running,
    process_namespace,
    prune_exited_marker,
    register_process_marker,
    signal_owned_process,
)

process_state = importlib.import_module("src.workflow.process_state")


def _identity_record(pid=54321, created=100.0, **changes):
    return {"schema": 1, "pid": pid, "create_time": created, "namespace": process_namespace()} | changes


@pytest.fixture
def harmless_child():
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", "import time; print('ready', flush=True); time.sleep(30)"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "ready"
        yield child
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


@pytest.fixture
def owned_marker(tmp_path, monkeypatch):
    folder = tmp_path / "pids"
    folder.mkdir()
    marker = folder / "54321"
    marker.write_text(json.dumps(_identity_record()))
    process = Mock()
    process.is_running.return_value = True
    process.status.return_value = psutil.STATUS_SLEEPING
    process.create_time.return_value = 100.0
    monkeypatch.setattr(psutil, "Process", Mock(return_value=process))
    return folder, marker, process


def test_registered_real_child_has_exact_birth_identity(tmp_path, harmless_child):
    marker = tmp_path / str(harmless_child.pid)
    register_process_marker(marker, harmless_child.pid)
    assert json.loads(marker.read_text()) == {
        "schema": 1,
        "pid": harmless_child.pid,
        "create_time": psutil.Process(harmless_child.pid).create_time(),
        "namespace": process_namespace(),
    }
    assert prune_exited_marker(marker) is True
    assert local_workflow_running(tmp_path) is True
    assert list(tmp_path.iterdir()) == [marker]


def test_owned_real_child_can_be_stopped_and_reaped(tmp_path, harmless_child):
    marker = tmp_path / str(harmless_child.pid)
    register_process_marker(marker, harmless_child.pid)
    assert signal_owned_process(marker, signal.SIGTERM) is True
    harmless_child.wait(timeout=5)
    assert prune_exited_marker(marker) is False
    assert not marker.exists()


@pytest.mark.parametrize("operation", ["status", "stop"])
def test_reused_pid_marker_does_not_signal_unrelated_live_child(
    tmp_path, harmless_child, monkeypatch, operation
):
    marker = tmp_path / str(harmless_child.pid)
    marker.write_text(json.dumps(_identity_record(
        harmless_child.pid, psutil.Process(harmless_child.pid).create_time() - 100,
    )))
    signal_guard = Mock(side_effect=AssertionError("Unrelated process must never receive a signal"))
    with monkeypatch.context() as guarded:
        guarded.setattr(psutil.Process, "send_signal", signal_guard)
        if operation == "status":
            assert local_workflow_running(tmp_path) is False
        else:
            assert signal_owned_process(marker, signal.SIGTERM) is False
        signal_guard.assert_not_called()
        assert harmless_child.poll() is None
    assert not marker.exists()


@pytest.mark.parametrize("payload", [
    b"", b"not JSON", b"[]", b"\xff",
    {"schema": True}, {"pid": 54322}, {"create_time": float("nan")}, {"create_time": None},
    b'{"schema": 1, "pid": 54321, "create_time": 100.0}',
])
def test_empty_legacy_or_invalid_live_marker_never_proves_ownership(owned_marker, payload):
    folder, marker, process = owned_marker
    if isinstance(payload, dict):
        payload = json.dumps(_identity_record(**payload)).encode()
    marker.write_bytes(payload)
    assert local_workflow_running(folder) is True
    with pytest.raises(PermissionError, match="ownership"):
        signal_owned_process(marker, signal.SIGTERM)
    assert marker.read_bytes() == payload
    process.send_signal.assert_not_called()


def test_empty_legacy_marker_for_dead_process_is_still_cleaned_up(tmp_path, monkeypatch):
    marker = tmp_path / "54321"
    marker.touch()
    monkeypatch.setattr(psutil, "Process", Mock(side_effect=psutil.NoSuchProcess(54321)))
    assert local_workflow_running(tmp_path) is False
    assert not marker.exists()


def test_pid_reused_after_comparison_uses_psutil_identity_guard_not_raw_signal(owned_marker, monkeypatch):
    _folder, marker, process = owned_marker
    process.send_signal.side_effect = psutil.NoSuchProcess(54321, "PID has been reused")
    raw_signal = Mock(side_effect=AssertionError("Do not retry by PID number"))
    monkeypatch.setattr(os, "kill", raw_signal)
    assert signal_owned_process(marker, signal.SIGTERM) is False
    process.create_time.assert_called_once_with()
    process.send_signal.assert_called_once_with(signal.SIGTERM)
    raw_signal.assert_not_called()
    assert not marker.exists()


@pytest.mark.parametrize("reused", [False, True])
def test_force_stop_uses_identity_checked_kill_api(owned_marker, reused):
    _folder, marker, process = owned_marker
    if reused:
        process.kill.side_effect = psutil.NoSuchProcess(54321, "PID has been reused")
    assert signal_owned_process(marker, 9) is (not reused)
    process.kill.assert_called_once_with()
    process.send_signal.assert_not_called()
    assert marker.exists() is (not reused)


@pytest.mark.parametrize("phase", ["liveness", "birth", "signal"])
def test_access_denied_retains_busy_tracking_and_refuses_signal(owned_marker, phase):
    folder, marker, process = owned_marker
    if phase == "liveness":
        process.status.side_effect = psutil.AccessDenied(54321)
    elif phase == "birth":
        process.create_time.side_effect = psutil.AccessDenied(54321)
    else:
        process.send_signal.side_effect = psutil.AccessDenied(54321)
    assert local_workflow_running(folder) is True
    with pytest.raises(PermissionError):
        signal_owned_process(marker, signal.SIGTERM)
    assert marker.is_file()
    if phase != "signal":
        process.send_signal.assert_not_called()


def test_marker_disappearing_during_validation_cannot_authorize_signal(owned_marker, monkeypatch):
    _folder, marker, process = owned_marker
    original = SimpleNamespace(read_text=Path.read_text)

    def disappeared(path, *args, **kwargs):
        if path == marker:
            marker.unlink()
        return original.read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", disappeared)
    assert signal_owned_process(marker, signal.SIGTERM) is False
    process.send_signal.assert_not_called()


@pytest.mark.parametrize("fail_publish", [False, True])
def test_registration_publishes_complete_identity_or_retains_previous_record(
    owned_marker, monkeypatch, fail_publish
):
    folder, marker, process = owned_marker
    previous = marker.read_bytes()
    process.create_time.return_value = 200.0
    replace = os.replace
    publications = []

    def publish(source, destination):
        assert Path(destination) == marker
        assert marker.read_bytes() == previous
        record = json.loads(Path(source).read_text())
        assert record == _identity_record(created=200.0)
        assert Path(source).parent == folder and Path(source) != marker
        publications.append(record)
        if fail_publish:
            raise PermissionError("marker directory is read-only")
        return replace(source, destination)

    monkeypatch.setattr(process_state.os, "replace", publish)
    if fail_publish:
        with pytest.raises(PermissionError, match="read-only"):
            register_process_marker(marker, 54321)
        assert marker.read_bytes() == previous
    else:
        register_process_marker(marker, 54321)
        assert json.loads(marker.read_text())["create_time"] == 200.0
    assert len(publications) == 1
    assert list(folder.iterdir()) == [marker]


@pytest.mark.parametrize("denied", [False, True])
def test_exited_or_uninspectable_process_does_not_publish_partial_identity(tmp_path, monkeypatch, denied):
    marker = tmp_path / "54321"
    error = psutil.AccessDenied(54321) if denied else psutil.NoSuchProcess(54321)
    monkeypatch.setattr(psutil, "Process", Mock(side_effect=error))
    if denied:
        with pytest.raises(PermissionError, match="creation time"):
            register_process_marker(marker, 54321)
    else:
        register_process_marker(marker, 54321)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("identity", ["owned", "legacy", "reused", "dead"])
def test_queue_probe_retains_records_that_may_belong_to_a_remote_namespace(owned_marker, identity):
    folder, marker, process = owned_marker
    if identity == "legacy":
        marker.write_text("")
    elif identity == "reused":
        process.create_time.return_value = 200.0
    elif identity == "dead":
        process.is_running.return_value = False
    before = marker.read_bytes()
    assert owned_workflow_running(folder) is (identity == "owned")
    assert marker.read_bytes() == before
    process.send_signal.assert_not_called()
    process.kill.assert_not_called()


def test_queue_probe_for_missing_directory_is_nondestructive(tmp_path):
    missing = tmp_path / "remote-pids"
    assert owned_workflow_running(missing) is False
    assert not missing.exists()


@pytest.mark.parametrize("unavailable", ["liveness", "birth", "record", "directory"])
def test_queue_ack_remains_authoritative_when_local_ownership_is_unknown(
    owned_marker, monkeypatch, unavailable
):
    folder, marker, process = owned_marker
    before = marker.read_bytes()
    if unavailable == "liveness":
        process.status.side_effect = psutil.AccessDenied(54321)
    elif unavailable == "birth":
        process.create_time.side_effect = psutil.AccessDenied(54321)
    elif unavailable == "record":
        original = SimpleNamespace(read_text=Path.read_text)

        def denied(path, *args, **kwargs):
            if path == marker:
                raise PermissionError("remote tracking record unavailable")
            return original.read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)
    else:
        listing = Path.iterdir

        def denied(path):
            if path == folder:
                raise PermissionError("remote tracking directory unavailable")
            return listing(path)

        monkeypatch.setattr(Path, "iterdir", denied)
    assert owned_workflow_running(folder) is False
    assert local_workflow_running(folder) is True
    assert marker.read_bytes() == before
    process.send_signal.assert_not_called()


@pytest.mark.parametrize("identity", ["reused", "dead", "reused_after_validation"])
def test_queue_cleanup_does_not_prune_foreign_or_reused_pid_records(owned_marker, identity):
    _folder, marker, process = owned_marker
    if identity == "reused":
        process.create_time.return_value = 200.0
    elif identity == "dead":
        process.is_running.return_value = False
    else:
        process.send_signal.side_effect = psutil.NoSuchProcess(54321, "PID has been reused")
    before = marker.read_bytes()
    assert signal_owned_process(marker, signal.SIGTERM, prune_stale=False) is False
    assert marker.read_bytes() == before
    if identity == "reused_after_validation":
        process.send_signal.assert_called_once_with(signal.SIGTERM)
    else:
        process.send_signal.assert_not_called()


def test_queue_cleanup_never_signals_legacy_identity(owned_marker):
    _folder, marker, process = owned_marker
    marker.write_text("")
    with pytest.raises(PermissionError, match="ownership"):
        signal_owned_process(marker, signal.SIGTERM, prune_stale=False)
    assert marker.read_bytes() == b""
    process.send_signal.assert_not_called()


def test_queue_cleanup_can_stop_a_proven_local_child_without_erasing_its_record(tmp_path, harmless_child):
    marker = tmp_path / str(harmless_child.pid)
    register_process_marker(marker, harmless_child.pid)
    before = marker.read_bytes()
    assert signal_owned_process(marker, signal.SIGTERM, prune_stale=False) is True
    harmless_child.wait(timeout=5)
    assert owned_workflow_running(tmp_path) is False
    assert marker.read_bytes() == before


@pytest.mark.parametrize("phase", ["birth", "signal"])
def test_queue_cleanup_access_denied_retains_remote_record(owned_marker, phase):
    _folder, marker, process = owned_marker
    before = marker.read_bytes()
    if phase == "birth":
        process.create_time.side_effect = psutil.AccessDenied(54321)
    else:
        process.send_signal.side_effect = psutil.AccessDenied(54321)
    with pytest.raises(PermissionError):
        signal_owned_process(marker, signal.SIGTERM, prune_stale=False)
    assert marker.read_bytes() == before


@pytest.mark.parametrize("pid_absent_locally", [False, True])
def test_foreign_namespace_cannot_signal_an_identical_local_pid_and_birth(
    tmp_path, harmless_child, monkeypatch, pid_absent_locally
):
    marker = tmp_path / str(harmless_child.pid)
    marker.write_text(json.dumps(_identity_record(
        harmless_child.pid,
        psutil.Process(harmless_child.pid).create_time(),
        namespace="another-host-or-pid-namespace",
    )))
    before = marker.read_bytes()
    signal_guard = Mock(side_effect=AssertionError("A foreign marker cannot authorize any local signal"))
    with monkeypatch.context() as guarded:
        if pid_absent_locally:
            guarded.setattr(psutil, "Process", Mock(side_effect=psutil.NoSuchProcess(harmless_child.pid)))
        else:
            guarded.setattr(psutil.Process, "send_signal", signal_guard)
            guarded.setattr(psutil.Process, "kill", signal_guard)
        assert owned_workflow_running(tmp_path) is False
        with pytest.raises(PermissionError):
            signal_owned_process(marker, signal.SIGTERM, prune_stale=False)
        assert marker.read_bytes() == before
        # Offline recovery treats an old container's namespace as stale. Queue
        # callers above retain it for acknowledgement by its actual worker.
        assert local_workflow_running(tmp_path) is False
        assert not marker.exists()
        marker.write_bytes(before)
        assert prune_exited_marker(marker) is False
        assert not marker.exists()
        marker.write_bytes(before)
        assert signal_owned_process(marker, signal.SIGTERM) is False
        assert not marker.exists()
        signal_guard.assert_not_called()
        assert harmless_child.poll() is None


@pytest.mark.parametrize("linux_namespace,changed_component", [
    (True, "host"), (True, "pid_namespace"), (True, "boot"),
    (False, "host"), (False, "boot"),
])
def test_process_namespace_is_stable_per_process_and_distinguishes_instances(
    monkeypatch, linux_namespace, changed_component
):
    original = SimpleNamespace(read_text=Path.read_text)
    hostname = Mock(return_value="host-a")
    namespace_link = Mock(return_value="pid:[namespace-a]")
    boot_time = Mock(return_value=100.0)
    boot_id = ["boot-a"]

    def boot_file(path, *args, **kwargs):
        if str(path) == "/proc/sys/kernel/random/boot_id":
            if not linux_namespace:
                raise FileNotFoundError("No proc boot identifier on this platform")
            return boot_id[0]
        return original.read_text(path, *args, **kwargs)

    if not linux_namespace:
        namespace_link.side_effect = OSError("PID namespaces unavailable")
    monkeypatch.setattr(socket, "gethostname", hostname)
    monkeypatch.setattr(os, "readlink", namespace_link)
    monkeypatch.setattr(psutil, "boot_time", boot_time)
    monkeypatch.setattr(Path, "read_text", boot_file)
    process_namespace.cache_clear()
    try:
        first = process_namespace()
        assert isinstance(first, str) and first
        process_namespace.cache_clear()
        assert process_namespace() == first
        if changed_component == "host":
            hostname.return_value = "host-b"
        elif changed_component == "pid_namespace":
            namespace_link.return_value = "pid:[namespace-b]"
        else:
            boot_time.return_value = 200.0
            boot_id[0] = "boot-b"
        assert process_namespace() == first  # One stable identity per interpreter.
        process_namespace.cache_clear()
        assert process_namespace() != first
    finally:
        process_namespace.cache_clear()


@pytest.mark.parametrize("stored,current,accepted", [
    ("host-a|100.0|host", "host-a|101.9|host", True),
    ("host-a|100.0|host", "host-a|102.0|host", True),
    ("host-a|100.0|host", "host-a|102.01|host", False),
    ("host-a|100.0|host", "host-b|100.0|host", False),
    ("host-a|boot-a|pid:[42]", "host-a|boot-a|pid:[42]", True),
    ("host-a|boot-a|pid:[42]", "host-a|boot-b|pid:[42]", False),
    ("host-a|boot-a|pid:[42]", "host-a|boot-a|pid:[43]", False),
    ("host-a|100.0|pid:[42]", "host-a|101.0|pid:[42]", False),
])
def test_boot_time_fallback_tolerates_clock_jitter_without_relaxing_process_birth(
    owned_marker, monkeypatch, stored, current, accepted
):
    folder, marker, process = owned_marker
    record = json.loads(marker.read_text()) | {"namespace": stored}
    marker.write_text(json.dumps(record))
    monkeypatch.setattr(process_state, "process_namespace", lambda: current)
    assert owned_workflow_running(folder) is accepted
    assert signal_owned_process(marker, signal.SIGTERM) is accepted
    if accepted:
        process.send_signal.assert_called_once_with(signal.SIGTERM)
        assert marker.exists()
        # Boot-time tolerance is never a tolerance on the process birth time.
        process.create_time.return_value = 100.001
        assert signal_owned_process(marker, signal.SIGTERM) is False
        assert not marker.exists()
        assert process.send_signal.call_count == 1
    else:
        process.send_signal.assert_not_called()
        assert not marker.exists()
