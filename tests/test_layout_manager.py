"""Tests for the layout manager's Streamlit-free part and its grid renderer."""

import pytest

import json
import os
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


def test_assistant_view_is_read_only_in_the_editor(tmp_path):
    from src.layout_manager.layout import load_views, save_views

    path = tmp_path / "viewer.json"
    state = load_views(path, COMPONENTS, VIEWS, DEFAULT)
    state["views"].append({"name": "custom-1", "label": "Assistant view", "rows": [["plot"]], "preset": False,
                           "in_bar": True, "by": "assistant"})
    save_views(path, state)
    at = AppTest.from_string(_BAR_APP.format(components=COMPONENTS, presets=VIEWS, default=DEFAULT))
    at.session_state["path"] = str(path)
    at.run()
    # Sent like a ready-made view (just its name), or changed by hand: its label and rows stay
    for nonce, sent in ((2, {"name": "custom-1", "in_bar": False}),
                        (4, {"name": "custom-1", "label": "Changed", "rows": [["table"]], "in_bar": True})):
        at.session_state["vb_bar"] = {"action": "edit", "nonce": nonce - 1}
        at.run()
        at.session_state["vb_editor"] = {
            "action": "save", "nonce": nonce, "current": "all", "experiments": 1, "side_by_side": False,
            "views": [{"name": "all", "in_bar": True}, {"name": "plots", "in_bar": True}, sent]}
        at.run()
        assert not at.exception
        view = next(v for v in load_views(path, COMPONENTS, VIEWS, DEFAULT)["views"] if v["name"] == "custom-1")
        assert (view["label"], view["rows"], view["by"]) == ("Assistant view", [["plot"]], "assistant")
        assert view["in_bar"] is sent["in_bar"]


def test_duplicate_keeps_the_defaults_of_its_source(tmp_path):
    from src.layout_manager.layout import load_views, save_views

    path = tmp_path / "viewer.json"
    defaults = [{"selection": {"protein": "P1"}, "zoom": {"plot": {"x": [1.0, 2.0]}}}]
    state = load_views(path, COMPONENTS, VIEWS, DEFAULT)
    state["views"].append({"name": "custom-1", "label": "Assistant view", "rows": [["plot"]], "preset": False,
                           "in_bar": True, "by": "assistant", "defaults": defaults})
    save_views(path, state)
    at = AppTest.from_string(_BAR_APP.format(components=COMPONENTS, presets=VIEWS, default=DEFAULT))
    at.session_state["path"] = str(path)
    at.run()
    at.session_state["vb_bar"] = {"action": "edit", "nonce": 1}
    at.run()
    # Duplicate to edit: a new view whose source is named, with no defaults of its own in the payload
    at.session_state["vb_editor"] = {
        "action": "save", "nonce": 2, "current": "custom-2", "experiments": 1, "side_by_side": False,
        "views": [{"name": "all", "in_bar": True}, {"name": "plots", "in_bar": True},
                  {"name": "custom-1", "in_bar": True},
                  {"name": "custom-2", "label": "Assistant view (copy)", "rows": [["plot"]], "in_bar": True,
                   "copy_of": "custom-1"}]}
    at.run()
    assert not at.exception
    views = {v["name"]: v for v in load_views(path, COMPONENTS, VIEWS, DEFAULT)["views"]}
    assert views["custom-2"]["defaults"] == defaults
    assert "by" not in views["custom-2"]
    assert views["custom-1"]["defaults"] == defaults



