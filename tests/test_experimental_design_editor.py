"""
The experimental design table keeps every edit: after an edit is saved, the
next edit must not be lost (a condition typed and confirmed with Tab or Enter
vanished on every second edit).
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402

from src.workflow.ExperimentalDesign import load_design, save_design  # noqa: E402


def _design_app(workflow_dir, files):
    def app(workflow_dir, files):
        from pathlib import Path
        from types import SimpleNamespace

        from src.workflow.StreamlitUI import StreamlitUI

        ui = SimpleNamespace(
            workflow_dir=Path(workflow_dir),
            params={"mzML-files": files},
            parameter_manager=SimpleNamespace(param_prefix="wf-param-"),
        )
        StreamlitUI.experimental_design(ui, "mzML-files")

    return AppTest.from_function(app, args=(str(workflow_dir), files))


def _editor(at):
    editors = [e for e in at.get("arrow_data_frame") if e.proto.editing_mode]
    assert len(editors) == 1
    return editors[0].proto


def test_saved_edit_does_not_replace_the_editor(tmp_path):
    wf = tmp_path / "wf"
    wf.mkdir()
    files = [str(tmp_path / f"{n}.mzML") for n in ("a", "b", "c")]
    at = _design_app(wf, files).run()
    assert not at.exception
    first = _editor(at).id

    # What the run after an edit leaves on disk: the design with that edit
    design = load_design(wf, files)
    design.loc[0, "condition"] = "ctrl"
    save_design(wf, design, files)

    at.run()
    assert not at.exception
    # Same editor: a new one (other data, other id) would drop the next edit
    assert _editor(at).id == first

