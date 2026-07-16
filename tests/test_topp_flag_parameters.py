"""
Unit tests for PR #397 — flag parameter support for TOPP tools.

PR #397 lets a caller mark certain TOPP parameters as CLI *flags*: parameters
passed by presence only (e.g. ``-force``), without a trailing value. The flag
names are persisted per tool instance by ``input_TOPP()`` into both
``st.session_state["_topp_flag_params"]`` and ``params.json["_flag_params"]``,
and consumed by ``run_topp()`` in ``src/workflow/CommandExecutor.py`` when it
builds the command line.

These tests exercise ``run_topp()`` — the consumer that turns the persisted flag
definitions and merged parameters into an actual command. Driving ``run_topp()``
also validates the persistence *contract* (the exact ``_flag_params`` /
``_topp_flag_params`` shapes that ``input_TOPP()`` writes), which is where the two
halves of the feature meet.

The suite covers the working behaviour of the feature and also guards the two
issues CodeRabbit flagged during review, which are now fixed in ``run_topp()``:
    - Finding 1 (per-tool flag fallback):
      https://github.com/OpenMS/streamlit-template/pull/397#discussion_r3585023551
    - Finding 2 (list expansion / empty-list skipping):
      https://github.com/OpenMS/streamlit-template/pull/397#discussion_r3585023558
The tests that pin those findings carry a "CodeRabbit finding N" note in their
docstrings and live alongside the related behaviour they protect.
"""
import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Import the modules under test with `streamlit` (and `pyopenms`) mocked at the
# sys.modules level. Both CommandExecutor and ParameterManager do
# `import streamlit as st` at module top (ParameterManager also
# `import pyopenms as poms`). run_topp() only needs `st.session_state` to behave
# like a plain dict and never touches pyopenms, so lightweight mocks keep the
# test runnable without those heavy deps installed while still exercising the
# real command-construction logic. Mirrors tests/test_tool_instance_name.py.
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


TOOL = "FeatureFinderMetabo"


@pytest.fixture(autouse=True)
def reset_session_state():
    """Give each test a fresh, empty mocked session_state."""
    mock_streamlit.session_state = {}
    yield
    mock_streamlit.session_state = {}


def build_command(
    params_json=None,
    session_state=None,
    *,
    tool=TOOL,
    input_output=None,
    custom_params=None,
    tool_instance_name=None,
):
    """
    Invoke ``run_topp()`` with the supplied ``params.json`` content and
    ``session_state``, and return the single command list it builds.

    ``run_command`` / ``run_multiple_commands`` are stubbed so nothing is
    executed; the built command is captured from the ``run_command`` mock.
    ``max_threads`` is pinned to 1 so the trailing ``-threads`` argument is
    deterministic.
    """
    if input_output is None:
        input_output = {"in": ["input.mzML"], "out": ["output.featureXML"]}

    params_json = dict(params_json or {})
    params_json.setdefault("max_threads", 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_dir = Path(tmpdir)
        pm = ParameterManager(workflow_dir)
        with open(pm.params_file, "w", encoding="utf-8") as f:
            json.dump(params_json, f)

        mock_streamlit.session_state = dict(session_state or {})

        executor = CommandExecutor(workflow_dir, MagicMock(), pm)
        executor.run_command = MagicMock(return_value=True)
        executor.run_multiple_commands = MagicMock(return_value=True)

        executor.run_topp(
            tool,
            input_output,
            custom_params=custom_params or {},
            tool_instance_name=tool_instance_name or tool,
        )

        assert executor.run_command.call_count == 1, (
            "expected exactly one single-process command, got "
            f"{executor.run_command.call_count}"
        )
        return executor.run_command.call_args.args[0]


# --------------------------- assertion helpers -----------------------------

def has_flag(cmd, name):
    """True if ``-name`` appears anywhere in the command."""
    return f"-{name}" in cmd


def token_after(cmd, name):
    """The single token immediately following ``-name`` (or None if it is last)."""
    idx = cmd.index(f"-{name}")
    return cmd[idx + 1] if idx + 1 < len(cmd) else None


def values_after(cmd, name):
    """All value tokens following ``-name`` up to the next ``-flag`` token."""
    idx = cmd.index(f"-{name}")
    vals = []
    for tok in cmd[idx + 1:]:
        if tok.startswith("-"):
            break
        vals.append(tok)
    return vals


def is_bare_flag(cmd, name):
    """True if ``-name`` is present with no value (next token is another flag)."""
    if not has_flag(cmd, name):
        return False
    nxt = token_after(cmd, name)
    return nxt is None or nxt.startswith("-")


# ============================ working behaviour ============================


class TestCommandSkeleton:
    def test_input_output_files_prefixed(self):
        cmd = build_command()
        assert cmd[0] == TOOL
        assert cmd[1:5] == ["-in", "input.mzML", "-out", "output.featureXML"]
        # threads pinned to 1 and always appended last
        assert cmd[-2:] == ["-threads", "1"]

    def test_collected_files_passed_as_single_list(self):
        # A [["a", "b"]] entry is expanded in place after its -key.
        cmd = build_command(input_output={"in": [["a.mzML", "b.mzML"]], "out": ["c.featureXML"]})
        assert cmd[1:4] == ["-in", "a.mzML", "b.mzML"]


class TestFlagParameters:
    """Flags emit a bare ``-key`` when enabled and nothing when disabled."""

    def test_flag_true_bool_emits_bare_flag(self):
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}, TOOL: {"force": True}}
        )
        assert is_bare_flag(cmd, "force")
        assert "True" not in cmd

    def test_flag_string_true_emits_bare_flag(self):
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}, TOOL: {"force": "true"}}
        )
        assert is_bare_flag(cmd, "force")
        assert "true" not in cmd

    def test_flag_string_true_is_case_insensitive(self):
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}, TOOL: {"force": "True"}}
        )
        assert is_bare_flag(cmd, "force")

    def test_flag_false_bool_omitted(self):
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}, TOOL: {"force": False}}
        )
        assert not has_flag(cmd, "force")

    def test_flag_string_false_omitted(self):
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}, TOOL: {"force": "false"}}
        )
        assert not has_flag(cmd, "force")