def test_duplicate_in_the_editor_sends_its_source(tmp_path):
    """The editor's own Save carries ``copy_of``, so the server can copy the defaults."""
    sync_api = pytest.importorskip("playwright.sync_api")
    import json
    from pathlib import Path
    from src.layout_manager.layout import load_views

    page_file = Path(__file__).parent.parent / "src" / "layout_manager" / "frontend" / "index.html"
    views = load_views(tmp_path / "viewer.json", COMPONENTS, VIEWS, DEFAULT)["views"]
    views.append({"name": "custom-1", "label": "Assistant view", "rows": [["plot"]], "preset": True,
                  "in_bar": True, "by": "assistant"})
    args = {"components": COMPONENTS, "default_layout": DEFAULT, "saved_layout": None, "side_by_side": False,
            "views": views, "current": "custom-1", "experiments": 1, "fresh": None, "fresh_from": None,
            "max_experiments": 1, "max_columns": 3, "revision": "0-0", "server_error": None,
            "target": "the Viewer", "experiment_label": "Experiment"}
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        except Exception as exc:  # no browser on this machine
            pytest.skip(f"no Chromium: {exc}")
        page = browser.new_page()
        page.add_init_script("""window.__sent = [];
            window.addEventListener('message', e => {
              if (e.data && e.data.type === 'streamlit:setComponentValue') window.__sent.push(e.data.value);
            });""")
        page.goto(page_file.as_uri())
        page.evaluate("a => window.postMessage({type: 'streamlit:render', args: a}, '*')", args)
        page.get_by_role("button", name="Duplicate to edit").click()
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_function("window.__sent.length > 0", timeout=5000)
        sent = page.evaluate("window.__sent")
        browser.close()
    saved = json.loads(json.dumps(sent[-1]))
    copies = [v for v in saved["views"] if v["name"] not in {"all", "plots", "custom-1"}]
    assert len(copies) == 1 and copies[0]["copy_of"] == "custom-1"


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

    # ... and a run without it does not show the locked view: the first view it can fill instead
    at.session_state["available"] = []
    at.run()
    drawn = [m.value for m in at.markdown]
    assert "current:all" in drawn and "drawn:ids" not in drawn


def test_component_draws_a_note_where_no_view_can_be_filled(tmp_path):
    only_ids = [{"name": "ids", "label": "IDs", "layout": [["table", "ids"]]}]
    at = AppTest.from_string(_NEEDS_APP.format(components=NEEDS, views=only_ids, default=[["table", "ids"]],
                                               analyses=ANALYSES))
    at.session_state["path"] = str(tmp_path / "viewer.json")
    at.session_state["available"] = []
    at.run()
    texts = " ".join(m.value for m in at.markdown)
    assert "current:ids" in texts and "drawn:table" in texts and "drawn:ids" not in texts
    assert "Needs Identification, which this run was not processed with." in texts
    at.button(key="grid_missing_ids").click().run()
    assert at.session_state["vb_missing"]["component"] == "ids"


# --- Zoom and selection kept with a view -------------------------------------


def test_capture_and_clean_defaults():
    from src.layout_manager.layout import capture_defaults, clean_defaults, has_defaults, zoom_identifier

    selections = {
        "protein": "P1",
        "row@table": 3,
        "table_page": {"page": 2},            # pagination is never kept
        "spectrum": None,                      # nothing selected
        zoom_identifier("plot"): {"x": [900, 400]},
        zoom_identifier("map"): {"xRange": [1, 2], "yRange": [-1, -1]},
        zoom_identifier("other"): {"xRange": [-1, -1], "yRange": [-1, -1]},
        "odd": {1, 2},                          # not JSON: left out
    }
    entry = capture_defaults(selections, dataset="run1")
    assert entry == {
        "dataset": "run1",
        "selection": {"protein": "P1", "row@table": 3},
        "zoom": {"plot": {"x": [400.0, 900.0]}, "map": {"x": [1.0, 2.0]}},
    }
    assert capture_defaults({"table_page": 1}) == {}

    cleaned = clean_defaults([entry, {}, {"selection": {"a_page": 1}, "zoom": {"p": {"x": [1, 1]}}}])
    assert cleaned == [entry]  # trailing entries without anything to apply are dropped
    assert clean_defaults([{}, entry]) == [{}, entry]
    assert len(clean_defaults([entry] * 9)) == 5
    assert clean_defaults("nope") == []
    assert has_defaults({"defaults": cleaned}) and not has_defaults({"defaults": [{}]})


