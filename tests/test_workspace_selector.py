"""
The local-mode workspace selector's ``on_change`` callback must not crash when
it fires without a readable ``chosen-workspace`` value.

Switching pages while a page is still loading can make Streamlit replay the
selectbox's value before its key is mapped again. The callback then fired, read
``st.session_state["chosen-workspace"]`` and raised ``KeyError`` in place of the
page. It now leaves the workspace unchanged when there is no value or the value
is the current workspace. AppTest cannot recreate the unmapped key, so this
test pins the path the guard must keep working: picking another workspace.
"""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def _workspace_selectbox(at):
    return next(
        s for s in at.sidebar.selectbox if s.label == "choose existing workspace"
    )


@pytest.fixture
def app(tmp_path):
    at = AppTest.from_file("content/file_upload.py")
    with open("settings.json", "r") as f:
        at.session_state.settings = json.load(f)
    at.session_state.settings["test"] = True
    # Keep the workspaces this test creates out of the real workspaces folder.
    at.session_state.settings["workspaces_dir"] = str(tmp_path)
    at.secrets["workspace"] = "test"
    at.run(timeout=30)
    assert not at.exception
    return at


@pytest.fixture
def other_workspace(app):
    workspaces_dir = Path(app.session_state.workspace).parent
    path = workspaces_dir / "test-workspace-selector-other"
    path.mkdir()
    return path.name


def test_picking_another_workspace_switches_to_it(app, other_workspace):
    app.run(timeout=30)
    _workspace_selectbox(app).set_value(other_workspace).run(timeout=30)
    assert not app.exception
    assert app.query_params["workspace"] == [other_workspace]
