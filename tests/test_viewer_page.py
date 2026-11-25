"""Tests for the standard Viewer page (src/layout_manager/viewer.py)."""

import json

import pytest

from streamlit.testing.v1 import AppTest
from streamlit.testing.v1 import element_tree


def _indices(self):
    # AppTest reads every button group as a multi-select; a segmented control
    # with selection_mode="single" holds one value, or None
    value = self.value
    values = [] if value is None else value if isinstance(value, list) else [value]
    return [self.options.index(self.format_func(v)) for v in values]


@pytest.fixture(autouse=True)
def _single_button_groups(monkeypatch):
    monkeypatch.setattr(element_tree.ButtonGroup, "indices", property(_indices))

# A Viewer with two kinds: runs, and comparisons of runs that list their runs
# as members. Every renderer writes what it draws, so the tests read the page.
_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager.viewer import DatasetKind, ViewerSpec, show_viewer, show_dataset

ROOT = Path({root!r})
MODE = {mode!r}
COMPONENTS = [
    {{"name": "plot", "label": "Plot", "group": "Plots"}},
    {{"name": "ids", "label": "Identifications", "group": "Tables", "needs": "identification"}},
]
PRESETS = [
    {{"name": "plots", "label": "Plots", "layout": [["plot"]]}},
    {{"name": "ids", "label": "IDs", "layout": [["plot", "ids"]]}},
]
IDENTIFIED = {{"r1"}}


def renderers(ctx):
    return {{name: (lambda name=name: st.markdown(
        f"{{ctx.index}}:{{ctx.kind.name}}:{{ctx.dataset}}:{{ctx.member}}:{{name}}"))
        for name in ("plot", "ids")}}


def options(missing, view, ctx):
    st.session_state["asked_for"] = (ctx.dataset, list(missing))
    return [{{"label": f"Add to {{ctx.dataset}}", "on_click": lambda: None}}]


RUN = DatasetKind(
    name="run", components=COMPONENTS, presets=PRESETS, default_layout=[["plot"]],
    views_path=ROOT / "runs.json", renderers=renderers, states=None,
    available=lambda ctx: {{"identification"}} if ctx.dataset in IDENTIFIED else set(),
    analyses={{"identification": "identification"}}, unavailable_options=options,
    default_view=lambda ctx: "ids" if ctx.dataset in IDENTIFIED else "plots",
    buttons=lambda ctx: st.button(f"run button {{ctx.index}}", key=f"rb{{ctx.index}}"),
)
COMPARISON = DatasetKind(
    name="comparison", components=COMPONENTS[:1], presets=PRESETS[:1], default_layout=[["plot"]],
    views_path=ROOT / "comparisons.json", states=None, max_experiments=1, link=False,
    render=lambda ctx, rows: st.markdown(f"comparison grid {{ctx.dataset}} {{rows}}"),
)
if st.session_state.pop("_show", None):
    show_dataset("v", st.session_state["_show_target"])
