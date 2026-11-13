"""Exercise races at native process and temporary-file ownership boundaries."""

import importlib
import json
import os
import shutil
import signal
import subprocess
import sys
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from src.workflow.process_state import (
    local_workflow_running,
    pid_markers,
    process_namespace,
    prune_exited_marker,
    register_process_marker,
)


@pytest.fixture
def executor(tmp_path):
    cls = importlib.import_module('src.workflow.CommandExecutor').CommandExecutor
    return cls(tmp_path, Mock(), SimpleNamespace(get_parameters_from_json=dict))


def owned_process(marker, monkeypatch):
    """Represent an owned process, including the birth recorded at spawn."""
    pid = int(marker.name)
    marker.write_text(json.dumps({'schema': 1, 'pid': pid, 'create_time': 100.0, 'namespace': process_namespace()}))
    process = Mock()
    process.pid = pid
    process.create_time.return_value = 100.0
    process.is_running.return_value = True
    process.status.return_value = psutil.STATUS_SLEEPING
    lookup = Mock(return_value=process)
    monkeypatch.setattr(psutil, 'Process', lookup)
    return process, lookup


@pytest.mark.parametrize('failure', ['registration', 'stream'])
def test_failure_after_spawn_reaps_real_child_and_retains_original_error(executor, monkeypatch, failure):
    module = importlib.import_module('src.workflow.CommandExecutor')
    native_popen = subprocess.Popen
    children = []

    def record_child(*args, **kwargs):
        process = native_popen(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(module.subprocess, 'Popen', record_child)
    if failure == 'registration':
        def cannot_register(_marker, _pid):
            shutil.rmtree(executor.pid_dir)
            raise FileNotFoundError('tracking directory removed during cancellation')

        monkeypatch.setattr(module, 'register_process_marker', cannot_register)
    else:
        monkeypatch.setattr(executor, '_stream_output', Mock(side_effect=RuntimeError('monitor failure')))
    step = executor.progress.start_step('NativeChild', ['sample.mzML'])
    error = FileNotFoundError if failure == 'registration' else RuntimeError
    try:
        with pytest.raises(error, match='tracking directory|monitor failure'):
            executor.run_command([sys.executable, '-c', 'import time; time.sleep(60)'], task=(step, 0))
        assert len(children) == 1
        assert children[0].poll() is not None
        assert children[0].stdout.closed and children[0].stderr.closed
        assert not list(executor.pid_dir.glob('*'))
        state = importlib.import_module('src.workflow.progress').read_progress(executor.pid_dir.parent)
        recorded = state['steps'][step]['files'][0]
        assert recorded['status'] == 'failed' and recorded['returncode'] == -1
        assert ('tracking directory' if failure == 'registration' else 'monitor failure') in recorded['output'][0]
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_tracking_directory_failure_happens_before_spawning(executor, monkeypatch):
    executor.pid_dir.write_text('not a directory')
    popen = Mock()
    monkeypatch.setattr('src.workflow.CommandExecutor.subprocess.Popen', popen)
    with pytest.raises(FileExistsError):
        executor.run_command([sys.executable, '-c', 'pass'])
    popen.assert_not_called()


def test_finished_fast_child_keeps_all_buffered_stdout_and_stderr(executor):
    # Reaping before reading makes this deterministic: poll() is already done,
    # but every remaining buffered line still belongs to this command's log.
    script = "import sys; [print(f'out-{i}') for i in range(20)]; [print(f'err-{i}',file=sys.stderr) for i in range(20)]"
    process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.wait(timeout=10)
        stderr, stdout = [], deque(maxlen=100)
        executor._stream_output(process, stderr, stdout)
        assert list(stdout) == [f'out-{i}' for i in range(20)]
        assert stderr == [f'err-{i}' for i in range(20)]
        assert process.stdout.closed and process.stderr.closed
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_stop_ignores_unowned_entries_and_tolerates_disappeared_markers(executor, monkeypatch):
    folder = executor.pid_dir
    folder.mkdir()
    notes = folder / 'notes.json'
    notes.write_text('preserve')
    (folder / '0').touch()
    directory = folder / '54322'
    directory.mkdir()
    target = folder.parent / 'evidence.txt'
    target.write_text('preserve target')
    link = folder / '54323'
    link.touch()
    native_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == link or native_is_symlink(path))
    marker = folder / '54321'
    process, lookup = owned_process(marker, monkeypatch)
    calls = []

    def kill():
        calls.append((process.pid, 9))
        marker.unlink()
        raise psutil.NoSuchProcess(process.pid)

    process.kill.side_effect = kill
    executor.stop()
    assert calls == [(54321, 9)]
    assert all(call.args == (54321,) for call in lookup.call_args_list)
    assert notes.read_text() == 'preserve'
    assert (folder / '0').is_file()
    assert directory.is_dir() and link.is_symlink()
    assert target.read_text() == 'preserve target'