def test_apply_and_compare_defaults():
    from src.layout_manager.layout import apply_defaults, differs_from_defaults

    class State:
        def __init__(self, sel):
            self.sel = dict(sel)

        def get_all_selections(self):
            return dict(self.sel)

        def get_selection(self, identifier):
            return self.sel.get(identifier)

        def set_selection(self, identifier, value):
            changed = self.sel.get(identifier) != value
            self.sel[identifier] = value
            return changed

        def clear_selection(self, identifier):
            return self.sel.pop(identifier, None) is not None

    entry = {"dataset": "run1", "selection": {"protein": "P1"}, "zoom": {"plot": {"x": [1.0, 2.0]}}}
    state = State({"protein": "P9", "peptide": "PEP", "zoom@map": {"x": [5, 6]}})
    assert differs_from_defaults(state.get_all_selections(), entry, "run1")
    assert apply_defaults(state, entry, "run1")
    # Saved values set, a zoom the view does not name back to the full view, the rest kept
    zoom = {"x": [1.0, 2.0], "xRange": [1.0, 2.0], "yRange": [-1, -1]}  # the Heatmap reads xRange/yRange
    assert state.sel == {"protein": "P1", "peptide": "PEP", "zoom@plot": zoom}
    assert not differs_from_defaults(state.get_all_selections(), entry, "run1")
    assert not apply_defaults(state, entry, "run1")

    # Another dataset shown: the zoom is applied, the selection is not
    other = State({"protein": "Q2"})
    apply_defaults(other, entry, "run2")
    assert other.sel == {"protein": "Q2", "zoom@plot": zoom}


def test_view_extras_and_defaults_round_trip(tmp_path):
    from src.layout_manager.layout import has_own_defaults, load_views, save_views, set_view_defaults

    path = tmp_path / "viewer.json"
    state = load_views(path, COMPONENTS, VIEWS, DEFAULT)
    state["views"].append({
        "name": "custom-1", "label": "Assistant view", "rows": [["plot"]], "preset": False, "in_bar": True,
        "by": "assistant", "runs": ["run1"], "explanation": ["One.", "Two."], "question": "Why?",
        "created": "2026-11-08T10:00:00", "unknown": "dropped",
        "defaults": [{"selection": {"protein": "P1", "x_page": 1}}],
    })
    save_views(path, state)
    view = next(v for v in load_views(path, COMPONENTS, VIEWS, DEFAULT)["views"] if v["name"] == "custom-1")
    assert view["by"] == "assistant" and view["runs"] == ["run1"] and view["question"] == "Why?"
    assert view["explanation"] == ["One.", "Two."] and view["created"] == "2026-11-08T10:00:00"
    assert "unknown" not in view
    assert view["defaults"] == [{"selection": {"protein": "P1"}}]

    assert not set_view_defaults(path, "nope", [{"selection": {"a": 1}}], COMPONENTS, VIEWS, DEFAULT)

    # A view the assistant made: the user's pin replaces its zoom and selection, removing it brings them back
    assert set_view_defaults(path, "custom-1", [{"zoom": {"plot": {"x": [3, 4]}}}], COMPONENTS, VIEWS, DEFAULT)
    view = next(v for v in load_views(path, COMPONENTS, VIEWS, DEFAULT)["views"] if v["name"] == "custom-1")
    assert view["defaults"] == [{"zoom": {"plot": {"x": [3.0, 4.0]}}}]
    assert has_own_defaults(view)
    assert set_view_defaults(path, "custom-1", None, COMPONENTS, VIEWS, DEFAULT)
    view = next(v for v in load_views(path, COMPONENTS, VIEWS, DEFAULT)["views"] if v["name"] == "custom-1")
    assert view["defaults"] == [{"selection": {"protein": "P1"}}]
    assert not has_own_defaults(view)

    # A ready-made view keeps the user's pin in the views file
    presets = [dict(VIEWS[0], defaults=[{"selection": {"protein": "SHIPPED"}}]), VIEWS[1]]
    view = next(v for v in load_views(path, COMPONENTS, presets, DEFAULT)["views"] if v["name"] == "all")
    assert view["defaults"] == [{"selection": {"protein": "SHIPPED"}}] and not has_own_defaults(view)
    assert set_view_defaults(path, "all", [{"selection": {"a": 1}}], COMPONENTS, presets, DEFAULT)
    view = next(v for v in load_views(path, COMPONENTS, presets, DEFAULT)["views"] if v["name"] == "all")
    assert view["defaults"] == [{"selection": {"a": 1}}] and has_own_defaults(view)
    stored = json.loads(path.read_text())
    assert next(v for v in stored["views"] if v["name"] == "all")["defaults"] == [{"selection": {"a": 1}}]
    # Removing it brings the shipped ones back
    assert set_view_defaults(path, "all", None, COMPONENTS, presets, DEFAULT)
    view = next(v for v in load_views(path, COMPONENTS, presets, DEFAULT)["views"] if v["name"] == "all")
    assert view["defaults"] == [{"selection": {"protein": "SHIPPED"}}] and not has_own_defaults(view)
    # A ready-made view without shipped ones keeps the pin too, and loses it again
    assert set_view_defaults(path, "plots", [{"zoom": {"plot": {"x": [1, 2]}}}], COMPONENTS, VIEWS, DEFAULT)
    view = next(v for v in load_views(path, COMPONENTS, VIEWS, DEFAULT)["views"] if v["name"] == "plots")
    assert has_own_defaults(view)
    assert set_view_defaults(path, "plots", None, COMPONENTS, VIEWS, DEFAULT)
    view = next(v for v in load_views(path, COMPONENTS, VIEWS, DEFAULT)["views"] if v["name"] == "plots")
    assert "defaults" not in view and not has_own_defaults(view)


