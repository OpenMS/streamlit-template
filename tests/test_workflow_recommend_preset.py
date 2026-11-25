"""The detection preset the example workflow suggests for the selected files."""
import json
from pathlib import Path

from src.Workflow import Workflow


def _wf():
    return object.__new__(Workflow)


def test_no_files_no_suggestion():
    assert _wf().recommend_preset([]) == (None, "")


def test_few_files_balanced():
    preset, why = _wf().recommend_preset(["a.mzML", "b.mzML"])
    assert preset == "Metabolomics Default"
    assert "2 files" in why and "Balanced" in why


def test_many_files_fast():
    files = [f"{i}.mzML" for i in range(Workflow.MANY_FILES)]
    preset, why = _wf().recommend_preset(files)
    assert preset == "Fast Analysis"
    assert "Fast" in why


def test_every_offered_preset_exists():
    presets = json.loads(Path("presets.json").read_text())["topp-workflow"]
    assert set(Workflow.DETECTION_PRESETS) <= set(presets)


def test_display_stale_only_when_preset_changed(monkeypatch):
    import streamlit as st

    wf = _wf()
    monkeypatch.setattr(Workflow, "current_preset", lambda self: None)
    st.session_state.pop(Workflow.SHOWN_PRESET_KEY, None)
    assert not wf.preset_display_stale()  # box not drawn yet
    st.session_state[Workflow.SHOWN_PRESET_KEY] = None
    assert not wf.preset_display_stale()  # an unrelated edit
    st.session_state[Workflow.SHOWN_PRESET_KEY] = "Metabolomics Default"
    assert wf.preset_display_stale()  # the edit changed a preset value
    st.session_state.pop(Workflow.SHOWN_PRESET_KEY, None)
