"""
Per-file progress of run_topp() (src/workflow/progress.py).

run_topp() records each tool call as a step with one entry per command (input
file); a failed entry keeps the exit code and the tail of the tool output, and
the failure is logged as "While running <tool> on file n of N (<name>)". A
fake TOPP tool on PATH stands in for a real one.
"""
import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_original_streamlit = sys.modules.get("streamlit")
_original_pyopenms = sys.modules.get("pyopenms")
sys.modules["streamlit"] = mock_streamlit
if _original_pyopenms is None:
    sys.modules["pyopenms"] = MagicMock()

from src.workflow.ParameterManager import ParameterManager
from src.workflow.CommandExecutor import CommandExecutor
from src.workflow.Logger import Logger
from src.workflow.progress import (
    RunProgress,
    failure_context,
    file_counts,
    failures,
    format_duration,
    key_message,
    read_progress,
)

if _original_streamlit is not None:
    sys.modules["streamlit"] = _original_streamlit
else:
    sys.modules.pop("streamlit", None)
if _original_pyopenms is None:
    sys.modules.pop("pyopenms", None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)

FAKE_TOOL = """#!{python}
import os, sys, time
time.sleep(float(os.environ.get("FAKE_TOOL_SECONDS", "0")))
args = sys.argv[1:]
name = args[args.index("-in") + 1]
print("Progress: loading " + name)
if "bad" in name:
    print("Error: Unable to read file (" + name + ")", file=sys.stderr)
    sys.exit(3)
"""


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    """A workflow dir with local settings, 2 threads and FakeTool on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool = bin_dir / "FakeTool"
    tool.write_text(FAKE_TOOL.format(python=sys.executable))
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    (tmp_path / "settings.json").write_text(
        json.dumps({"online_deployment": False, "max_threads": {"local": 2, "online": 1}})
    )
    monkeypatch.chdir(tmp_path)
    wf_dir = tmp_path / "wf"
    wf_dir.mkdir()
    pm = ParameterManager(wf_dir)
    pm.params_file.write_text(json.dumps({"max_threads": 2}))
    executor = CommandExecutor(wf_dir, Logger(wf_dir), pm)
    (wf_dir / "pids").mkdir()
    return wf_dir, executor


def test_run_topp_records_every_file(workflow):
    wf_dir, executor = workflow
    ok = executor.run_topp(
        "FakeTool",
        {"in": ["a/one.mzML", "a/two.mzML", "a/three.mzML"], "out": ["1", "2", "3"]},
    )
    assert ok
    state = read_progress(wf_dir)
    (step,) = state["steps"]
    assert step["tool"] == "FakeTool"
    assert [f["name"] for f in step["files"]] == ["one.mzML", "two.mzML", "three.mzML"]
    assert [f["status"] for f in step["files"]] == ["done"] * 3
    assert all(f["ended"] >= f["started"] for f in step["files"])
    assert step["ended"] is not None
    assert (step["threads"], step["parallel"]) == (1, 2)
    assert failures(state) == []


def test_failed_file_is_put_in_context(workflow):
    wf_dir, executor = workflow
    ok = executor.run_topp(
        "FakeTool",
        {"in": ["one.mzML", "bad.mzML", "three.mzML"], "out": ["1", "2", "3"]},
        tool_instance_name="FakeTool-second",
    )
    assert not ok
    state = read_progress(wf_dir)
    statuses = [f["status"] for f in state["steps"][0]["files"]]
    assert statuses == ["done", "failed", "done"]
    (failure,) = failures(state)
    assert failure["context"] == (
        "While running FakeTool (FakeTool-second) on file 2 of 3 (bad.mzML)"
    )
    assert failure["message"] == "Error: Unable to read file (bad.mzML)"
    assert failure["returncode"] == 3
    # stdout tail first, then stderr
    assert failure["output"] == [
        "Progress: loading bad.mzML",
        "Error: Unable to read file (bad.mzML)",
    ]
    log = (wf_dir / "logs" / "minimal.log").read_text()
    assert (
        "ERROR: While running FakeTool (FakeTool-second) on file 2 of 3 (bad.mzML) (exit code 3)"
        in log
    )


def test_single_command_and_collected_inputs(workflow):
    wf_dir, executor = workflow
    assert executor.run_topp("FakeTool", {"in": ["only.mzML"], "out": ["o"]})
    # A collected list goes to one command: labelled by its size
    labels = CommandExecutor._command_labels({"in": [["a.x", "b.x"]], "out": ["o"]}, 1)
    assert labels == ["2 files"]
    # The per-file key wins over a shared input such as a database
    labels = CommandExecutor._command_labels(
        {"database": ["db.fasta"], "in": ["a.mzML", "b.mzML"], "out": ["1", "2"]}, 2
    )
    assert labels == ["a.mzML", "b.mzML"]
    state = read_progress(wf_dir)
    step = state["steps"][0]
    assert failure_context(step, 0) == "While running FakeTool on (only.mzML)"


def test_missing_tool_is_recorded_and_raises(workflow):
    wf_dir, executor = workflow
    with pytest.raises(OSError):
        executor.run_topp("NoSuchTool", {"in": ["x.mzML"], "out": ["o"]})
    (failure,) = failures(read_progress(wf_dir))
    assert failure["context"] == "While running NoSuchTool on (x.mzML)"
    assert failure["returncode"] == -1


def test_progress_helpers(tmp_path):
    assert read_progress(tmp_path) is None
    progress = RunProgress(tmp_path)
    step = progress.start_step("T", ["a", "b"])
    progress.file_started(step, 0)
    progress.file_finished(step, 0, ok=False, returncode=1, output=[str(i) for i in range(300)])
    entry = read_progress(tmp_path)["steps"][0]["files"][0]
    assert len(entry["output"]) == 200 and entry["output"][-1] == "299"
    assert key_message(["start", "ERROR: bad input", "cleanup", ""]) == "ERROR: bad input"
    assert key_message(["only line"]) == "only line"
    openms = (
        "Error: Unable to read file (- due to that error of type Parse Error in: "
        "/build/src/openms/source/FORMAT/HANDLERS/XMLHandler.cpp@108-void "
        "OpenMS::Internal::XMLHandler::fatalError(ActionMode) const)"
    )
    assert key_message([openms]) == (
        "Error: Unable to read file (- due to that error of type Parse Error)"
    )
    assert key_message([]) == ""
    assert format_duration(42) == "0:42"
    assert format_duration(725) == "12:05"
    assert format_duration(3725) == "1:02:05"


def _max_overlap(entries):
    """Most files whose [started, ended] intervals overlap at one moment."""
    events = sorted(
        [(e["started"], 1) for e in entries] + [(e["ended"], -1) for e in entries],
        key=lambda ev: (ev[0], ev[1]),
    )
    running = most = 0
    for _, delta in events:
        running += delta
        most = max(most, running)
    return most


def test_parallel_files_are_each_tracked(workflow, monkeypatch):
    """Files run two at a time; every start and end lands in progress.json."""
    wf_dir, executor = workflow
    monkeypatch.setenv("FAKE_TOOL_SECONDS", "0.4")
    names = [f"s{i}.mzML" for i in range(6)]
    names[3] = "bad.mzML"
    ok = executor.run_topp(
        "FakeTool", {"in": names, "out": [str(i) for i in range(6)]}
    )
    assert not ok
    step = read_progress(wf_dir)["steps"][0]
    assert (step["threads"], step["parallel"]) == (1, 2)
    statuses = [f["status"] for f in step["files"]]
    assert statuses == ["done", "done", "done", "failed", "done", "done"]
    assert file_counts(step) == {"pending": 0, "running": 0, "done": 5, "failed": 1}
    # Two at a time, never more: the semaphore, as recorded
    assert _max_overlap(step["files"]) == 2
    (failure,) = failures(read_progress(wf_dir))
    assert failure["context"] == "While running FakeTool on file 4 of 6 (bad.mzML)"


def test_concurrent_updates_are_not_lost(tmp_path):
    """Many threads updating the same step at once: no entry is lost."""
    import threading

    progress = RunProgress(tmp_path)
    step = progress.start_step("T", [str(i) for i in range(40)], parallel=8)

    def work(i):
        progress.file_started(step, i)
        progress.file_finished(step, i, ok=i % 7 != 0, returncode=1)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    counts = file_counts(read_progress(tmp_path)["steps"][0])
    assert counts == {"pending": 0, "running": 0, "done": 34, "failed": 6}
    assert not list((tmp_path / "logs").glob(".progress-*"))


def test_replace_is_retried_while_the_file_is_held(tmp_path, monkeypatch):
    """Windows refuses the replace while the Run page reads the file."""
    import src.workflow.progress as progress_module

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("in use")
        real_replace(src, dst)

    monkeypatch.setattr(progress_module.os, "replace", flaky_replace)
    monkeypatch.setattr(progress_module.time, "sleep", lambda s: None)
    progress = RunProgress(tmp_path)
    assert progress.start_step("T", ["a"]) == 0
    assert read_progress(tmp_path)["steps"][0]["tool"] == "T"


def test_progress_that_cannot_be_written_does_not_stop_the_run(tmp_path, monkeypatch):
    import src.workflow.progress as progress_module

    def refuse(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(progress_module.os, "replace", refuse)
    monkeypatch.setattr(progress_module.time, "sleep", lambda s: None)
    progress = RunProgress(tmp_path)
    step = progress.start_step("T", ["a"])
    assert step == -1
    progress.file_started(step, 0)
    progress.file_finished(step, 0, ok=False)
    progress.end_step(step)
    assert read_progress(tmp_path) is None
    assert not list((tmp_path / "logs").glob(".progress-*"))


def test_missing_tool_in_parallel_fails_the_step(workflow):
    """A command that cannot start in a worker thread counts as failed."""
    wf_dir, executor = workflow
    ok = executor.run_topp(
        "NoSuchTool", {"in": ["x.mzML", "y.mzML"], "out": ["1", "2"]}
    )
    assert ok is False
    step = read_progress(wf_dir)["steps"][0]
    assert [f["status"] for f in step["files"]] == ["failed", "failed"]