_DEFAULTS_APP = """
import sys
import streamlit as st
from pathlib import Path
sys.path.insert(0, {tests!r})
from test_layout_manager import _FakeStateManager
from src.layout_manager import view_bar

path = Path(st.session_state["path"])
states = lambda i: _FakeStateManager(f"exp_state_{{i}}")
current = view_bar(path, {components!r}, {presets!r}, {default!r}, key="vb", states=states,
                   datasets=lambda i: "run1")
st.markdown(current + " " + repr(sorted(states(0).get_all_selections().items())))
"""


def test_view_bar_saves_and_restores_zoom_and_selection(tmp_path):
    from src.layout_manager.layout import load_views, save_views

    path = tmp_path / "viewer.json"
    state = load_views(path, COMPONENTS, VIEWS, DEFAULT)
    state["views"].append({"name": "custom-1", "label": "Mine", "rows": [["plot"]], "preset": False, "in_bar": True})
    save_views(path, state)

    at = AppTest.from_string(_DEFAULTS_APP.format(
        tests=str(Path(__file__).parent), components=COMPONENTS, presets=VIEWS, default=DEFAULT))
    at.session_state["path"] = str(path)
    at.run()
    assert not at.exception

    # On the view of one's own: select and zoom, then 📌 and Save
    at.session_state["vb_bar"] = {"action": "pick", "view": "custom-1", "nonce": 1}
    at.run()
    at.session_state["exp_state_0"] = {"selections": {"protein": "P1", "zoom@plot": {"x": [1, 2]}, "t_page": 3}}
    at.session_state["vb_bar"] = {"action": "button", "id": "_save_view_defaults", "nonce": 2}
    at.run()
    assert not at.exception
    at.button(key="vb_defaults_save").click().run()
    assert not at.exception
    view = next(v for v in load_views(path, COMPONENTS, VIEWS, DEFAULT)["views"] if v["name"] == "custom-1")
    assert view["defaults"] == [{"dataset": "run1", "selection": {"protein": "P1"},
                                 "zoom": {"plot": {"x": [1.0, 2.0]}}}]

    # Changed afterwards, ↺ brings the saved state back
    at.session_state["exp_state_0"] = {"selections": {"protein": "P7", "zoom@plot": {"x": [5, 9]}}}
    at.session_state["vb_bar"] = {"action": "button", "id": "_restore_view_defaults", "nonce": 3}
    at.run()
    assert at.markdown[-1].value == "custom-1 [('protein', 'P1'), ('zoom@plot', {'x': [1.0, 2.0], 'xRange': [1.0, 2.0], 'yRange': [-1, -1]})]"

    # Another view and back: opening the view applies its defaults
    at.session_state["vb_bar"] = {"action": "pick", "view": "plots", "nonce": 4}
    at.run()
    at.session_state["exp_state_0"] = {"selections": {"protein": "P8"}}
    at.run()
    at.session_state["vb_bar"] = {"action": "pick", "view": "custom-1", "nonce": 5}
    at.run()
    assert at.markdown[-1].value == "custom-1 [('protein', 'P1'), ('zoom@plot', {'x': [1.0, 2.0], 'xRange': [1.0, 2.0], 'yRange': [-1, -1]})]"