show_viewer(ViewerSpec(
    key="v", kinds=[RUN, COMPARISON], member_mode=MODE,
    datasets={{"cmp": "Comparison of 2", "r3": "Run 3"}} if MODE == "switch" else {{"r1": "Run 1", "r3": "Run 3"}},
    kind_of=lambda d: "comparison" if d == "cmp" else "run",
    members=lambda e: ["r1", "r2"] if e in ("cmp", "r1") else [],
    whole=(lambda e: e == "cmp") if MODE == "switch" else None,
    lone_whole=lambda ctx: st.session_state.update(lone=ctx.dataset),
    later=lambda kind: {{"r1": "Run 1", "r2": "Run 2", "r3": "Run 3"}},
    buttons=lambda ctx: st.button("history", key="history"),
    empty=lambda: st.markdown("nothing here"),
    on_pick=lambda ctx: st.session_state.update(picked=(ctx.experiment, ctx.dataset)),
))
"""


def _app(tmp_path, mode="switch"):
    return AppTest.from_string(_APP.format(root=str(tmp_path), mode=mode))


def _texts(at):
    return [m.value for m in at.markdown]


def _segmented(at, key):
    """A segmented control (a button group to AppTest), or None."""
    found = [b for b in at.button_group if b.key == key]
    return found[0] if found else None


def _choose(at, key, value):
    _segmented(at, key).set_value([value])
    return at.run()


def test_comparison_and_its_runs(tmp_path):
    at = _app(tmp_path).run()
    assert not at.exception
    # The first experiment opens as a whole: the comparison, with its own grid
    assert _texts(at) == ["comparison grid cmp [['plot']]"]
    assert at.session_state["picked"] == ("cmp", "cmp")
    assert _segmented(at, "v_show_0_widget").value == "whole"
    # Single run: its first run, with the run views (identified: its default view)
    _choose(at, "v_show_0_widget", "member")
    assert not at.exception
    assert _texts(at) == ["0:run:r1:r1:plot", "0:run:r1:r1:ids"]
    assert at.button(key="rb0") and at.button(key="history")
    at.selectbox(key="v_member_0_cmp_widget").set_value("r2").run()
    # r2 was not identified: its default view has the plot only
    assert _texts(at) == ["0:run:r2:r2:plot"]
    assert at.session_state["picked"] == ("cmp", "r2")


def test_a_run_alone_offers_the_comparison(tmp_path):
    at = _app(tmp_path).run()
    at.selectbox(key="v_experiment_0_select").set_value("r3").run()
    assert _texts(at) == ["0:run:r3:None:plot"]
    _choose(at, "v_show_0_lone", "whole")
    assert not at.exception
    assert at.session_state["lone"] == "r3"
    assert _segmented(at, "v_show_0_lone").value == "member"


def test_show_dataset_finds_a_member(tmp_path):
    at = _app(tmp_path).run()
    at.session_state["_show"] = True
    at.session_state["_show_target"] = "r2"
    at.run()
    assert _texts(at) == ["0:run:r2:r2:plot"]
    assert at.session_state["picked"] == ("cmp", "r2")


def test_files_of(tmp_path):
    at = _app(tmp_path, mode="files").run()
    assert not at.exception
    # The experiment stays the dataset; Files of picks the member
    assert _texts(at) == ["0:run:r1:r1:plot", "0:run:r1:r1:ids"]
    _choose(at, "v_member_0_r1_widget", "r2")
    assert _texts(at)[0] == "0:run:r1:r2:plot"
    # A run of one member has no Files of
    at.selectbox(key="v_experiment_0_select").set_value("r3").run()
    assert _texts(at) == ["0:run:r3:None:plot"]
    assert _segmented(at, "v_member_0_r3_widget") is None


def test_saved_views_and_later_experiments(tmp_path):
    # Two experiments side by side, in a view of the user's own
    (tmp_path / "runs.json").write_text(json.dumps({
        "layout": [[["plot", "ids"]], [["plot", "ids"]]], "side_by_side": True,
        "current": "mine", "experiments": 2,
        "views": [{"name": "mine", "label": "Mine", "rows": [["plot", "ids"]]}],
    }))
    at = _app(tmp_path, mode="files").run()
    assert not at.exception
    texts = _texts(at)
    assert "0:run:r1:r1:plot" in texts and "0:run:r1:r1:ids" in texts
    # The second experiment starts on the second dataset it is offered; it lacks
    # the identifications, so a note takes their place
    assert "1:run:r2:None:plot" in texts
    assert not any(t.startswith("1:run:r2:None:ids") for t in texts)
    assert at.button(key="rb1")
    note = next(b for b in at.button if b.key == "v_1_missing_ids")
    note.click().run()
    assert not at.exception
    assert at.session_state["asked_for"] == ("r2", ["identification"])


def test_nothing_to_show(tmp_path):
    at = AppTest.from_string(
        "from pathlib import Path\n"
        "import streamlit as st\n"
        "from src.layout_manager.viewer import DatasetKind, ViewerSpec, show_viewer\n"
        "K = DatasetKind(name='run', components=[], presets=[], default_layout=[], views_path=Path('x.json'))\n"
        "show_viewer(ViewerSpec(datasets={}, kinds=[K], empty=lambda: st.markdown('nothing here')))\n"
    ).run()
    assert not at.exception
    assert _texts(at) == ["nothing here"]


def test_files_of_is_kept_per_experiment(tmp_path):
    at = _app(tmp_path, mode="files").run()
    _choose(at, "v_member_0_r1_widget", "r2")
    at.selectbox(key="v_experiment_0_select").set_value("r3").run()
    at.selectbox(key="v_experiment_0_select").set_value("r1").run()
    assert _texts(at)[0] == "0:run:r1:r2:plot"


def test_presets_follow_the_shown_dataset(tmp_path):
    # A kind's presets, components and default layout may depend on what is shown
    at = AppTest.from_string(
        "from pathlib import Path\n"
        "import streamlit as st\n"
        "from src.layout_manager.viewer import DatasetKind, ViewerSpec, show_viewer\n"
        "C = [{'name': 'a', 'label': 'A', 'group': 'G'}, {'name': 'b', 'label': 'B', 'group': 'G'}]\n"
        "K = DatasetKind(name='run', components=lambda ctx: C if ctx.dataset == 'x' else C[:1],\n"
        "    presets=lambda ctx: [{'name': 'p', 'label': 'P', 'layout': [['a', 'b']] if ctx.dataset == 'x' else [['a']]}],\n"
        "    default_layout=lambda ctx: [['a', 'b']] if ctx.dataset == 'x' else [['a']], views_path=Path(%r) / 'v.json', states=None,\n"
        "    renderers=lambda ctx: {n: (lambda n=n: st.markdown(f'{ctx.dataset}:{n}')) for n in ('a', 'b')})\n"
        "show_viewer(ViewerSpec(key='v', kinds=[K], datasets={'x': 'X', 'y': 'Y'}))\n" % str(tmp_path)
    ).run()
    assert not at.exception
    assert _texts(at) == ["x:a", "x:b"]
    at.selectbox(key="v_experiment_0_select").set_value("y").run()
    assert not at.exception
    assert _texts(at) == ["y:a"]


def test_later_experiments_have_no_switch(tmp_path):
    (tmp_path / "runs.json").write_text(json.dumps({
        "layout": [[["plot"]], [["plot"]]], "side_by_side": False, "current": "plots", "experiments": 2,
    }))
    at = _app(tmp_path).run()
    at.selectbox(key="v_experiment_0_select").set_value("r3").run()
    assert not at.exception
    # The first experiment offers the comparison locked; the second has no control
    assert _segmented(at, "v_show_0_lone") is not None
    assert _segmented(at, "v_show_1_lone") is None and _segmented(at, "v_show_1_widget") is None


# An experiment whose id is its first run's (runs that added files to it):
# Single run shows that run under the same id, and whole_kind names the kind
# of the whole
_SAME_ID_APP = """
import streamlit as st
from pathlib import Path
from src.layout_manager.viewer import DatasetKind, ViewerSpec, show_viewer

