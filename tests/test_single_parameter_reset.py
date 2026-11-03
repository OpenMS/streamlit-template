"""
Changing one TOPP parameter outside its widget, as the "All parameters" dialog
of input_TOPP() does: set_topp_parameter(), reset_topp_parameter() and the
applied preset's values for one tool (applied_preset_values()).
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Same sys.modules mocking as tests/test_user_presets.py
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_original_streamlit = sys.modules.get("streamlit")
sys.modules["streamlit"] = mock_streamlit

from src.workflow.ParameterManager import ParameterManager

if _original_streamlit is not None:
    sys.modules["streamlit"] = _original_streamlit
else:
    sys.modules.pop("streamlit", None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


BUILTIN = {"test-workflow": {"Fast": {"ToolA": {"param1": 10.0}}}}


@pytest.fixture(autouse=True)
def reset_session_state():
    mock_streamlit.session_state.clear()
    yield
    mock_streamlit.session_state.clear()


@pytest.fixture
def pm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "presets.json").write_text(json.dumps(BUILTIN), encoding="utf-8")
    workflow_dir = tmp_path / "test-workflow"
    workflow_dir.mkdir()
    manager = ParameterManager(workflow_dir)
    manager.params_file.write_text(
        json.dumps(
            {
                "_defaults": {"ToolA": {"param1": 1.0}},
                "ToolA": {"param1": 5.0, "param2": "x"},
                "ToolB": {"param3": 3},
            }
        ),
        encoding="utf-8",
    )
    return manager


def stored(manager):
    return json.loads(manager.params_file.read_text(encoding="utf-8"))


def key(manager, tool, name):
    return f"{manager.topp_param_prefix}{tool}:1:{name}"


def test_set_stores_value_and_drops_widget_state(pm):
    mock_streamlit.session_state[key(pm, "ToolA", "param2")] = "x"
    mock_streamlit.session_state[key(pm, "ToolA", "param2") + "_display"] = ["x"]
    assert pm.set_topp_parameter("ToolA", "param2", "y", default="z")
    assert stored(pm)["ToolA"] == {"param1": 5.0, "param2": "y"}
    assert key(pm, "ToolA", "param2") not in mock_streamlit.session_state
    assert key(pm, "ToolA", "param2") + "_display" not in mock_streamlit.session_state
    # Other tools are untouched
    assert stored(pm)["ToolB"] == {"param3": 3}


def test_set_to_default_removes_the_override(pm):
    assert pm.set_topp_parameter("ToolA", "param1", 1, default=1.0)
    assert "param1" not in stored(pm)["ToolA"]
    # Lists compare with their newline-joined form
    assert pm.set_topp_parameter("ToolC", "mods", "a\nb", default=["a", "b"])
    assert stored(pm)["ToolC"] == {}


def test_reset_and_unreadable_file(pm):
    mock_streamlit.session_state[key(pm, "ToolA", "param1")] = 5.0
    assert pm.reset_topp_parameter("ToolA", "param1")
    assert stored(pm)["ToolA"] == {"param2": "x"}
    assert key(pm, "ToolA", "param1") not in mock_streamlit.session_state
    # Nothing stored for that parameter: still fine
    assert pm.reset_topp_parameter("ToolB", "nope")

    pm.params_file.write_text("{torn", encoding="utf-8")
    assert not pm.set_topp_parameter("ToolA", "param1", 2.0)
    assert not pm.reset_topp_parameter("ToolA", "param1")
    assert pm.params_file.read_text(encoding="utf-8") == "{torn"


def test_applied_preset_values(pm):
    assert pm.applied_preset_values("ToolA") == (None, {}, False)
    assert pm.apply_preset("Fast")
    # A built-in preset only sets what it names
    assert pm.applied_preset_values("ToolA") == ("Fast", {"param1": 10.0}, False)
    assert pm.applied_preset_values("ToolB") == ("Fast", {}, False)

    assert pm.save_user_preset("Mine")
    # A user preset is a full snapshot
    name, values, complete = pm.applied_preset_values("ToolA")
    assert (name, complete) == ("Mine", True)
    assert values == {"param1": 10.0, "param2": "x"}


def test_get_topp_defaults_without_ini(pm):
    assert pm.get_topp_defaults("ToolA") == {}
