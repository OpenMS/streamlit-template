"""Concurrent run updates retain snapshots, terminal state and complete files."""

import importlib
import shutil
import subprocess
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.workflow.file_lock import file_lock
from src.workflow.RunManager import CANCELLED, FAILED, FINISHED, RunManager

manager_module = importlib.import_module("src.workflow.RunManager")


def test_file_lock_has_nonblocking_contention_and_releases_on_exception(tmp_path):
    path = tmp_path / ".locks/state.lock"
    with pytest.raises(RuntimeError, match="operation failed"), file_lock(path):
        with pytest.raises(BlockingIOError), file_lock(path, blocking=False):
            pytest.fail("A competing handle must not acquire the lock")
        raise RuntimeError("operation failed")
    with file_lock(path, blocking=False):
        assert path.exists()


def test_file_lock_is_released_when_its_process_exits(tmp_path):
    path = tmp_path / ".locks/state.lock"
    script = """
import sys
from src.workflow.file_lock import file_lock
with file_lock(sys.argv[1]):
    print('locked', flush=True)
    sys.stdin.readline()
"""
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", script, str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert process.stdout.readline().strip() == "locked"
        with pytest.raises(BlockingIOError), file_lock(path, blocking=False):
            pytest.fail("Another process holds the lock")
        process.terminate()
        process.wait(timeout=10)
        with file_lock(path, blocking=False):
            assert path.exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_simultaneous_processes_get_distinct_runs_names_and_snapshots(tmp_path):
    script = """
import importlib,json,sys
from datetime import datetime
from pathlib import Path
from src.workflow.RunManager import RunManager
module=importlib.import_module('src.workflow.RunManager')
class Frozen(datetime):
    @classmethod
    def now(cls): return cls(2026,11,12,10,0,0)
module.datetime=Frozen
source=Path(sys.argv[1])/('source-'+sys.argv[2]+'.json')
source.write_text(json.dumps({'sample':sys.argv[2]}))
print('ready',flush=True)
sys.stdin.readline()
runs=RunManager(Path(sys.argv[1])/'workflow')
run=runs.new_run(params_file=source)
(runs.results_dir(run)/'sample.txt').write_text(sys.argv[2])
print(run,flush=True)
"""
    processes = [subprocess.Popen(
        [sys.executable, "-u", "-c", script, str(tmp_path), str(index)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) for index in range(8)]
    try:
        for process in processes:
            assert process.stdout.readline().strip() == "ready"
        for process in processes:
            process.stdin.write("go\n")
            process.stdin.flush()
        identities = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 0, stderr
            identities.append(stdout.strip())
        assert len(set(identities)) == 8
        runs = RunManager(tmp_path / "workflow")
        assert {run["name"] for run in runs.list_runs()} == {f"Run {index}" for index in range(1, 9)}
        for index, identity in enumerate(identities):
            assert runs.params(identity) == {"sample": str(index)}
            assert (runs.results_dir(identity) / "sample.txt").read_text() == str(index)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


def test_snapshot_disappearing_does_not_publish_a_phantom_run(tmp_path, monkeypatch):
    runs = RunManager(tmp_path)
    source = tmp_path / "params.json"
    source.write_text('{"sample":"original"}')
    copy = shutil.copy2

    def disappear(src, dst, *args, **kwargs):
        if Path(src) == source:
            source.unlink()
        return copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(manager_module.shutil, "copy2", disappear)
    with pytest.raises(FileNotFoundError):
        runs.new_run("Keep my name", source)
    assert runs.list_runs() == []
    assert not [path for path in runs.runs_dir.iterdir() if not path.name.startswith(".")]


def test_metadata_writers_use_private_temporary_files(tmp_path, monkeypatch):
    runs = RunManager(tmp_path)
    identity = runs.new_run()
    barrier = threading.Barrier(2)
    replace = Path.replace
    temporary = []

    def concurrent_replace(path, target):
        if target == runs.run_dir(identity) / "run.json":
            temporary.append(path)
            barrier.wait(timeout=10)
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", concurrent_replace)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(runs._write, identity, {"name": label, "status": FINISHED}) for label in ["first", "second"]]
        for future in futures:
            future.result(timeout=10)
    assert len(set(temporary)) == 2
    assert runs.get(identity)["name"] in {"first", "second"}
    assert not list(runs.run_dir(identity).glob("*.tmp"))


@pytest.mark.parametrize("second", ["rename", "cancel", "finish"])
def test_read_modify_write_does_not_lose_concurrent_name_or_terminal_state(tmp_path, monkeypatch, second):
    runs = RunManager(tmp_path)
    identity = runs.new_run("original")
    write = RunManager._write
    entered, release = threading.Event(), threading.Event()
    first_status = CANCELLED if second == "finish" else FINISHED

    def paused_write(manager, run_id, record):
        if record["status"] == first_status and not entered.is_set():
            entered.set()
            assert release.wait(timeout=10)
        return write(manager, run_id, record)

    monkeypatch.setattr(RunManager, "_write", paused_write)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(runs.finish, identity, first_status)
        try:
            assert entered.wait(timeout=10)
            # The write is paused after its read: another manager must not be
            # allowed to read the same stale version and replace its outcome.
            with pytest.raises(BlockingIOError), file_lock(runs.runs_dir / ".locks/metadata.lock", blocking=False):
                pytest.fail("Read-modify-write must be serialized")
            other = RunManager(tmp_path)
            if second == "rename":
                following = pool.submit(other.rename, identity, "renamed")
            else:
                following = pool.submit(other.finish, identity, CANCELLED if second == "cancel" else FAILED)
        finally:
            release.set()
        first.result(timeout=10)
        following.result(timeout=10)
    final = runs.get(identity)
    assert final["status"] == (CANCELLED if second == "finish" else FINISHED)
    assert final["name"] == ("renamed" if second == "rename" else "original")


def test_deletion_during_log_copy_does_not_recreate_the_run(tmp_path, monkeypatch):
    runs = RunManager(tmp_path)
    identity = runs.new_run()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "minimal.log").write_text("tool completed")
    copy = shutil.copytree

    def delete_before_copy(src, dst, *args, **kwargs):
        if Path(src) == logs:
            assert runs.delete(identity)
        return copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(manager_module.shutil, "copytree", delete_before_copy)
    runs.finish(identity, FINISHED)
    assert runs.get(identity) is None
    assert not runs.run_dir(identity).exists()
    assert not list(tmp_path.glob(".run-logs-*"))