ROOT = Path({root!r})
COMPONENTS = [{{"name": "plot", "label": "Plot", "group": "Plots"}}]
PRESETS = [{{"name": "plots", "label": "Plots", "layout": [["plot"]]}}]


def kind(name):
    return DatasetKind(
        name=name, components=COMPONENTS, presets=PRESETS, default_layout=[["plot"]],
        views_path=ROOT / f"{{name}}.json", states=None,
        renderers=lambda ctx: {{"plot": lambda: st.markdown(
            f"{{ctx.kind.name}}:{{ctx.dataset}}:{{ctx.whole}}")}},
    )


show_viewer(ViewerSpec(
    key="s", kinds=[kind("run"), kind("experiment")], member_mode="switch", whole_kind="experiment",
    datasets={{"r1": "Run 1"}}, members=lambda e: ["r1", "r2"],
))
"""


def test_whole_of_an_experiment_named_after_its_first_run(tmp_path):
    at = AppTest.from_string(_SAME_ID_APP.format(root=str(tmp_path))).run()
    assert not at.exception
    assert _texts(at) == ["experiment:r1:True"]
    _choose(at, "s_show_0_widget", "member")
    assert _texts(at) == ["run:r1:False"]
    at.selectbox(key="s_member_0_r1_widget").set_value("r2").run()
    assert _texts(at) == ["run:r2:False"]


_SWITCH_APP = """
import streamlit as st
from src.layout_manager import member_switch

