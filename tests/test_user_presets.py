"""
Tests for user-saved presets and the "changed since preset" status.

A user preset is a snapshot of the workflow's settings, saved in
<workflow_dir>/user-presets.json. It leaves out input file selections and
max_threads, and applying it restores every saved setting (TOPP parameters it
did not hold go back to their defaults). The file also records the preset
applied last, so the parameter page can say whether the settings still match it.
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Same sys.modules mocking as tests/test_parameter_presets.py
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


BUILTIN = {
    "test-workflow": {
        "Fast": {
            "_description": "Fewer iterations",
            "ToolA": {"param1": 10.0},
        }
    }
}


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
    (workflow_dir / "input-files" / "mzML-files").mkdir(parents=True)
    manager = ParameterManager(workflow_dir)
    write(manager, {
        "mzML-files": ["a.mzML"],
        "max_threads": 8,
        "my-cutoff": 0.5,
        "_defaults": {"ToolA": {"param1": 1.0}},
        "ToolA": {"param1": 5.0, "param2": "x"},
        "ToolB": {"param3": 3},
    })
    return manager


def write(manager, params):
    manager.params_file.write_text(json.dumps(params), encoding="utf-8")


def stored(manager):
    return json.loads(manager.params_file.read_text(encoding="utf-8"))


def test_snapshot_leaves_out_files_threads_and_reserved_keys(pm):
    snapshot = pm.snapshot_preset()
    assert snapshot == {
        "_general": {"my-cutoff": 0.5},
        "ToolA": {"param1": 5.0, "param2": "x"},
        "ToolB": {"param3": 3},
    }


def test_save_and_list_user_preset(pm):
    assert pm.save_user_preset("My run", "Tuned for my samples")
    assert pm.get_user_preset_names() == ["My run"]
    assert pm.get_preset_description("My run") == "Tuned for my samples"
    # Saving makes it the current preset, unchanged
    assert pm.applied_preset_status() == ("My run", False)


@pytest.mark.parametrize("name", ["", "   ", "Fast", "_hidden"])
def test_save_rejects_empty_builtin_and_reserved_names(pm, name):
    assert not pm.save_user_preset(name)
    assert pm.get_user_preset_names() == []


def test_applying_user_preset_restores_the_snapshot(pm):
    pm.save_user_preset("My run")
    # Change things after saving: a new TOPP value, a changed one, another file
    write(pm, {
        "mzML-files": ["b.mzML"],
        "max_threads": 2,
        "my-cutoff": 0.9,
        "_defaults": {"ToolA": {"param1": 1.0}},
        "ToolA": {"param1": 7.0, "param2": "x", "param4": True},
        "ToolB": {"param3": 3},
    })
    topp_key = f"{pm.topp_param_prefix}ToolA:1:param4"
    file_key = f"{pm.param_prefix}mzML-files"
    mock_streamlit.session_state[topp_key] = True
    mock_streamlit.session_state[file_key] = ["b.mzML"]
    assert pm.applied_preset_status() == ("My run", True)

    assert pm.apply_preset("My run")

    params = stored(pm)
    assert params["ToolA"] == {"param1": 5.0, "param2": "x"}  # param4 back to default
    assert params["my-cutoff"] == 0.5
    # Files, threads and _defaults are not part of a preset
    assert params["mzML-files"] == ["b.mzML"]
    assert params["max_threads"] == 2
    assert params["_defaults"] == {"ToolA": {"param1": 1.0}}
    assert topp_key not in mock_streamlit.session_state
    assert mock_streamlit.session_state[file_key] == ["b.mzML"]
    assert pm.applied_preset_status() == ("My run", False)


def test_builtin_preset_status_checks_only_its_own_values(pm):
    assert pm.apply_preset("Fast")
    assert pm.applied_preset_status() == ("Fast", False)

    # A setting the preset does not name may change freely
    params = stored(pm)
    params["ToolB"]["param3"] = 99
    write(pm, params)
    assert pm.applied_preset_status() == ("Fast", False)

    params["ToolA"]["param1"] = 11.0
    write(pm, params)
    assert pm.applied_preset_status() == ("Fast", True)


def test_status_tolerates_number_and_list_forms(pm):
    pm.save_user_preset("Mine")
    params = stored(pm)
    params["ToolB"]["param3"] = 3.0
    write(pm, params)
    assert pm.applied_preset_status() == ("Mine", False)
    assert ParameterManager._same_value(["a", "b"], "a\nb")


def test_delete_and_forget(pm):
    pm.save_user_preset("Mine")
    assert pm.delete_user_preset("Mine")
    assert not pm.delete_user_preset("Mine")
    assert pm.get_user_preset_names() == []
    assert pm.applied_preset_status() == (None, False)

    pm.apply_preset("Fast")
    pm.forget_applied_preset()
    assert pm.applied_preset_status() == (None, False)


def test_no_status_without_a_preset_file(pm):
    assert pm.applied_preset_status() == (None, False)
    assert pm.get_user_preset_names() == []


def test_unreadable_user_preset_file_is_treated_as_empty(pm):
    pm.user_presets_file.write_text("{not json", encoding="utf-8")
    assert pm.get_user_preset_names() == []
    assert pm.applied_preset_status() == (None, False)


@pytest.mark.parametrize("content", ["{not json", b"\xff\xfe{}", '{"presets": []}'])
def test_unreadable_file_is_never_overwritten(pm, content):
    """A failed read must not turn into an empty state written over the saved presets."""
    if isinstance(content, bytes):
        pm.user_presets_file.write_bytes(content)
    else:
        pm.user_presets_file.write_text(content, encoding="utf-8")
    before = pm.user_presets_file.read_bytes()
    params_before = pm.params_file.read_bytes()

    assert not pm.save_user_preset("Mine")
    assert not pm.delete_user_preset("Mine")
    assert not pm.apply_preset("Fast")
    pm.forget_applied_preset()

    assert pm.user_presets_file.read_bytes() == before
    assert pm.params_file.read_bytes() == params_before


def test_malformed_entries_are_dropped(pm):
    pm.user_presets_file.write_text(json.dumps({
        "presets": {
            "ok": {"ToolA": {"param1": 2.0}, "_general": "oops"},
            "not-a-dict": "oops",
        },
        "applied": ["not", "a", "name"],
    }), encoding="utf-8")
    assert pm.get_user_preset_names() == ["ok"]
    assert pm.applied_preset_status() == (None, False)
    assert pm.apply_preset("ok")
    assert stored(pm)["ToolA"] == {"param1": 2.0}
