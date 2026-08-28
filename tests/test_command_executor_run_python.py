"""
The ``run_python()`` result contract.

``CommandExecutor.run_topp()`` returns a bool and ``execution()`` gates on it.
``run_python()`` looked like it did the same — the shipped workflow guards both
of its Python steps with ``if not self.executor.run_python(...)`` — but it was
annotated ``-> None`` and simply discarded the bool ``run_command()`` handed
back, at every one of its branches. So those guards were dead code: a Python
tool that exited non-zero still produced ``execution() == True``,
``tasks.execute_workflow`` still wrote the ``WORKFLOW FINISHED`` marker, and
``classify_log_outcome`` still reported "finished" next to the
``ERROR: Command failed with exit code`` line already in the log.

That is invisible from ``tests/test_tasks.py``, which drives a ``MagicMock``
executor: ``run_python.return_value = False`` is a value the real method could
not produce, so the parametrized "python-export-fails" case certified a code
path that could never run. These tests pin the real thing.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Import with `streamlit` and `pyopenms` mocked at the sys.modules level,
# mirroring tests/test_topp_flag_parameters.py. run_python() needs neither: it
# reads params.json through ParameterManager and shells out through
# run_command(), which is stubbed below.
# ---------------------------------------------------------------------------
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_original_streamlit = sys.modules.get("streamlit")
_original_pyopenms = sys.modules.get("pyopenms")
sys.modules["streamlit"] = mock_streamlit
if _original_pyopenms is None:
    sys.modules["pyopenms"] = MagicMock()

from src.workflow.ParameterManager import ParameterManager
from src.workflow.CommandExecutor import CommandExecutor

# Restore the original modules so other test files import the real ones. The
# classes imported above keep their module-level `st`/`poms` bound to the mocks.
if _original_streamlit is not None:
    sys.modules["streamlit"] = _original_streamlit
else:
    sys.modules.pop("streamlit", None)
if _original_pyopenms is None:
    sys.modules.pop("pyopenms", None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


SCRIPT_WITH_DEFAULTS = '''DEFAULTS = [
    {"key": "in", "value": [], "hide": True},
    {"key": "my-param", "value": 5, "name": "My Parameter"},
]
'''

SCRIPT_WITHOUT_DEFAULTS = "PLACEHOLDER = 1\n"


def _executor(tmp_path, run_command_result):
    """A CommandExecutor whose run_command() reports the given exit status."""
    executor = CommandExecutor(tmp_path, MagicMock(), ParameterManager(tmp_path))
    executor.run_command = MagicMock(return_value=run_command_result)
    return executor


def _write_tool(tmp_path, source=SCRIPT_WITH_DEFAULTS, name="example_tool.py"):
    script = tmp_path / name
    script.write_text(source, encoding="utf-8")
    return script


@pytest.mark.parametrize("exit_status", [True, False], ids=["exit-0", "exit-non-zero"])
def test_run_python_reports_the_scripts_exit_status(tmp_path, exit_status):
    """
    The bool from run_command() has to reach the caller.

    Without it every `if not self.executor.run_python(...)` in execution() is
    dead code and a failed Python tool is reported as a completed workflow.
    """
    executor = _executor(tmp_path, exit_status)
    script = _write_tool(tmp_path)

    result = executor.run_python(str(script), {"in": ["a.mzML"]})

    assert result is exit_status, (
        f"run_python() returned {result!r} for a script that exited "
        f"{'0' if exit_status else 'non-zero'}; it must return the same bool "
        "run_topp() does, or execution() cannot tell the two apart"
    )
    assert executor.run_command.call_count == 1


def test_run_python_without_defaults_reports_the_exit_status(tmp_path):
    """The no-DEFAULTS branch runs the script too, so it reports on it too."""
    executor = _executor(tmp_path, False)
    script = _write_tool(tmp_path, SCRIPT_WITHOUT_DEFAULTS, "bare_tool.py")

    assert executor.run_python(str(script)) is False
    assert executor.run_command.call_args.args[0] == ["python", str(script)]


def test_run_python_passes_the_parameters_file_and_cleans_it_up(tmp_path):
    """
    The DEFAULTS branch writes a temporary params file, passes it as argv and
    removes it. Pinned alongside the return value so returning early on failure
    cannot leak it into the workflow directory.
    """
    executor = _executor(tmp_path, False)
    script = _write_tool(tmp_path)

    executor.run_python(str(script), {"in": ["a.mzML"]})

    command = executor.run_command.call_args.args[0]
    assert command[:2] == ["python", str(script)]
    assert not Path(command[2]).exists(), (
        "the temporary parameter file was left behind in the workflow directory"
    )


def test_run_python_passes_input_output_and_stored_parameters(tmp_path):
    """
    Guards the argv the exit status is reported *about*: DEFAULTS, overridden by
    the stored params.json entries for this script, overridden by input_output.
    """
    pm = ParameterManager(tmp_path)
    script = _write_tool(tmp_path)
    pm.params_file.write_text(
        json.dumps({f"{script.name}:my-param": 42, "unrelated": 1}), encoding="utf-8"
    )

    executor = CommandExecutor(tmp_path, MagicMock(), pm)
    captured = {}

    def capture(command):
        captured["params"] = json.loads(
            Path(command[2]).read_text(encoding="utf-8")
        )
        return True

    executor.run_command = MagicMock(side_effect=capture)

    assert executor.run_python(str(script), {"in": ["a.mzML"]}) is True
    assert captured["params"]["my-param"] == 42
    assert captured["params"]["in"] == ["a.mzML"]
    assert "unrelated" not in captured["params"]


def test_missing_script_returns_false_instead_of_raising(tmp_path):
    """
    A script that is nowhere to be found used to log and fall through into
    importlib, raising out of execution() rather than reporting a failed step -
    and in queue mode that traceback is all the user gets.
    """
    executor = _executor(tmp_path, True)

    assert executor.run_python("definitely-not-a-real-tool") is False
    executor.run_command.assert_not_called()


def test_defaults_of_the_wrong_shape_is_not_reported_as_success(tmp_path):
    """
    DEFAULTS must be the documented list of parameter dicts. Anything else runs
    nothing at all, which is a failed step, not a successful one - reporting it
    as success would put the WORKFLOW FINISHED marker on a run that skipped a
    step silently.
    """
    executor = _executor(tmp_path, True)
    script = _write_tool(tmp_path, 'DEFAULTS = {"my-param": 5}\n', "dict_tool.py")

    assert executor.run_python(str(script)) is False
    executor.run_command.assert_not_called()