picked = member_switch("m", {members!r}, label_of=str.upper)
st.markdown(f"picked {{picked}}")
"""


def test_member_switch(tmp_path):
    at = AppTest.from_string(_SWITCH_APP.format(members=["a", "b"])).run()
    assert _texts(at) == ["picked None"]
    _choose(at, "m_show_widget", "member")
    assert _texts(at) == ["picked a"]
    at.selectbox(key="m_member_widget").set_value("b").run()
    assert _texts(at) == ["picked b"]
    _choose(at, "m_show_widget", "whole")
    assert _texts(at) == ["picked None"]
    # One run: nothing to switch
    at = AppTest.from_string(_SWITCH_APP.format(members=["a"])).run()
    assert _texts(at) == ["picked None"] and _segmented(at, "m_show_widget") is None


_COMPARISON_APP = """
import streamlit as st
from src.layout_manager import edit_comparison

def done():
    st.session_state["done"] = st.session_state.get("step_value")
    return st.session_state.get("step_value") != "bad"

edit_comparison(
    "c", [("1. One", lambda: st.text_input("value", key="step_value")), ("2. Two", lambda: st.markdown("two"))],
    on_reset=lambda: st.session_state.update(reset=True), on_done=done,
)
"""


def test_edit_comparison(tmp_path):
    at = AppTest.from_string(_COMPARISON_APP).run()
    assert not at.exception and not at.tabs
    at.button(key="c_comparison_button").click().run()
    assert [t.label for t in at.tabs] == ["1. One", "2. Two"]
    at.text_input(key="step_value").set_value("bad").run()
    at.button(key="c_comparison_done").click().run()
    # on_done returned False: the dialog stays
    assert at.session_state["done"] == "bad" and at.tabs
    at.text_input(key="step_value").set_value("good").run()
    at.button(key="c_comparison_done").click().run()
    # AppTest keeps the dialog's elements after a rerun from inside it, so check the state
    assert at.session_state["done"] == "good" and not at.session_state["c_comparison_open"]
    at = AppTest.from_string(_COMPARISON_APP).run()
    at.button(key="c_comparison_button").click().run()
    at.button(key="c_comparison_reset").click().run()
    assert at.session_state["reset"] and at.session_state["c_comparison_open"]


def _picks_spec(pick=None):
    from src.layout_manager.viewer import ViewerSpec
    spec = ViewerSpec.__new__(ViewerSpec)
    spec.key, spec.datasets, spec.members, spec.pick = "v", ["a", "b", "c"], None, pick
    return spec


def test_link_sets_every_experiment_and_a_pick_is_seen(monkeypatch):
    from src.layout_manager import viewer
    state = {}
    monkeypatch.setattr(viewer.st, "session_state", state)
    viewer._apply_picks(_picks_spec(pick="c"), ["b", None, "a"])
    assert state[viewer._selection_key("v", 0)] == "b"
    assert viewer._selection_key("v", 1) not in state
    assert state[viewer._selection_key("v", 2)] == "a"
    # The pick of another page lost to the link, but is not taken for a new one later
    state[viewer._selection_key("v", 0)] = "b"
    viewer._apply_picks(_picks_spec(pick="c"), [])
    assert state[viewer._selection_key("v", 0)] == "b"
    viewer._apply_picks(_picks_spec(pick="a"), [])
    assert state[viewer._selection_key("v", 0)] == "a"


def test_a_link_to_a_kind_without_links_is_applied_once(tmp_path):
    """A link naming a dataset whose kind has no links is used up on the first run,
    so the user's later picks stay."""
    from src.layout_manager.layout import link_params
    source = _APP.format(root=str(tmp_path), mode="switch").replace(
        'buttons=lambda ctx: st.button(f"run button', 'link=True, buttons=lambda ctx: st.button(f"run button')
    at = AppTest.from_string(source)
    for name, value in link_params("plots", [{"dataset": "cmp"}]).items():
        at.query_params[name] = value
    at.run()
    assert not at.exception
    assert _texts(at) == ["comparison grid cmp [['plot']]"]
    assert not any(name in at.query_params for name in link_params("plots"))
    at.selectbox(key="v_experiment_0_select").set_value("r3").run()
    assert _texts(at) == ["0:run:r3:None:plot"]
    at.run()
    assert _texts(at) == ["0:run:r3:None:plot"]
