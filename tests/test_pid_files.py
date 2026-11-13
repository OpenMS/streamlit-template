"""src/workflow/pid_files.py: pid files of processes that are gone are removed."""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workflow import pid_files  # noqa: E402
from src.workflow.pid_files import reap  # noqa: E402


def _ended_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def test_missing_folder_is_not_running(tmp_path):
    assert reap(tmp_path / "pids") == (False, 0)


def test_a_running_process_keeps_its_file(tmp_path):
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir()
    (pid_dir / str(os.getpid())).touch()
    assert reap(pid_dir) == (True, 0)
    assert (pid_dir / str(os.getpid())).exists()


def test_an_ended_process_loses_its_file_and_the_folder_goes(tmp_path):
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir()
    (pid_dir / str(_ended_pid())).touch()
    assert reap(pid_dir) == (False, 1)
    assert not pid_dir.exists()


def test_a_reused_pid_is_not_the_process_of_the_file(tmp_path):
    """After a restart the pid can belong to another process, started later."""
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir()
    pid_file = pid_dir / str(os.getpid())
    pid_file.touch()
    an_hour_before_this_process = pid_files.psutil.Process().create_time() - 3600
    os.utime(pid_file, (an_hour_before_this_process, an_hour_before_this_process))
    assert reap(pid_dir) == (False, 1)


def test_ended_and_running_processes_mixed(tmp_path):
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir()
    (pid_dir / str(_ended_pid())).touch()
    (pid_dir / str(os.getpid())).touch()
    assert reap(pid_dir) == (True, 1)
    assert [f.name for f in pid_dir.iterdir()] == [str(os.getpid())]


def test_a_new_empty_folder_is_a_start_in_progress(tmp_path):
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir()
    assert reap(pid_dir) == (False, 0)
    assert pid_dir.exists()
    old = time.time() - 120
    os.utime(pid_dir, (old, old))
    assert reap(pid_dir) == (False, 0)
    assert not pid_dir.exists()
