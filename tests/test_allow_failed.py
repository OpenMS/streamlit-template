"""
run_topp(..., allow_failed=True): a run goes on without the files a tool fails on.

One bad file of 200 used to fail the whole run. With ``allow_failed`` the call
returns True while any file worked, ``executor.failed`` names the others,
``keep_succeeded()`` drops them from the next step's inputs, and the Run page
of the finished run says which files were left out and why. A fake TOPP tool on
PATH stands in for a real one (it fails on any input whose name holds "bad").
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
name = args[args.index("-in") + 1]
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


IN = ["one.mzML", "bad.mzML", "three.mzML", "bad2.mzML"]
OUT = ["1", "2", "3", "4"]


def test_without_allow_failed_one_bad_file_fails_the_call(workflow):
    _, executor = workflow
    assert not executor.run_topp("FakeTool", {"in": IN, "out": OUT})
    assert executor.failed == [1, 3]


def test_allow_failed_goes_on_without_the_bad_files(workflow):
    wf_dir, executor = workflow
    assert executor.run_topp("FakeTool", {"in": IN, "out": OUT}, allow_failed=True)
    assert executor.failed == [1, 3]
    assert executor.keep_succeeded(OUT) == ["1", "3"]
    assert executor.keep_succeeded(IN) == ["one.mzML", "three.mzML"]

    state = read_progress(wf_dir)
    assert state["steps"][0]["allow_failed"] is True
    left = failures(state, left_out=True)
    assert [f["context"] for f in left] == [
        "While running FakeTool on file 2 of 4 (bad.mzML)",
        "While running FakeTool on file 4 of 4 (bad2.mzML)",
    ]
    assert left[0]["message"] == "Error: Unable to read file (bad.mzML)"
    assert failures(state, left_out=False) == []
    assert len(failures(state)) == 2

    log = (wf_dir / "logs" / "minimal.log").read_text()
    assert "FakeTool failed for 2 of 4 files; the run goes on without them: bad.mzML, bad2.mzML" in log


def test_allow_failed_still_fails_when_every_file_fails(workflow):
    wf_dir, executor = workflow
    ok = executor.run_topp(
        "FakeTool", {"in": ["bad.mzML", "bad2.mzML"], "out": ["1", "2"]}, allow_failed=True
    )
    assert not ok
    assert executor.keep_succeeded(["1", "2"]) == []
    assert "FakeTool failed for every file." in (wf_dir / "logs" / "minimal.log").read_text()


def test_single_file_call(workflow):
    _, executor = workflow
    assert executor.run_topp("FakeTool", {"in": ["one.mzML"], "out": ["1"]}, allow_failed=True)
    assert executor.failed == []
    assert not executor.run_topp("FakeTool", {"in": ["bad.mzML"], "out": ["1"]}, allow_failed=True)
    assert executor.failed == [0]


def test_keep_succeeded_before_any_call(workflow):
    _, executor = workflow
    assert executor.keep_succeeded([1, 2]) == [1, 2]


def _summary_script():
    import os
    from pathlib import Path

    from src.workflow.StreamlitUI import StreamlitUI

    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = Path(os.environ["SUMMARY_WORKFLOW_DIR"])
    ui._show_run_summary(show_failures=os.environ.get("SUMMARY_FAILED") == "1")


def test_run_page_names_the_files_left_out(workflow, monkeypatch):
    wf_dir, executor = workflow
    assert executor.run_topp("FakeTool", {"in": IN, "out": OUT}, allow_failed=True)
    monkeypatch.chdir(PROJECT_ROOT)
    monkeypatch.setenv("SUMMARY_WORKFLOW_DIR", str(wf_dir))
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_summary_script, default_timeout=60).run()
    assert not at.exception
    (warning,) = at.warning
    assert "2 files were left out after an error" in warning.value
    assert "file 2 of 4 (bad.mzML): Error: Unable to read file (bad.mzML)" in warning.value
    assert not at.error
    assert at.expander[0].label == "Tool output of the files left out"

    # A failed run shows its failures as errors, not a second time as left out
    monkeypatch.setenv("SUMMARY_FAILED", "1")
    at = AppTest.from_function(_summary_script, default_timeout=60).run()
    assert not at.warning
    # (two failed files of one tool: one line and a table of the files)
    (error,) = at.error
    assert "FakeTool failed on 2 of 4 files" in error.value
    assert len(at.dataframe) == 1