def test_log_folder_cleared_during_finish_keeps_completed_status(tmp_path, monkeypatch):
    runs = RunManager(tmp_path)
    identity = runs.new_run()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "minimal.log").write_text("tool completed")
    copy = shutil.copytree

    def clear_before_copy(src, dst, *args, **kwargs):
        if Path(src) == logs:
            shutil.rmtree(logs)
        return copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(manager_module.shutil, "copytree", clear_before_copy)
    runs.finish(identity, FINISHED)
    assert runs.get(identity)["status"] == FINISHED
    assert not list(tmp_path.glob(".run-logs-*"))


def test_run_directory_disappearing_during_listing_is_an_empty_state(tmp_path, monkeypatch):
    runs = RunManager(tmp_path)
    runs.new_run()
    iterdir = Path.iterdir

    def disappear(path):
        if path == runs.runs_dir:
            shutil.rmtree(path)
        return iterdir(path)

    monkeypatch.setattr(Path, "iterdir", disappear)
    assert runs.list_runs() == []


def test_archive_replacement_leaves_previous_complete_zip_readable(tmp_path, monkeypatch):
    runs = RunManager(tmp_path)
    identity = runs.new_run()
    result = runs.results_dir(identity) / "data.tsv"
    result.write_text("original result")
    runs.finish(identity, FINISHED)
    archive = runs.zip(identity)
    old = archive.read_bytes()
    result.write_text("updated result")
    open_zip = zipfile.ZipFile
    seen = []

    def inspect_previous(file, mode="r", *args, **kwargs):
        writer = open_zip(file, mode, *args, **kwargs)
        if mode == "w":
            assert archive.read_bytes() == old
            with open_zip(archive) as previous:
                assert previous.read("results/data.tsv") == b"original result"
            seen.append(Path(file))
        return writer

    monkeypatch.setattr(manager_module.zipfile, "ZipFile", inspect_previous)
    runs.zip(identity)
    assert seen and seen[0] != archive
    with open_zip(archive) as current:
        assert current.read("results/data.tsv") == b"updated result"
    assert not list(archive.parent.glob(".*.zip"))