def test_view_bar_pins_zoom_and_selection_on_a_ready_made_view(tmp_path):
    from src.layout_manager.layout import load_views

    path = tmp_path / "viewer.json"
    presets = [dict(VIEWS[0], defaults=[{"selection": {"protein": "SHIPPED"}}]), VIEWS[1]]
    at = AppTest.from_string(_DEFAULTS_APP.format(
        tests=str(Path(__file__).parent), components=COMPONENTS, presets=presets, default=DEFAULT))
    at.session_state["path"] = str(path)
    at.run()
    assert not at.exception

    # 📌 on the ready-made view, then Save
    at.session_state["exp_state_0"] = {"selections": {"protein": "P1", "zoom@plot": {"x": [1, 2]}}}
    at.session_state["vb_bar"] = {"action": "button", "id": "_save_view_defaults", "nonce": 1}
    at.run()
    assert not at.exception
    at.button(key="vb_defaults_save").click().run()
    assert not at.exception
    view = next(v for v in load_views(path, COMPONENTS, presets, DEFAULT)["views"] if v["name"] == "all")
    assert view["defaults"] == [{"dataset": "run1", "selection": {"protein": "P1"},
                                 "zoom": {"plot": {"x": [1.0, 2.0]}}}]

    # Another view and back: the pinned state is applied, not the shipped one
    at.session_state["vb_bar"] = {"action": "pick", "view": "plots", "nonce": 2}
    at.run()
    at.session_state["exp_state_0"] = {"selections": {"protein": "P8"}}
    at.session_state["vb_bar"] = {"action": "pick", "view": "all", "nonce": 3}
    at.run()
    assert at.markdown[-1].value.startswith("all [('protein', 'P1')")

    # Back to the view's own: the shipped selection returns
    at.session_state["vb_bar"] = {"action": "button", "id": "_save_view_defaults", "nonce": 4}
    at.run()
    at.button(key="vb_defaults_remove").click().run()
    assert not at.exception
    view = next(v for v in load_views(path, COMPONENTS, presets, DEFAULT)["views"] if v["name"] == "all")
    assert view["defaults"] == [{"selection": {"protein": "SHIPPED"}}]


def test_zoom_is_shared_by_a_private_state():
    from src.layout_manager.ui import _private_state

    class Base:
        def __init__(self, session_key):
            self.values = {"protein": "P1", "row@table": 2, "row@other": 7, "zoom@plot": {"x": [1, 2]}}

        def get_all_selections(self):
            return dict(self.values)

    state = _private_state(Base)("s", {"row": "row@table"})
    assert state.get_all_selections() == {"protein": "P1", "row": 2, "zoom@plot": {"x": [1, 2]}}
    # A view stores what every component keeps apart too, so it can restore those rows
    from src.layout_manager.ui import _stored
    assert _stored(state) == Base("s").values


def test_defaults_review_fixes(tmp_path):
    from src.layout_manager.layout import capture_defaults, load_views, normalize_zoom, selections_to_apply

    # An oversized number in a stored zoom drops that range instead of breaking the bar
    assert normalize_zoom({"x": [10 ** 400, 1]}) is None
    # A table's page kept apart for it is pagination too
    assert capture_defaults({"table_page@table": 3, "protein": "P1"}) == {"selection": {"protein": "P1"}}
    # A Heatmap reads xRange/yRange, the other plots x/y: both are written
    assert selections_to_apply({"zoom": {"map": {"y": [3.0, 4.0]}}})["zoom@map"] == {
        "y": [3.0, 4.0], "xRange": [-1, -1], "yRange": [3.0, 4.0]}
    # A ready-made view can ship defaults
    presets = [dict(VIEWS[0], defaults=[{"selection": {"protein": "P1"}, "zoom": {"plot": {"x": [2, 1]}}}])] + VIEWS[1:]
    view = load_views(tmp_path / "v.json", COMPONENTS, presets, DEFAULT)["views"][0]
    assert view["defaults"] == [{"selection": {"protein": "P1"}, "zoom": {"plot": {"x": [1.0, 2.0]}}}]


