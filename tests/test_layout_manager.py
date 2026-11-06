"""Tests for the layout manager's Streamlit-free part and its grid renderer."""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.layout_manager.layout import (
    clear_layout,
    load_layout,
    resolve_layout,
    save_layout,
    validate_layout,
)

COMPONENTS = [
    {"name": "table", "label": "Table", "group": "Tables"},
    {"name": "detail", "label": "Detail", "group": "Tables", "requires": "table"},
    {"name": "plot", "label": "Plot", "group": "Plots"},
]


def test_validate_layout():
    assert validate_layout([[["table", "detail"], ["plot"]]], COMPONENTS) == ""
    assert "needs Table" in validate_layout([[["detail"]]], COMPONENTS)
    assert "twice" in validate_layout([[["plot"], ["plot"]]], COMPONENTS)
    assert "Unknown" in validate_layout([[["nope"]]], COMPONENTS)
    assert "at most 3" in validate_layout([[["table", "detail", "plot", "plot"]]], COMPONENTS)
    assert "empty row" in validate_layout([[["plot"], []]], COMPONENTS)
    assert validate_layout([], COMPONENTS) == "Empty layout"
    assert "At most 1" in validate_layout([[["plot"]], [["plot"]]], COMPONENTS, max_experiments=1)


def test_save_load_clear(tmp_path):
    path = tmp_path / "layouts" / "viewer.json"
    assert load_layout(path) is None
    save_layout(path, [[["plot"]], [["table"]]], side_by_side=True)
    assert load_layout(path) == ([[["plot"]], [["table"]]], True)
    # side by side only applies to two experiments
    save_layout(path, [[["plot"]]], side_by_side=True)
    assert load_layout(path) == ([[["plot"]]], False)
    clear_layout(path)
    assert load_layout(path) is None
    clear_layout(path)  # no error when nothing is stored


def test_load_ignores_corrupt_file(tmp_path):
    path = tmp_path / "viewer.json"
    path.write_text("{not json")
    assert load_layout(path) is None


def test_resolve_layout(tmp_path):
    path = tmp_path / "viewer.json"
    default = [["table", "detail"], ["plot"]]
    assert resolve_layout(path, COMPONENTS, default) == ([default], False)

    # Components that are not offered any more are dropped, empty rows too
    path.write_text(json.dumps({"layout": [[["gone"], ["plot", "gone"]]], "side_by_side": False}))
    assert resolve_layout(path, COMPONENTS, default) == ([[["plot"]]], False)

    # An experiment with nothing left falls back to the default
    path.write_text(json.dumps({"layout": [[["gone"]], [["plot"]]], "side_by_side": True}))
    assert resolve_layout(path, COMPONENTS, default) == ([default, [["plot"]]], True)

    # The default itself is filtered by the catalog
    assert resolve_layout(tmp_path / "none.json", COMPONENTS[2:], default) == ([[["plot"]]], False)


_GRID_APP = """
import streamlit as st
from src.layout_manager import render_layout

render_layout(
    [["a", "b"], ["missing"]],
    {"a": lambda: st.markdown("cell a"), "b": lambda: st.markdown("cell b")},
    {"missing": "Missing component"},
)
"""


def test_render_layout():
    at = AppTest.from_string(_GRID_APP).run()
    assert not at.exception
    assert [m.value for m in at.markdown] == ["cell a", "cell b"]
    assert "Missing component is not available here." in at.info[0].value


_EDITOR_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager import layout_editor

layout_editor(Path(st.session_state["path"]), {components!r}, [["table", "detail"]], key="ed")
"""


def test_editor_saves_submitted_layout(tmp_path):
    path = tmp_path / "viewer.json"
    at = AppTest.from_string(_EDITOR_APP.format(components=COMPONENTS))
    at.session_state["path"] = str(path)
    at.run()
    assert not at.exception
    assert load_layout(path) is None

    # What the browser sends on Save
    at.session_state["ed"] = {"action": "save", "layout": [[["plot"]]], "side_by_side": False, "nonce": 1}
    at.run()
    assert load_layout(path) == ([[["plot"]]], False)

    # An invalid layout is refused
    at.session_state["ed"] = {"action": "save", "layout": [[["detail"]]], "side_by_side": False, "nonce": 2}
    at.run()
    assert load_layout(path) == ([[["plot"]]], False)

    # Reset forgets it
    at.session_state["ed"] = {"action": "reset", "nonce": 3}
    at.run()
    assert load_layout(path) is None
    assert Path(path).parent.exists()


_EXPERIMENTS_APP = """
import streamlit as st
from src.layout_manager import render_experiments

picked = render_experiments(
    st.session_state["layout"], st.session_state["side_by_side"],
    {"r1": "Run 1", "r2": "Run 2", "c1": "Comparison"},
    lambda dataset, index: {"plot": lambda: st.markdown(f"plot {dataset} {index}")},
    key="viewer",
    buttons=lambda i: st.button("Edit layout") if i == 0 else None,
)
st.session_state["picked"] = picked
"""


def test_render_experiments_one_selector_per_experiment():
    at = AppTest.from_string(_EXPERIMENTS_APP)
    at.session_state["layout"] = [[["plot"]], [["plot"]], [["plot"]]]
    at.session_state["side_by_side"] = False
    at.run()
    assert not at.exception
    # Experiment n starts on the n-th dataset; one button, next to the first selector
    assert [m.value for m in at.markdown] == ["plot r1 0", "plot r2 1", "plot c1 2"]
    assert len(at.selectbox) == 3 and len(at.button) == 1
    assert at.selectbox[0].options == ["Run 1", "Run 2", "Comparison"]

    # Picking another dataset redraws only that experiment, and the pick sticks
    at.selectbox[1].set_value("c1").run()
    assert [m.value for m in at.markdown] == ["plot r1 0", "plot c1 1", "plot c1 2"]
    at.run()
    assert at.session_state["picked"] == ["r1", "c1", "c1"]


def test_render_experiments_side_by_side_and_empty():
    at = AppTest.from_string(_EXPERIMENTS_APP)
    at.session_state["layout"] = [[["plot"]], [["plot"]]]
    at.session_state["side_by_side"] = True
    at.run()
    assert not at.exception
    assert len(at.columns) >= 2
    assert [m.value for m in at.markdown] == ["plot r1 0", "plot r2 1"]

    empty = AppTest.from_string(
        "import streamlit as st\n"
        "from src.layout_manager import render_experiments\n"
        "st.session_state['picked'] = render_experiments([[['plot']]], False, {}, lambda d, i: {}, key='v')\n"
    ).run()
    assert not empty.exception and empty.session_state["picked"] == [None]
