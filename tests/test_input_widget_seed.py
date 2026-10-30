"""
``StreamlitUI.input_widget()`` must keep a seeded value across reruns.

On Streamlit < 1.50 a widget's initial-value argument is hashed into its
element id. Passing the persisted value only on the first render gave the
second render another id, and the widget restarted from its built-in default:
a "Generate Decoy Database" checkbox seeded True from params.json turned False
on the next rerun (e.g. after an mzML file was selected), and the saved value
followed. Runs the real Streamlit through AppTest.
"""
import json
import os

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app(workflow_dir: str, project_root: str) -> None:
    import sys
    from pathlib import Path

    import streamlit as st

    sys.path.insert(0, project_root)
    from src.workflow.ParameterManager import ParameterManager
    from src.workflow.StreamlitUI import StreamlitUI

    ui = object.__new__(StreamlitUI)
    ui.parameter_manager = ParameterManager(Path(workflow_dir))
    ui.params = ui.parameter_manager.get_parameters_from_json()
    ui.input_widget("flag", default=False, name="Flag", widget_type="checkbox")
    ui.input_widget("choice", default="b", name="Choice", widget_type="selectbox", options=["a", "b", "c"])
    ui.input_widget("many", default=[], name="Many", widget_type="multiselect", options=["x", "y", "z"])
    ui.input_widget("n", default=1, name="N", widget_type="number")
    st.button("rerun")


def test_seeded_values_survive_reruns(tmp_path):
    workflow_dir = tmp_path / "wf"
    workflow_dir.mkdir()
    (workflow_dir / "params.json").write_text(
        json.dumps({"flag": True, "choice": "c", "many": ["y", "gone"], "n": 7}),
        encoding="utf-8",
    )
    at = AppTest.from_function(_app, args=(str(workflow_dir), PROJECT_ROOT)).run()
    for _ in range(3):
        assert not at.exception
        assert at.checkbox[0].value is True
        assert at.selectbox[0].value == "c"
        # A saved value that is no longer an option is dropped, not an error.
        assert at.multiselect[0].value == ["y"]
        assert at.number_input[0].value == 7
        at.button[0].click().run()


def test_user_changes_are_kept(tmp_path):
    workflow_dir = tmp_path / "wf"
    workflow_dir.mkdir()
    (workflow_dir / "params.json").write_text(json.dumps({"flag": True}), encoding="utf-8")
    at = AppTest.from_function(_app, args=(str(workflow_dir), PROJECT_ROOT)).run()
    at.checkbox[0].uncheck().run()
    at.multiselect[0].select("x").run()
    at.button[0].click().run()
    assert at.checkbox[0].value is False
    assert at.multiselect[0].value == ["x"]