def test_annotations_kept_and_applied_only_for_their_dataset():
    from src.layout_manager.layout import (annotations_identifier, apply_defaults, capture_defaults,
                                           clean_defaults, differs_from_defaults)

    points = {"17": {"highlight": True, "annotation": "b2 1+"}}
    entry = clean_defaults([{"dataset": "run1", "annotations": {"spectrum": points, "bad": "x"},
                             "selection": {"spectrum": 5}}])[0]
    assert entry == {"dataset": "run1", "selection": {"spectrum": 5}, "annotations": {"spectrum": points}}
    assert capture_defaults({annotations_identifier("spectrum"): points}) == {"annotations": {"spectrum": points}}

    class State(dict):
        def get_all_selections(self):
            return dict(self)

        def get_selection(self, identifier):
            return self.get(identifier)

        def set_selection(self, identifier, value):
            self[identifier] = value
            return True

        def clear_selection(self, identifier):
            return self.pop(identifier, None) is not None

    shown = State({"annotations@other": {"1": {"highlight": True}}})
    apply_defaults(shown, entry, "run1")
    assert shown == {"spectrum": 5, "annotations@spectrum": points}
    assert not differs_from_defaults(dict(shown), entry, "run1")
    elsewhere = State()
    apply_defaults(elsewhere, entry, "run2")
    assert elsewhere == {}


def test_link_params_round_trip():
    from src.layout_manager.layout import link_params, link_url, read_link

    entries = [{"dataset": "run1", "selection": {"protein": "P1", "t_page": 2},
                "zoom": {"plot": {"x": [1, 2]}}}, {"dataset": "run2"}, {}]
    params = link_params("custom-1", entries)
    assert set(params) == {"view", "show"} and "=" not in params["show"]
    assert read_link(params) == {"view": "custom-1", "experiments": [
        {"dataset": "run1", "selection": {"protein": "P1"}, "zoom": {"plot": {"x": [1.0, 2.0]}}},
        {"dataset": "run2"}]}
    # A view alone, and what does not decode
    assert link_params("all") == {"view": "all"}
    assert read_link({"view": "all"}) == {"view": "all", "experiments": []}
    assert read_link({"view": "all", "show": "not base64!"}) == {"view": "all", "experiments": []}
    assert read_link({"show": "e30"}) is None  # {} is no experiment
    assert read_link({"workspace": "abc"}) is None
    assert read_link({"view": ["all"]}) == {"view": "all", "experiments": []}
    # The page's other parameters stay, an older link's are replaced
    url = link_url("https://app.example/view?workspace=abc&view=old", params)
    assert url.startswith("https://app.example/view?workspace=abc&view=custom-1&show=")
    assert read_link(dict(__import__("urllib.parse").parse.parse_qsl(url.split("?", 1)[1])))["view"] == "custom-1"


_LINK_APP = """
import sys
import streamlit as st
from pathlib import Path
sys.path.insert(0, {tests!r})
from test_layout_manager import _FakeStateManager
from src.layout_manager import linked_datasets, view_bar

path = Path(st.session_state["path"])
linked = linked_datasets("vb")
if linked and linked[0]:
    st.session_state["dataset"] = linked[0]
states = lambda i: _FakeStateManager(f"exp_state_{{i}}")
current = view_bar(path, {components!r}, {presets!r}, {default!r}, key="vb", states=states,
                   datasets=lambda i: st.session_state.get("dataset", "run1"), link=True)
st.markdown(current + " " + st.session_state.get("dataset", "run1") + " "
            + repr(sorted(states(0).get_all_selections().items())))
"""


