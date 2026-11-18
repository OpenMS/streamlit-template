"""
run_topp(..., retry_singly=True): a command of several files that fails runs
again once per file, so one bad file does not take the others with it.

A search engine that builds its index once takes several files per command.
One unreadable file failed the whole command, and with ``allow_failed`` every
file of it was left out. The fake TOPP tool on PATH takes several ``-in``
files and fails when any of them holds "bad".
"""
import json
import os
import stat
import sys
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
from src.workflow.progress import failures, read_progress

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
import sys
args = sys.argv[1:]
start = args.index("-in") + 1
names = []
for a in args[start:]:
    if a.startswith("-"):
        break
    names.append(a)
with open("ran.txt", "a") as ran:
    ran.write(" ".join(names) + "\\n")
for name in names:
    if "bad" in name:
        print("Error: Unable to read file (" + name + ")", file=sys.stderr)
        sys.exit(3)
"""


@pytest.fixture
def workflow(tmp_path, monkeypatch):
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



BATCHES = [["one.mzML", "bad.mzML", "three.mzML"], ["four.mzML", "five.mzML"]]
OUTS = [["1", "2", "3"], ["4", "5"]]
FILES = [f for b in BATCHES for f in b]


def test_a_bad_file_leaves_out_only_itself(workflow):
    wf_dir, executor = workflow
    assert executor.run_topp(
        "FakeTool", {"in": BATCHES, "out": OUTS, "db": ["x.fasta"]}, retry_singly=True
    )
    assert executor.failed == [1]
    assert executor.keep_succeeded(FILES) == ["one.mzML", "three.mzML", "four.mzML", "five.mzML"]

    state = read_progress(wf_dir)
    first, again = state["steps"]
    assert [f["status"] for f in first["files"]] == ["retried", "done"]
    assert [f["name"] for f in again["files"]] == ["one.mzML", "bad.mzML", "three.mzML"]
    assert [f["status"] for f in again["files"]] == ["done", "failed", "done"]
    # Only the bad file is named as left out, not the command it was in
    left = failures(state, left_out=True)
    assert [f["file"] for f in left] == ["bad.mzML"]
    assert failures(state, left_out=False) == []

    log = (wf_dir / "logs" / "minimal.log").read_text()
    assert "running each of their files on its own" in log
    assert "FakeTool failed for 1 of 5 files; the run goes on without them: bad.mzML" in log
    assert "failed for every file" not in log


def test_every_file_good_runs_once(workflow):
    wf_dir, executor = workflow
    good = [["one.mzML", "two.mzML"], ["three.mzML"]]
    assert executor.run_topp("FakeTool", {"in": good, "out": [["1", "2"], ["3"]]}, retry_singly=True)
    assert executor.failed == []
    assert len(read_progress(wf_dir)["steps"]) == 1


def test_a_failed_single_file_command_is_not_run_again(workflow):
    wf_dir, executor = workflow
    io = {"in": [["one.mzML", "two.mzML"], ["bad.mzML"]], "out": [["1", "2"], ["3"]]}
    assert executor.run_topp("FakeTool", io, retry_singly=True)
    assert executor.failed == [2]
    state = read_progress(wf_dir)
    assert len(state["steps"]) == 1
    # The Run page names it as left out, the run went on without it
    assert [f["file"] for f in failures(state, left_out=True)] == ["bad.mzML"]


def test_every_file_bad_fails_the_call(workflow):
    wf_dir, executor = workflow
    io = {"in": [["bad.mzML", "bad2.mzML"]], "out": [["1", "2"]]}
    assert not executor.run_topp("FakeTool", io, retry_singly=True)
    assert executor.failed == [0, 1]
    assert executor.keep_succeeded(["a", "b"]) == []
    assert "FakeTool failed for every file." in (wf_dir / "logs" / "minimal.log").read_text()


def test_one_command_of_several_files(workflow):
    _, executor = workflow
    io = {"in": [["one.mzML", "bad.mzML"]], "out": [["1", "2"]]}
    assert executor.run_topp("FakeTool", io, retry_singly=True)
    assert executor.failed == [1]


def _ran(wf_dir):
    return (wf_dir.parent / "ran.txt").read_text().splitlines()


def test_a_shared_value_before_the_inputs(workflow):
    """A database given before the inputs does not make every command take
    the first command's files."""
    wf_dir, executor = workflow
    assert executor.run_topp(
        "FakeTool", {"db": ["x.fasta"], "in": BATCHES, "out": OUTS}, retry_singly=True
    )
    assert executor.failed == [1]
    ran = _ran(wf_dir)
    assert sorted(ran[:2]) == sorted(" ".join(b) for b in BATCHES)
    assert sorted(ran[2:]) == ["bad.mzML", "one.mzML", "three.mzML"]


def test_a_shared_input_is_not_taken_for_the_samples(workflow):
    wf_dir, executor = workflow
    io = {"in_db": ["db.fasta"], "in": [["one.mzML", "bad.mzML"]], "out": [["1", "2"]]}
    assert executor.run_topp("FakeTool", io, retry_singly=True)
    assert executor.failed == [1]
    assert sorted(_ran(wf_dir)[1:]) == ["bad.mzML", "one.mzML"]


def test_one_output_for_several_files_is_not_run_again(workflow):
    """Its runs would all write the one output, so its files are left out."""
    wf_dir, executor = workflow
    io = {"in": [["one.mzML", "bad.mzML"], ["three.mzML"]], "out": ["merged", "3"]}
    assert executor.run_topp("FakeTool", io, retry_singly=True)
    assert executor.failed == [0, 1]
    assert len(read_progress(wf_dir)["steps"]) == 1
