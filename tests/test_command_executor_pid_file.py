"""
run_command() and a pid file removed while its tool ends.

After a tool exits and before run_command() has waited for it, the process is a
zombie. The Run page polls the workflow status, and pid_files.reap() removes the
pid file of a zombie as a process that is gone. run_command() then removed the
same file itself, got FileNotFoundError, and the whole workflow failed although
the tool had succeeded (seen in the macOS desktop app's end-to-end test).
"""
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

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

if _original_streamlit is not None:
    sys.modules["streamlit"] = _original_streamlit
else:
    sys.modules.pop("streamlit", None)
if _original_pyopenms is None:
    sys.modules.pop("pyopenms", None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


def test_run_command_succeeds_when_the_pid_file_is_already_gone(tmp_path, monkeypatch):
    executor = CommandExecutor(tmp_path, MagicMock(), ParameterManager(tmp_path))
    executor.pid_dir.mkdir()
    real_wait = subprocess.Popen.wait

    def reap_then_wait(process, *args, **kwargs):
        # What reap() does while the tool is a zombie: its pid file goes.
        for pid_file in executor.pid_dir.iterdir():
            pid_file.unlink()
        return real_wait(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "wait", reap_then_wait)

    assert executor.run_command([sys.executable, "-c", "print('done')"]) is True
    assert list(executor.pid_dir.iterdir()) == []
