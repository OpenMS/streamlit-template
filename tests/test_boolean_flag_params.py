"""
Tests for boolean flag parameter handling in CommandExecutor.run_topp().

Verifies that:
- Python bool True (flag-style) emits only the flag, no value
- Python bool False (flag-style) omits the flag entirely
- String "true"/"false" (string-style) emits -param true / -param false
- Other parameter types (int, float, str, empty, multiline) are unchanged
"""
import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Mock pyopenms and streamlit before importing project modules
mock_pyopenms = MagicMock()
mock_pyopenms.__version__ = "3.0.0"
sys.modules['pyopenms'] = mock_pyopenms

mock_streamlit = MagicMock()
mock_streamlit.session_state = {"settings": {"max_threads": {"local": 4, "online": 2}}}
sys.modules['streamlit'] = mock_streamlit

from src.workflow.ParameterManager import ParameterManager
from src.workflow.CommandExecutor import CommandExecutor
from src.workflow.Logger import Logger


@pytest.fixture
def workflow_env(tmp_path):
    """
    Set up a realistic workflow environment with a fake ini file and params.json.

    Creates:
    - tmp_path/ini/FakeTool.ini (empty file, run_topp only checks existence)
    - tmp_path/params.json with mixed parameter types
    """
    # Create ini directory and fake ini file
    ini_dir = tmp_path / "ini"
    ini_dir.mkdir()
    ini_file = ini_dir / "FakeTool.ini"
    ini_file.write_text("<PARAMETERS></PARAMETERS>")

    # Write params.json with all parameter type variants
    params = {
        "FakeTool": {
            "enable_feature": True,         # bool True -> flag only
            "disable_feature": False,        # bool False -> omit entirely
            "string_bool_on": "true",        # str "true" -> -param true
            "string_bool_off": "false",      # str "false" -> -param false
            "threshold": 1000.0,             # float
            "mode": "fast",                  # regular string
            "count": 5,                      # int
            "empty_flag": "",                # empty string -> flag only
            "multi_value": "val1\nval2",     # multiline string -> split
        }
    }
    params_file = tmp_path / "params.json"
    params_file.write_text(json.dumps(params, indent=4))

    return tmp_path


@pytest.fixture
def captured_command(workflow_env):
    """
    Create a CommandExecutor with mocked dependencies, call run_topp(),
    and return the command list that would have been executed.
    """
    captured = {}

    pm = ParameterManager(workflow_env)
    logger = MagicMock(spec=Logger)
    executor = CommandExecutor(workflow_env, logger, pm)

    # Capture the command instead of executing it
    def fake_run_command(cmd):
        captured["command"] = cmd
        return True

    executor.run_command = fake_run_command

    executor.run_topp("FakeTool", {"in": ["input.mzML"]})

    return captured["command"]


class TestBooleanFlagParams:
    """Test boolean flag parameter handling in run_topp()."""

    def test_bool_true_emits_flag_only(self, captured_command):
        """Python bool True should emit -flag with no following value."""
        idx = captured_command.index("-enable_feature")
        # Next element should NOT be "True" — it should be another flag or -threads
        next_elem = captured_command[idx + 1]
        assert next_elem.startswith("-"), (
            f"Expected flag-only for bool True, but got value '{next_elem}' after -enable_feature"
        )

    def test_bool_false_omits_flag(self, captured_command):
        """Python bool False should omit the flag entirely."""
        assert "-disable_feature" not in captured_command, (
            "bool False parameter should not appear in command at all"
        )

    def test_string_true_emits_value(self, captured_command):
        """String 'true' should emit -param true (with explicit value)."""
        idx = captured_command.index("-string_bool_on")
        assert captured_command[idx + 1] == "true", (
            f"Expected 'true' value after -string_bool_on, got '{captured_command[idx + 1]}'"
        )

    def test_string_false_emits_value(self, captured_command):
        """String 'false' should emit -param false (with explicit value)."""
        idx = captured_command.index("-string_bool_off")
        assert captured_command[idx + 1] == "false", (
            f"Expected 'false' value after -string_bool_off, got '{captured_command[idx + 1]}'"
        )

    def test_float_param(self, captured_command):
        """Float values should be emitted as string representation."""
        idx = captured_command.index("-threshold")
        assert captured_command[idx + 1] == "1000.0"

    def test_string_param(self, captured_command):
        """Regular string values should be emitted as-is."""
        idx = captured_command.index("-mode")
        assert captured_command[idx + 1] == "fast"

    def test_int_param(self, captured_command):
        """Integer values should be emitted as string representation."""
        idx = captured_command.index("-count")
        assert captured_command[idx + 1] == "5"

    def test_empty_string_emits_flag_only(self, captured_command):
        """Empty string should emit the flag with no value."""
        idx = captured_command.index("-empty_flag")
        next_elem = captured_command[idx + 1]
        assert next_elem.startswith("-"), (
            f"Expected flag-only for empty string, but got value '{next_elem}'"
        )

    def test_multiline_string_splits(self, captured_command):
        """Multiline string should be split into separate values."""
        idx = captured_command.index("-multi_value")
        assert captured_command[idx + 1] == "val1"
        assert captured_command[idx + 2] == "val2"

    def test_threads_present(self, captured_command):
        """The -threads flag should always be present."""
        assert "-threads" in captured_command

    def test_ini_flag_present(self, captured_command):
        """The -ini flag should be present when ini file exists."""
        assert "-ini" in captured_command
        idx = captured_command.index("-ini")
        assert captured_command[idx + 1].endswith("FakeTool.ini")

    def test_input_file_present(self, captured_command):
        """Input files should be present in the command."""
        assert "-in" in captured_command
        idx = captured_command.index("-in")
        assert captured_command[idx + 1] == "input.mzML"

    def test_command_starts_with_tool(self, captured_command):
        """Command should start with the tool name."""
        assert captured_command[0] == "FakeTool"