@pytest.mark.parametrize("failure", [None, "contention", "unexpected"])
def test_windows_lock_byte_range_contract(tmp_path, monkeypatch, failure):
    import errno
    import os
    from types import SimpleNamespace

    lock_globals = file_lock.__wrapped__.__globals__
    calls, sleeps = [], []

    def locking(descriptor, mode, count):
        calls.append((descriptor, mode, count))
        if mode == 1 and failure == "contention" and len(calls) == 1:
            raise OSError(errno.EACCES, "Sharing conflict")
        if failure == "unexpected":
            raise OSError(errno.EIO, "Storage failed")

    monkeypatch.setitem(lock_globals, "_WINDOWS", True)
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(locking=locking, LK_NBLCK=1, LK_UNLCK=2))
    monkeypatch.setattr(lock_globals["time"], "sleep", sleeps.append)
    path = tmp_path / ".locks/windows.lock"
    if failure == "unexpected":
        with pytest.raises(OSError, match="Storage failed"), file_lock(path):
            pytest.fail("An I/O failure cannot acquire the lock")
        assert [call[1] for call in calls] == [1]
    else:
        with pytest.raises(RuntimeError, match="operation failed"), file_lock(path):
            assert path.read_bytes() == b"\0"
            raise RuntimeError("operation failed")
        assert [call[1] for call in calls] == ([1, 1, 2] if failure else [1, 2])
        assert sleeps == ([0.05] if failure else [])
        assert all(call[2] == 1 for call in calls)
    with pytest.raises(OSError):
        os.fstat(calls[0][0])


def test_windows_nonblocking_contention_keeps_existing_lock_file(tmp_path, monkeypatch):
    import errno
    from types import SimpleNamespace

    lock_globals = file_lock.__wrapped__.__globals__
    calls = []

    def locking(descriptor, mode, count):
        calls.append((mode, count))
        raise OSError(errno.EAGAIN, "Sharing conflict")

    monkeypatch.setitem(lock_globals, "_WINDOWS", True)
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(locking=locking, LK_NBLCK=1, LK_UNLCK=2))
    path = tmp_path / "existing.lock"
    path.write_bytes(b"x")
    with pytest.raises(BlockingIOError), file_lock(path, blocking=False):
        pytest.fail("A busy lock must fail without blocking")
    assert calls == [(1, 1)]
    assert path.read_bytes() == b"x"


@pytest.mark.parametrize("missing", [True, False])
def test_nested_log_copy_race_ignores_only_disappeared_sources(tmp_path, monkeypatch, missing):
    runs = RunManager(tmp_path)
    identity = runs.new_run()
    logs = tmp_path / "logs/nested"
    logs.mkdir(parents=True)
    source = logs / "commands.log"
    source.write_text("completed native command")
    copy = shutil.copyfile

    def race(src, dst, *args, **kwargs):
        if Path(src) == source:
            if missing:
                source.unlink()
            else:
                raise PermissionError("The log destination cannot be written")
        return copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(manager_module.shutil, "copyfile", race)
    if missing:
        runs.finish(identity, FINISHED)
    else:
        with pytest.raises(shutil.Error, match="destination cannot be written"):
            runs.finish(identity, FINISHED)
    assert runs.get(identity)["status"] == FINISHED
    assert not list(tmp_path.glob(".run-logs-*"))