def test_unresponsive_untracked_child_is_killed_and_reaped(executor):
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired('native tool', 5), 0]
    executor._terminate_failed_command(process)
    process.terminate.assert_called_once_with()
    process.kill.assert_called_once_with()
    assert process.wait.call_count == 2
    process.stdout.close.assert_called_once_with()
    process.stderr.close.assert_called_once_with()


def test_stop_retains_live_marker_if_signalling_is_denied(executor, monkeypatch):
    executor.pid_dir.mkdir()
    marker = executor.pid_dir / '54321'
    process, _lookup = owned_process(marker, monkeypatch)
    process.kill.side_effect = PermissionError('cannot signal')
    executor.stop()
    process.kill.assert_called_once_with()
    process.send_signal.assert_not_called()
    assert marker.is_file()
    messages = [call.args[0] for call in executor.logger.log.call_args_list]
    assert 'Some processes are still stopping or could not be stopped.' in messages
    assert 'Workflow stopped.' not in messages


def test_stop_is_idempotent_when_tracking_directory_disappears(executor, monkeypatch):
    kill = Mock()
    monkeypatch.setattr('src.workflow.CommandExecutor.os.kill', kill)
    executor.stop()
    executor.stop()
    kill.assert_not_called()


def test_pid_snapshot_tolerates_directory_removed_after_caller_check(executor, monkeypatch):
    executor.pid_dir.mkdir()
    native_iterdir = Path.iterdir

    def disappear(path):
        if path == executor.pid_dir:
            path.rmdir()
        return native_iterdir(path)

    monkeypatch.setattr(Path, 'iterdir', disappear)
    assert pid_markers(executor.pid_dir) == []
    assert local_workflow_running(executor.pid_dir) is False


@pytest.mark.parametrize('outcome', ['success', 'failure', 'exception', 'already_removed'])
def test_python_parameter_cleanup_preserves_original_outcome(executor, monkeypatch, outcome):
    script = executor.pid_dir.parent / 'worker.py'
    script.write_text("DEFAULTS=[{'key':'value','value':0}]\n")
    used = []

    def command(args, **_kwargs):
        path = Path(args[2])
        used.append(path)
        assert json.loads(path.read_text())['value'] == 42
        if outcome == 'exception':
            raise RuntimeError('original command failure')
        if outcome == 'already_removed':
            path.unlink()
        return outcome != 'failure'

    monkeypatch.setattr(executor, 'run_command', command)
    if outcome == 'exception':
        with pytest.raises(RuntimeError, match='original command failure'):
            executor.run_python(str(script), {'value':42})
    else:
        assert executor.run_python(str(script), {'value':42}) is (outcome != 'failure')
    assert len(used) == 1 and not used[0].exists()