class TestRegularParameters:
    """Non-flag merged parameters keep the existing value-appending behaviour."""

    def test_empty_string_skipped(self):
        cmd = build_command({TOOL: {"opt": ""}})
        assert not has_flag(cmd, "opt")

    def test_none_skipped(self):
        cmd = build_command({TOOL: {"opt": None}})
        assert not has_flag(cmd, "opt")

    def test_zero_is_preserved(self):
        # 0 and 0.0 are valid values, not "empty" — they must be passed through.
        cmd = build_command({TOOL: {"min_int": 0, "min_float": 0.0}})
        assert values_after(cmd, "min_int") == ["0"]
        assert values_after(cmd, "min_float") == ["0.0"]

    def test_scalar_value_appended(self):
        cmd = build_command({TOOL: {"mz_tolerance": 10.5}})
        assert values_after(cmd, "mz_tolerance") == ["10.5"]

    def test_multiline_string_split_into_args(self):
        cmd = build_command({TOOL: {"seq": "ALPHA\nBETA\nGAMMA"}})
        assert values_after(cmd, "seq") == ["ALPHA", "BETA", "GAMMA"]

    def test_merged_list_param_expanded(self):
        """
        CodeRabbit finding 2 (fixed): a list-valued merged parameter expands into
        separate CLI args, not its Python ``str()`` (e.g. ``"['a', 'b']"``).
        https://github.com/OpenMS/streamlit-template/pull/397#discussion_r3585023558
        """
        cmd = build_command({TOOL: {"ids": ["a", "b"]}})
        assert values_after(cmd, "ids") == ["a", "b"]

    def test_merged_empty_list_param_skipped(self):
        """
        CodeRabbit finding 2 (fixed): an empty-list merged parameter is omitted
        entirely rather than emitting a ``-key`` with no usable value.
        https://github.com/OpenMS/streamlit-template/pull/397#discussion_r3585023558
        """
        cmd = build_command({TOOL: {"ids": []}})
        assert not has_flag(cmd, "ids")


class TestCustomParameters:
    """custom_params share the flag set and expand non-empty lists."""

    def test_custom_flag_truthy_bare(self):
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}},
            custom_params={"force": True},
        )
        assert is_bare_flag(cmd, "force")

    def test_custom_flag_false_omitted(self):
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}},
            custom_params={"force": False},
        )
        assert not has_flag(cmd, "force")

    def test_custom_scalar_value(self):
        cmd = build_command(custom_params={"extra": 5})
        assert values_after(cmd, "extra") == ["5"]

    def test_custom_nonempty_list_expanded(self):
        cmd = build_command(custom_params={"ids": ["a", "b", "c"]})
        assert values_after(cmd, "ids") == ["a", "b", "c"]

    def test_custom_empty_string_skipped(self):
        cmd = build_command(custom_params={"opt": ""})
        assert not has_flag(cmd, "opt")

    def test_custom_empty_list_param_skipped(self):
        """
        CodeRabbit finding 2 (fixed): an empty-list custom parameter is omitted
        rather than emitting a bare ``-key`` with no value.
        https://github.com/OpenMS/streamlit-template/pull/397#discussion_r3585023558
        """
        cmd = build_command(custom_params={"ids": []})
        assert not has_flag(cmd, "ids")


class TestFlagSourceContract:
    """Where run_topp() reads the flag definitions from."""

    def test_flag_params_loaded_from_params_json(self):
        # Survives a session restart: only params.json carries the flag list.
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}, TOOL: {"force": True}},
            session_state={},
        )
        assert is_bare_flag(cmd, "force")

    def test_fallback_to_session_state_when_json_has_no_flags(self):
        # params.json has no _flag_params at all -> live session_state is used.
        cmd = build_command(
            {TOOL: {"force": True}},
            session_state={"_topp_flag_params": {TOOL: ["force"]}},
        )
        assert is_bare_flag(cmd, "force")

    def test_params_json_takes_priority_over_session_state(self):
        # params.json says "force" is a flag; session_state disagrees (empty).
        # params.json wins, so force is treated as a flag (bare, no value).
        cmd = build_command(
            {"_flag_params": {TOOL: ["force"]}, TOOL: {"force": True}},
            session_state={"_topp_flag_params": {TOOL: []}},
        )
        assert is_bare_flag(cmd, "force")
        assert "True" not in cmd

    def test_flag_fallback_uses_current_tool_when_other_tool_has_flags(self):
        """
        CodeRabbit finding 1 (fixed): when params.json._flag_params holds an entry
        for a DIFFERENT tool, the current tool's flags must still be read from the
        session_state fallback. Previously the global ``if not flag_map`` check
        skipped the fallback whenever any tool had flags, so the current tool's
        flag was treated as a regular parameter and emitted as ``-force True``.
        https://github.com/OpenMS/streamlit-template/pull/397#discussion_r3585023551
        """
        cmd = build_command(
            {"_flag_params": {"OtherTool": ["some_flag"]}, TOOL: {"force": True}},
            session_state={"_topp_flag_params": {TOOL: ["force"]}},
        )
        assert is_bare_flag(cmd, "force")
        assert "True" not in cmd
