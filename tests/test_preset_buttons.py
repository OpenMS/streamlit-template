"""
``StreamlitUI.preset_buttons()`` must apply a preset in the button's callback,
never by calling ``st.rerun()`` from the button branch.

``preset_buttons()`` renders before ``configure()``. A ``st.rerun()`` there
interrupts the script before any configure widget is reached, and Streamlit
drops the widget state of every widget a run does not reach while keeping the
key. On the next run those widgets re-render from an empty value: selecting an
mzML file and then clicking a preset left the selection empty, and the next
start failed with "Select at least one mzML file".

A callback runs before the rerun starts, so the full run still renders every
widget and only the keys the preset deletes are re-seeded.
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Same sys.modules mocking as tests/test_streamlit_ui_param_read.py.
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_originals = {
    name: sys.modules.get(name)
    for name in ("streamlit", "pyopenms", "src.common.common")
}
sys.modules["streamlit"] = mock_streamlit
if _originals["pyopenms"] is None:
    sys.modules["pyopenms"] = MagicMock()
if _originals["src.common.common"] is None:
    sys.modules["src.common.common"] = MagicMock()

from src.workflow.ParameterManager import ParameterManager
from src.workflow.StreamlitUI import StreamlitUI

for name, module in _originals.items():
    if module is not None:
        sys.modules[name] = module
    else:
        sys.modules.pop(name, None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


PRESETS = {
    "test-workflow": {
        "Fast": {
            "_description": "Fewer iterations",
            "FeatureFinderMetabo": {"algorithm:common:noise_threshold_int": 500.0},
        }
    }
}


@pytest.fixture(autouse=True)
def reset_streamlit_mock():
    mock_streamlit.reset_mock()
    mock_streamlit.session_state = {}
    mock_streamlit.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
    yield
    mock_streamlit.reset_mock()
    mock_streamlit.columns.side_effect = None
    mock_streamlit.session_state = {}


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "presets.json").write_text(json.dumps(PRESETS), encoding="utf-8")
    workflow_dir = tmp_path / "test-workflow"
    ui = object.__new__(StreamlitUI)
    ui.parameter_manager = ParameterManager(workflow_dir)
    ui.parameter_manager.params_file.write_text(
        json.dumps({"mzML-files": ["a.mzML"]}), encoding="utf-8"
    )
    return ui


def test_button_applies_the_preset_in_a_callback(ui):
    # A pressed button must not change the outcome: nothing runs in the branch.
    mock_streamlit.button.return_value = True

    ui.preset_buttons()

    mock_streamlit.button.assert_called_once()
    kwargs = mock_streamlit.button.call_args.kwargs
    assert kwargs["on_click"] == ui._apply_preset_callback
    assert kwargs["args"] == ("Fast",)
    mock_streamlit.rerun.assert_not_called()


def test_callback_applies_only_the_preset_keys(ui):
    pm = ui.parameter_manager
    preset_key = f"{pm.topp_param_prefix}FeatureFinderMetabo:1:algorithm:common:noise_threshold_int"
    file_key = f"{pm.param_prefix}mzML-files"
    mock_streamlit.session_state[preset_key] = 1000.0
    mock_streamlit.session_state[file_key] = ["a.mzML"]

    ui._apply_preset_callback("Fast")

    assert preset_key not in mock_streamlit.session_state
    assert mock_streamlit.session_state[file_key] == ["a.mzML"]
    stored = json.loads(pm.params_file.read_text(encoding="utf-8"))
    assert stored["mzML-files"] == ["a.mzML"]
    assert stored["FeatureFinderMetabo"]["algorithm:common:noise_threshold_int"] == 500.0
    mock_streamlit.rerun.assert_not_called()