def test_concurrent_same_python_tool_has_private_parameter_files(executor, monkeypatch):
    script = executor.pid_dir.parent / 'worker.py'
    script.write_text("DEFAULTS=[{'key':'value','value':0}]\n")
    barrier = Barrier(2)
    paths = []
    observed = []

    def command(args, **_kwargs):
        path = Path(args[2])
        paths.append(path)
        barrier.wait(timeout=10)
        observed.append(json.loads(path.read_text())['value'])
        barrier.wait(timeout=10)
        return True

    monkeypatch.setattr(executor, 'run_command', command)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: executor.run_python(str(script), {'value':value}), [1,2]))
    assert results == [True, True]
    assert len(set(paths)) == 2 and sorted(observed) == [1,2]
    assert all(not path.exists() for path in paths)


def test_invalid_python_parameter_serialization_does_not_leave_temporary_file(executor):
    script = executor.pid_dir.parent / 'worker.py'
    script.write_text("DEFAULTS=[{'key':'value','value':0}]\n")
    with pytest.raises(TypeError, match='JSON serializable'):
        executor.run_python(str(script), {'value':object()})
    assert not list(script.parent.glob('worker-*.json'))


def test_concurrent_conversions_do_not_share_or_remove_partial_output(executor, monkeypatch):
    raw = executor.pid_dir.parent / 'sample.raw'
    raw.write_text('raw input')
    barrier = Barrier(2)
    partials = []

    def convert(_tool, io):
        partial = Path(io['out'][0])
        partials.append(partial)
        content = f'complete conversion {partial.parent.name}'
        partial.write_text(content)
        barrier.wait(timeout=10)
        assert partial.read_text() == content
        barrier.wait(timeout=10)
        return True

    monkeypatch.setattr(executor, 'run_topp', convert)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: executor.convert_to_mzml([str(raw)]), range(2)))
    destination = raw.parent / 'converted-mzML/sample.mzML'
    assert results == [[str(destination)], [str(destination)]]
    assert len(set(partials)) == 2
    assert destination.read_text().startswith('complete conversion ')
    assert list(destination.parent.iterdir()) == [destination]


def test_conversion_exception_removes_only_its_private_partial_output(executor, monkeypatch):
    raw = executor.pid_dir.parent / 'sample.raw'
    raw.write_text('raw input')
    output = raw.parent / 'converted-mzML'
    output.mkdir()
    evidence = output / 'another-complete.mzML'
    evidence.write_text('previous result')

    def fail(_tool, io):
        Path(io['out'][0]).write_text('partial conversion')
        raise RuntimeError('native conversion failure')

    monkeypatch.setattr(executor, 'run_topp', fail)
    with pytest.raises(RuntimeError, match='native conversion failure'):
        executor.convert_to_mzml([str(raw)])
    assert list(output.iterdir()) == [evidence]
    assert evidence.read_text() == 'previous result'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX SIGTERM handler semantics; platform-independent helper states are covered separately')
def test_signal_delivery_does_not_prune_a_real_child_that_has_not_exited(executor):
    script = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); time.sleep(60)"
    process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, text=True)
    executor.pid_dir.mkdir()
    marker = executor.pid_dir / str(process.pid)
    register_process_marker(marker, process.pid)
    try:
        assert process.stdout.readline().strip() == 'ready'
        process.send_signal(signal.SIGTERM)
        assert prune_exited_marker(marker) is True
        assert marker.is_file() and process.poll() is None
        process.kill()
        process.wait(timeout=5)
        assert prune_exited_marker(marker) is False
        assert not marker.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()


def test_successful_stop_signal_retains_marker_until_process_exits(executor, monkeypatch):
    executor.pid_dir.mkdir()
    marker = executor.pid_dir / '54321'
    process, _lookup = owned_process(marker, monkeypatch)
    executor.stop()
    process.kill.assert_called_once_with()
    process.send_signal.assert_not_called()
    assert marker.is_file()
    assert local_workflow_running(executor.pid_dir)
    process.is_running.return_value = False
    assert not local_workflow_running(executor.pid_dir)
    assert not marker.exists()