def test_view_bar_opens_and_gives_links(tmp_path):
    from src.layout_manager.layout import link_params, read_link

    path = tmp_path / "viewer.json"
    at = AppTest.from_string(_LINK_APP.format(
        tests=str(Path(__file__).parent), components=COMPONENTS, presets=VIEWS, default=DEFAULT))
    at.session_state["path"] = str(path)
    params = link_params("plots", [{"dataset": "run2", "selection": {"protein": "P4"},
                                    "zoom": {"plot": {"x": [3, 4]}}}])
    at.query_params.update(params)
    at.query_params["workspace"] = "abc"
    at.run()
    assert not at.exception
    assert at.markdown[-1].value.startswith("plots run2 [('protein', 'P4'), ('zoom@plot', {'x': [3.0, 4.0]")
    # Applied once: the link's parameters are gone, the workspace stays, the user's picks hold
    assert "view" not in at.query_params and at.query_params["workspace"] == ["abc"]
    at.session_state["exp_state_0"] = {"selections": {"protein": "P9"}}
    at.session_state["dataset"] = "run3"
    at.run()
    assert at.markdown[-1].value == "plots run3 [('protein', 'P9')]"

    # 🔗 gives a link to what is shown now
    at.session_state["vb_bar"] = {"action": "button", "id": "_copy_view_link", "nonce": 1}
    at.run()
    assert not at.exception
    from urllib.parse import parse_qsl, urlsplit
    url = at.code[0].value
    query = dict(parse_qsl(urlsplit(url).query))
    assert query["workspace"] == "abc"
    assert read_link(query) == {"view": "plots", "experiments": [
        {"dataset": "run3", "selection": {"protein": "P9"}}]}


def test_link_params_leaves_out_what_does_not_fit():
    from src.layout_manager.layout import MAX_LINK_LENGTH, link_params, read_link

    points = {str(i): {"highlight": True, "annotation": f"b{i} 1+"} for i in range(400)}
    entries = [{"dataset": "run1", "selection": {"protein": "P1"}, "annotations": {"spectrum": points}}]
    params = link_params("all", entries)
    assert len(params["show"]) <= MAX_LINK_LENGTH
    assert read_link(params)["experiments"] == [{"dataset": "run1", "selection": {"protein": "P1"}}]
    big = [{"dataset": "run1", "selection": {"ids": list(range(5000))}}]
    assert read_link(link_params("all", big))["experiments"] == [{"dataset": "run1"}]
    # Deeply nested input does not raise
    import base64
    show = base64.urlsafe_b64encode(b"[" * 5000).decode()[:MAX_LINK_LENGTH]
    assert read_link({"view": "all", "show": show}) == {"view": "all", "experiments": []}


def test_link_params_keeps_the_view_when_even_the_datasets_do_not_fit():
    from src.layout_manager.layout import link_params, read_link

    params = link_params("all", [{"dataset": "x" * 9000, "selection": {"protein": "P1"}}])
    assert params == {"view": "all"}
    assert read_link(params) == {"view": "all", "experiments": []}


def test_link_dialog_says_what_the_link_opens(tmp_path):
    at = AppTest.from_string(_LINK_APP.format(
        tests=str(Path(__file__).parent), components=COMPONENTS, presets=VIEWS, default=DEFAULT))
    at.session_state["path"] = str(tmp_path / "viewer.json")
    at.run()
    at.session_state["exp_state_0"] = {"selections": {"protein": "P1"}}
    at.session_state["vb_bar"] = {"action": "button", "id": "_copy_view_link", "nonce": 1}
    at.run()
    assert not at.exception
    opens = lambda: next(m.value for m in at.markdown if m.value.startswith("Opens"))
    assert "with the same data, zoom and selection" in opens()
    # A dataset id too long for a link: the view only, and the dialog says so
    at.session_state["dataset"] = "x" * 9000
    at.session_state["vb_bar"] = {"action": "button", "id": "_copy_view_link", "nonce": 2}
    at.run()
    assert not at.exception
    assert opens() == "Opens this page on **All**."
    assert any("opens the view only" in c.value for c in at.caption)
