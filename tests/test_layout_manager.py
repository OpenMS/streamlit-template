"""Tests for the layout manager's Streamlit-free part and its grid renderer."""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.layout_manager.layout import (
    apply_preset,
    clear_layout,
    load_layout,
    match_preset,
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

st.session_state["done"] = layout_editor(
    Path(st.session_state["path"]), {components!r}, [["table", "detail"]], key="ed"
)
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
    # A save reports itself once, so a dialog reruns the page only then
    assert at.session_state["done"] is True
    at.run()
    assert at.session_state["done"] is False

    # An invalid layout is refused
    at.session_state["ed"] = {"action": "save", "layout": [[["detail"]]], "side_by_side": False, "nonce": 2}
    at.run()
    assert load_layout(path) == ([[["plot"]]], False)
    assert at.session_state["done"] is False  # the dialog stays open on its message

    # Reset forgets it
    at.session_state["ed"] = {"action": "reset", "nonce": 3}
    at.run()
    assert load_layout(path) is None
    assert at.session_state["done"] is True
    assert Path(path).parent.exists()


_BUTTON_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager import layout_button, resolve_layout

path = Path(st.session_state["path"])
st.session_state["runs"] = st.session_state.get("runs", 0) + 1
layout_button(path, {components!r}, [["table", "detail"]], key="ed")
layout, _ = resolve_layout(path, {components!r}, [["table", "detail"]])
st.markdown(" | ".join(",".join(row) for row in layout[0]))
"""


def test_button_save_redraws_the_page(tmp_path):
    path = tmp_path / "viewer.json"
    at = AppTest.from_string(_BUTTON_APP.format(components=COMPONENTS))
    at.session_state["path"] = str(path)
    at.run()
    assert at.markdown[0].value == "table,detail"

    # Save in the open dialog: the page runs again and shows the new layout
    at.session_state["ed"] = {"action": "save", "layout": [[["plot"]]], "side_by_side": False, "nonce": 1}
    runs = at.session_state["runs"]
    at.button(key="ed_open").click().run()
    assert not at.exception
    assert load_layout(path) == ([[["plot"]]], False)
    assert at.session_state["runs"] == runs + 2  # the click, then the rerun after the save
    assert at.markdown[0].value == "plot"

    # A refused save does not rerun the page
    at.session_state["ed"] = {"action": "save", "layout": [[["detail"]]], "side_by_side": False, "nonce": 2}
    runs = at.session_state["runs"]
    at.button(key="ed_open").click().run()
    assert at.session_state["runs"] == runs + 1
    assert at.markdown[0].value == "plot"


_OPEN_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager import layout_button

layout_button(Path(st.session_state["path"]), {components!r}, [["table"]], key="ed", help_text="Arrange")
"""


def test_dialog_stays_open_until_saved(tmp_path):
    at = AppTest.from_string(_OPEN_APP.format(components=COMPONENTS))
    at.session_state["path"] = str(tmp_path / "viewer.json")
    at.run()
    assert [c.value for c in at.caption] == []
    at.button(key="ed_open").click().run()
    assert [c.value for c in at.caption] == ["Arrange"]
    # A rerun of the page the dialog did not ask for (a component on it) keeps it open
    at.run()
    assert [c.value for c in at.caption] == ["Arrange"]
    # Saving closes it
    at.session_state["ed"] = {"action": "save", "layout": [[["plot"]]], "side_by_side": False, "nonce": 1}
    at.run()
    assert not at.exception
    assert load_layout(tmp_path / "viewer.json") == ([[["plot"]]], False)
    at.run()
    assert [c.value for c in at.caption] == []


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


PRESETS = [
    {"name": "all", "label": "All", "layout": [["table", "detail"], ["plot"]]},
    {"name": "plots", "label": "Plots", "layout": [["plot"]], "help": "Only the plot."},
]


def test_match_and_apply_preset(tmp_path):
    path = tmp_path / "viewer.json"
    assert match_preset([[["table", "detail"], ["plot"]]], PRESETS, COMPONENTS) == "all"
    assert match_preset([[["plot"]], [["plot"]]], PRESETS, COMPONENTS) == "plots"
    assert match_preset([[["plot"]], [["table"]]], PRESETS, COMPONENTS) is None
    # Components the page does not offer are left out of both sides
    offered = [c for c in COMPONENTS if c["name"] != "plot"]
    assert match_preset([[["table", "detail"]]], PRESETS, offered) == "all"

    apply_preset(path, PRESETS[1]["layout"])
    assert load_layout(path) == ([[["plot"]]], False)
    # Experiments and side by side are kept
    save_layout(path, [[["table"]], [["table"]]], side_by_side=True)
    apply_preset(path, PRESETS[0]["layout"])
    assert load_layout(path) == ([PRESETS[0]["layout"]] * 2, True)


_PRESET_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager import layout_presets, resolve_layout

path = Path(st.session_state["path"])
shown = layout_presets(path, {components!r}, {presets!r}, [["table", "detail"], ["plot"]], key="view")
layout, _ = resolve_layout(path, {components!r}, [["table", "detail"], ["plot"]])
st.markdown(f"{{shown}}: " + " | ".join(",".join(row) for row in layout[0]))
"""


def test_preset_selector(tmp_path):
    path = tmp_path / "viewer.json"
    at = AppTest.from_string(_PRESET_APP.format(components=COMPONENTS, presets=PRESETS))
    at.session_state["path"] = str(path)
    at.run()
    assert not at.exception
    # The default layout is the first preset, and Custom is not offered
    assert at.markdown[0].value == "all: table,detail | plot"
    assert at.radio(key="view").options == ["All", "Plots"]
    # Picking a preset stores it
    at.radio(key="view").set_value("plots").run()
    assert at.markdown[0].value == "plots: plot"
    assert load_layout(path) == ([[["plot"]]], False)
    # A layout saved in the editor shows as Custom
    save_layout(path, [[["table"]]])
    at.run()
    assert at.markdown[0].value == "None: table"
    assert at.session_state["view"] == "_custom"
    assert at.radio(key="view").options == ["All", "Plots", "Custom"]


VIEWS = [
    {"name": "all", "label": "All", "layout": [["table", "detail"], ["plot"]]},
    {"name": "plots", "label": "Plots", "layout": [["plot"]]},
]
# The page's default is its first view
DEFAULT = [["table", "detail"], ["plot"]]


def test_views_round_trip(tmp_path):
    from src.layout_manager.layout import load_views, save_views, select_view, validate_views

    path = tmp_path / "viewer.json"
    state = load_views(path, COMPONENTS, VIEWS, DEFAULT)
    assert [v["name"] for v in state["views"]] == ["all", "plots"]
    assert state["current"] == "all"

    # A view of one's own, kept out of the bar, and a preset moved last
    state["views"] = [state["views"][1], state["views"][0],
                      {"name": "custom-1", "label": "Mine", "rows": [["table"]], "preset": False, "in_bar": False}]
    state["current"] = "custom-1"
    assert validate_views(state, COMPONENTS, VIEWS, DEFAULT) == ""
    save_views(path, state)
    again = load_views(path, COMPONENTS, VIEWS, DEFAULT)
    assert [(v["name"], v["in_bar"]) for v in again["views"]] == [("plots", True), ("all", True), ("custom-1", False)]
    assert again["current"] == "custom-1"
    # The current view is the layout resolve_layout reads
    assert resolve_layout(path, COMPONENTS, DEFAULT) == ([[["table"]]], False)

    assert select_view(path, "plots", COMPONENTS, VIEWS, DEFAULT)
    assert resolve_layout(path, COMPONENTS, DEFAULT) == ([[["plot"]]], False)
    assert not select_view(path, "nope", COMPONENTS, VIEWS, DEFAULT)

    # Refused: a duplicate label, an empty view, a missing preset
    bad = load_views(path, COMPONENTS, VIEWS, DEFAULT)
    bad["views"][2]["label"] = "All"
    assert validate_views(bad, COMPONENTS, VIEWS, DEFAULT)
    bad["views"][2].update(label="Mine", rows=[])
    assert validate_views(bad, COMPONENTS, VIEWS, DEFAULT)
    bad["views"] = bad["views"][1:]
    assert validate_views(bad, COMPONENTS, VIEWS, DEFAULT)


def test_legacy_layout_becomes_a_view(tmp_path):
    from src.layout_manager.layout import load_views

    path = tmp_path / "viewer.json"
    save_layout(path, [[["table"], ["plot"]]])
    state = load_views(path, COMPONENTS, VIEWS, DEFAULT)
    mine = next(v for v in state["views"] if not v["preset"])
    assert mine["label"] == "My layout" and mine["rows"] == [["table"], ["plot"]]
    assert state["current"] == mine["name"]


_BAR_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager import view_bar, resolve_layout

path = Path(st.session_state["path"])
clicks = st.session_state.setdefault("clicks", [])
current = view_bar(path, {components!r}, {presets!r}, {default!r}, key="vb",
                   actions=[{{"id": "x", "icon": "X", "help": "x", "on_click": lambda: clicks.append(1)}}])
layout, _ = resolve_layout(path, {components!r}, {default!r})
st.markdown(current + ":" + " | ".join(",".join(row) for row in layout[0]))
"""


def test_view_bar_pick_new_view_and_action(tmp_path):
    path = tmp_path / "viewer.json"
    at = AppTest.from_string(_BAR_APP.format(components=COMPONENTS, presets=VIEWS, default=DEFAULT))
    at.session_state["path"] = str(path)
    at.run()
    assert not at.exception
    assert at.markdown[0].value == "all:table,detail | plot"

    at.session_state["vb_bar"] = {"action": "pick", "view": "plots", "nonce": 1}
    at.run()
    assert at.markdown[0].value == "plots:plot"

    at.session_state["vb_bar"] = {"action": "button", "id": "x", "nonce": 2}
    at.run()
    assert at.session_state["clicks"] == [1]

    # + opens the editor on a copy of the current view; saving it makes it current
    at.session_state["vb_bar"] = {"action": "edit", "new_view": True, "nonce": 3}
    at.run()
    assert at.session_state["vb_dialog_new"] is True
    at.session_state["vb_editor"] = {
        "action": "save", "nonce": 4, "current": "custom-1", "experiments": 1, "side_by_side": False,
        "views": [{"name": "all", "in_bar": True}, {"name": "plots", "in_bar": True},
                  {"name": "custom-1", "label": "Plots (copy)", "rows": [["table"]], "in_bar": True}]}
    at.run()
    assert not at.exception
    assert at.session_state["vb_dialog_open"] is False
    assert at.markdown[0].value == "custom-1:table"


_STATE_APP = """
import sys, types
import streamlit as st

class StateManager:
    def __init__(self, key):
        self.key = key
        st.session_state.setdefault(key, {{"selections": {{}}}})

sys.modules["openms_insight"] = types.SimpleNamespace(StateManager=StateManager)
from src.layout_manager import experiment_state

a = experiment_state("v", 0, st.session_state["dataset"])
b = experiment_state("v", 1, "other")
if st.session_state.get("pick"):
    st.session_state[a.key]["selections"]["protein"] = "P1"
st.markdown(f"{{a.key}} {{b.key}} {{st.session_state[a.key]['selections']}}")
"""


def test_experiment_state_kept_until_dataset_changes(monkeypatch):
    import sys
    # The app swaps in a stand-in for openms-insight; put the real one back afterwards
    monkeypatch.setitem(sys.modules, "openms_insight", sys.modules.get("openms_insight"))
    at = AppTest.from_string(_STATE_APP.format())
    at.session_state["dataset"] = "run1"
    at.session_state["pick"] = True
    at.run()
    at.session_state["pick"] = False
    at.run()
    assert at.markdown[0].value == "v_state_0 v_state_1 {'protein': 'P1'}"
    at.session_state["dataset"] = "run2"
    at.run()
    assert at.markdown[0].value == "v_state_0 v_state_1 {}"


class _FakeStateManager:
    """The part of openms-insight's StateManager experiment_state relies on."""

    def __init__(self, session_key):
        import streamlit as st
        self._key = session_key
        st.session_state.setdefault(session_key, {"selections": {}})

    @property
    def _sel(self):
        import streamlit as st
        return st.session_state[self._key]["selections"]

    def get_selection(self, identifier):
        return self._sel.get(identifier)

    def set_selection(self, identifier, value):
        self._sel[identifier] = value
        return True

    def clear_selection(self, identifier):
        return self._sel.pop(identifier, None) is not None

    def get_all_selections(self):
        return dict(self._sel)

    def get_state_for_vue(self):
        return {"id": 1, **self._sel}

    def update_from_vue(self, vue_state):
        vue_state = {k: v for k, v in vue_state.items() if k != "id"}
        self._sel.update(vue_state)
        return bool(vue_state)


def test_private_identifiers_are_kept_apart(monkeypatch):
    import sys
    import types
    from unittest.mock import patch

    from src.layout_manager import experiment_state

    monkeypatch.setitem(sys.modules, "openms_insight", types.SimpleNamespace(StateManager=_FakeStateManager))
    session = {}
    with patch("src.layout_manager.ui.st") as fake_st:
        fake_st.session_state = session
        with patch("streamlit.session_state", session):
            search = experiment_state("v", 0, private=["identification"], owner="search")
            rescored = experiment_state("v", 0, private=["identification"], owner="rescored")
            plain = experiment_state("v", 0)
            search.update_from_vue({"id": 1, "spectrum": 7, "identification": 3})
            rescored.set_selection("identification", 9)
            # The spectrum is shared, each table keeps its own row
            assert plain.get_selection("spectrum") == 7
            assert rescored.get_selection("spectrum") == 7
            assert search.get_selection("identification") == 3
            assert rescored.get_state_for_vue() == {"id": 1, "spectrum": 7, "identification": 9}
            assert plain.get_all_selections() == {"spectrum": 7}


def test_requires_one_of_several():
    components = COMPONENTS + [
        {"name": "go", "label": "GO", "group": "Plots", "requires": ["table", "plot"],
         "requires_label": "a table or the plot"},
    ]
    assert validate_layout([[["go", "plot"]]], components) == ""
    assert validate_layout([[["table"], ["go"]]], components) == ""
    assert "needs a table or the plot" in validate_layout([[["go"]]], components)


_DEFAULT_VIEW_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager import view_bar

st.markdown(view_bar(Path(st.session_state["path"]), {components!r}, {presets!r}, {default!r},
                     key="vb", default_view="plots"))
"""


def test_default_view_until_one_is_picked(tmp_path):
    path = tmp_path / "viewer.json"
    at = AppTest.from_string(_DEFAULT_VIEW_APP.format(components=COMPONENTS, presets=VIEWS, default=DEFAULT))
    at.session_state["path"] = str(path)
    at.run()
    assert at.markdown[0].value == "plots"
    at.session_state["vb_bar"] = {"action": "pick", "view": "all", "nonce": 1}
    at.run()
    assert at.markdown[0].value == "all"


# ---- Views and components the shown data was not processed for ----

NEEDS = COMPONENTS + [
    {"name": "ids", "label": "Identifications", "group": "Tables", "needs": "identification"},
    {"name": "volcano", "label": "Volcano", "group": "Plots", "needs": ["identification", "comparison"]},
]
ANALYSES = {"identification": {"label": "Identification", "help": "Search a protein database."},
            "comparison": "Comparison"}


def test_missing_analyses():
    from src.layout_manager.layout import analysis_label, join_labels, missing_analyses, needs

    assert needs(NEEDS[-1]) == ["identification", "comparison"]
    assert needs(NEEDS[0]) == []
    assert missing_analyses([["table", "ids"], ["volcano"]], NEEDS, set()) == ["identification", "comparison"]
    assert missing_analyses([["volcano"]], NEEDS, {"identification"}) == ["comparison"]
    assert missing_analyses([["table", "plot"]], NEEDS, set()) == []
    assert missing_analyses([["ids"]], NEEDS, None) == []  # None: everything is there
    assert analysis_label("identification", ANALYSES) == "Identification"
    assert analysis_label("comparison", ANALYSES) == "Comparison"
    assert join_labels(["A", "B", "C"]) == "A, B and C"


_NEEDS_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager import render_layout, request_analysis, view_bar, resolve_layout

picked = st.session_state.setdefault("picked", [])
available = set(st.session_state.get("available", []))
current = view_bar(Path(st.session_state["path"]), {components!r}, {views!r}, {default!r}, key="vb",
                   available=available, analyses={analyses!r},
                   unavailable_options=lambda missing, view: [
                       {{"label": "Run identification", "on_click": lambda: picked.append((missing, view and view["name"]))}}])
layout, _ = resolve_layout(Path(st.session_state["path"]), {components!r}, {default!r})
st.markdown("current:" + current)
render_layout(layout[0], {{n: (lambda n=n: st.markdown("drawn:" + n)) for n in ["table", "detail", "plot", "ids", "volcano"]}},
              components={components!r}, available=available, analyses={analyses!r},
              on_missing=lambda missing, name: request_analysis("vb", missing, component=name), key="grid")
"""

NEEDS_VIEWS = VIEWS + [{"name": "ids", "label": "IDs", "layout": [["table", "ids"]]}]


def test_unavailable_view_opens_the_dialog_instead_of_switching(tmp_path):
    at = AppTest.from_string(_NEEDS_APP.format(components=NEEDS, views=NEEDS_VIEWS, default=DEFAULT,
                                               analyses=ANALYSES))
    at.session_state["path"] = str(tmp_path / "viewer.json")
    at.run()
    assert not at.exception

    at.session_state["vb_bar"] = {"action": "unavailable", "view": "ids", "nonce": 1}
    at.run()
    assert not at.exception
    assert "current:all" in [m.value for m in at.markdown]  # the view did not change
    texts = " ".join(m.value for m in at.markdown)
    assert "The view **IDs** needs Identification" in texts
    assert "Search a protein database." in texts

    at.button(key="vb_missing_option_0").click().run()
    assert at.session_state["picked"] == [(["identification"], "ids")]
    assert "vb_missing" not in at.session_state


def test_component_draws_a_note_where_its_analysis_is_missing(tmp_path):
    path = tmp_path / "viewer.json"
    at = AppTest.from_string(_NEEDS_APP.format(components=NEEDS, views=NEEDS_VIEWS, default=DEFAULT,
                                               analyses=ANALYSES))
    at.session_state["path"] = str(path)
    at.session_state["vb_bar"] = {"action": "pick", "view": "ids", "nonce": 1}
    # Picking works while the run has identification ...
    at.session_state["available"] = ["identification"]
    at.run()
    drawn = [m.value for m in at.markdown]
    assert "current:ids" in drawn and "drawn:ids" in drawn

    # ... and a run without it draws the note with a button that opens the dialog
    at.session_state["available"] = []
    at.run()
    texts = " ".join(m.value for m in at.markdown)
    assert "drawn:ids" not in texts
    assert "Needs Identification, which this run was not processed with." in texts
    at.button(key="grid_missing_ids").click().run()
    assert at.session_state["vb_missing"]["component"] == "ids"
