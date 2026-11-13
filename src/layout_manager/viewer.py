"""The standard Viewer page: what an app shows of its results, described as data.

Every Viewer of the apps does the same six things: list its datasets, pick the
one that opens first, draw the experiment selector with the buttons that act
on what it shows, draw the view bar of that kind of dataset, draw each
experiment's components with one selection state per experiment, and write the
dataset picked back for the other pages. An app describes its data in a
``ViewerSpec`` and calls ``show_viewer(spec)``; the page does the rest::

    RUNS = DatasetKind(
        name="run", components=CATALOG, presets=PRESETS, default_layout=DEFAULT_LAYOUT,
        views_path=workspace / "layouts" / "viewer.json",
        renderers=lambda ctx: renderers_for(ctx.dataset, ctx.index),
    )
    show_viewer(ViewerSpec(key="viewer", datasets={"run1": "Run 1"}, kinds=[RUNS]))

**Kinds.** A Viewer may show datasets of several kinds (a run, a comparison of
runs): each kind has its components, ready-made views, views file and
renderers, and ``kind_of(dataset)`` names the kind of a dataset. The view bar
and the experiments follow the kind of the first experiment's dataset.

**Experiments with members.** An experiment the selector lists may be made of
several datasets (``members(experiment)``):

* ``member_mode="files"``: the experiment is shown as a whole, and **Files of**
  picks the member whose files the components that show one run's files use
  (``ctx.member``), for runs that added files to an experiment.
* ``member_mode="switch"``: **Single run | Comparison** picks between the
  experiment as a whole (``whole(experiment)``, e.g. a comparison of runs) and
  one of its members, which is then the dataset shown, with its own kind. An
  experiment with no whole may offer the whole as a locked choice
  (``lone_whole(ctx)``, e.g. a dialog to process more files).

**Views the data was not processed for.** ``available(ctx)`` returns the
analyses a dataset has; the view bar locks views needing others and a note
takes the place of such a component. ``unavailable_options(missing, view, ctx)``
returns the dialog's choices, for the experiment that asked.

Pages that must show a particular dataset (a run that has just finished, a
comparison just made) call ``show_dataset(key, dataset_id)`` before
``show_viewer``; ``pick`` instead selects a dataset whenever it changes (the
run picked on another page).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import streamlit as st

from src.layout_manager.layout import MAX_EXPERIMENTS, load_layout, resolve_layout
from src.layout_manager.ui import (
    _picked,
    _selection_key,
    experiment_state,
    linked_datasets,
    render_layout,
    request_analysis,
    view_bar,
)

FILES, SWITCH = "files", "switch"
_WHOLE, _MEMBER = "whole", "member"


def default_states(ctx: "ViewerContext") -> Any:
    """One OpenMS-Insight ``StateManager`` per experiment, cleared when its dataset changes."""
    return experiment_state(ctx.key, ctx.index, ctx.dataset)


@dataclass
class DatasetKind:
    """What the Viewer shows for one kind of dataset (a run, a comparison, a file).

    ``renderers(ctx)`` returns component name -> function drawing it; a kind
    with a grid of its own passes ``render(ctx, rows)`` instead. ``rows(ctx,
    rows, saved)`` may change the rows an experiment shows (``saved`` is False
    while the user has not picked a view, when the rows are those of
    ``default_view(ctx)``). ``before(ctx)`` runs before the view bar (to
    migrate a views file, say). ``buttons(ctx)`` are drawn beside every
    experiment's selector while it shows this kind. ``states(ctx)`` returns the
    selection state of an experiment, so views keep its zoom and selection
    (None: none kept). ``max_experiments`` 1 makes the kind fill the page alone.
    """

    name: str
    components: Sequence[Dict[str, Any]]
    presets: Sequence[Dict[str, Any]]
    default_layout: List[List[str]]
    views_path: Path
    renderers: Optional[Callable[["ViewerContext"], Mapping[str, Callable[[], Any]]]] = None
    render: Optional[Callable[["ViewerContext", List[List[str]]], Any]] = None
    available: Optional[Callable[["ViewerContext"], Any]] = None
    analyses: Optional[Dict[str, Any]] = None
    unavailable_options: Optional[Callable[[List[str], Optional[Dict[str, Any]], "ViewerContext"],
                                           Sequence[Dict[str, Any]]]] = None
    default_view: Optional[Callable[["ViewerContext"], Optional[str]]] = None
    rows: Optional[Callable[["ViewerContext", List[List[str]], bool], List[List[str]]]] = None
    states: Optional[Callable[["ViewerContext"], Any]] = default_states
    before: Optional[Callable[["ViewerContext"], Any]] = None
    buttons: Optional[Callable[["ViewerContext"], Any]] = None
    actions: Optional[Sequence[Dict[str, Any]]] = None
    max_experiments: int = MAX_EXPERIMENTS
    labels: Optional[Mapping[str, str]] = None
    dataset_label: str = "run"
    experiment_label: str = "Experiment"
    help_text: str = ""
    target: str = "the Viewer"
    view_key: Optional[str] = None
    link: bool = False


@dataclass
class ViewerContext:
    """One experiment of the page: the dataset it shows, as experiment ``index``."""

    key: str
    index: int
    experiment: str
    dataset: str
    kind: DatasetKind
    member: Optional[str] = None
    members: List[str] = field(default_factory=list)
    view_key: str = ""

    @property
    def whole(self) -> bool:
        """True while the experiment is shown as a whole (not one of its members)."""
        return self.dataset == self.experiment

    def request_analysis(self, missing: Sequence[str], component: Optional[str] = None) -> None:
        """Open the view bar's dialog offering ``missing`` for this experiment
        (as a button callback, the note of a component in a grid of an app's own)."""
        st.session_state[f"{self.key}_missing_index"] = self.index
        request_analysis(self.view_key, missing, component=component)


@dataclass
class ViewerSpec:
    """An app's Viewer: its datasets, their kinds, and what acts on them."""

    datasets: Mapping[str, str]
    kinds: Sequence[DatasetKind]
    key: str = "viewer"
    kind_of: Optional[Callable[[str], str]] = None
    members: Optional[Callable[[str], Sequence[str]]] = None
    member_mode: str = FILES
    member_label: str = "Files of"
    member_format: Optional[Callable[[str], str]] = None
    member_help: str = ""
    whole: Optional[Callable[[str], bool]] = None
    switch_label: str = "show"
    member_choice: str = "Single run"
    whole_choice: str = "Comparison"
    member_select_label: str = "run"
    switch_help: str = ""
    lone_whole: Optional[Callable[[ViewerContext], Any]] = None
    lone_help: str = ""
    label: str = "Experiment"
    later_label: Optional[str] = None
    later: Optional[Callable[[str], Mapping[str, str]]] = None
    buttons: Optional[Callable[[ViewerContext], Any]] = None
    empty: Optional[Callable[[], Any]] = None
    pick: Optional[str] = None
    on_pick: Optional[Callable[[ViewerContext], Any]] = None

    def kind(self, dataset: str) -> DatasetKind:
        by_name = {k.name: k for k in self.kinds}
        name = self.kind_of(dataset) if self.kind_of else None
        return by_name.get(name, self.kinds[0])

    def view_key(self, kind: DatasetKind) -> str:
        return kind.view_key or f"{self.key}_{kind.name}_view"


# -- what is shown ------------------------------------------------------------

def show_dataset(key: str, dataset: str) -> None:
    """Show ``dataset`` (an experiment or one of its members) as the first
    experiment of ``show_viewer(ViewerSpec(key=key))`` the next time it draws."""
    st.session_state[f"{key}_show_pending"] = dataset


def _member_state(key: str, index: int, experiment: str) -> str:
    # Per experiment: going back to an experiment shows the member picked for it
    return f"{key}_member_{index}_{experiment}"


def _show_state(key: str, index: int) -> str:
    return f"{key}_show_{index}"


def _locate(spec: ViewerSpec, dataset: str) -> bool:
    """Make the first experiment show ``dataset``; False when no experiment holds it."""
    if dataset in spec.datasets:
        st.session_state[_selection_key(spec.key, 0)] = dataset
        st.session_state[_show_state(spec.key, 0)] = _WHOLE
        return True
    for experiment in spec.datasets:
        members = list(spec.members(experiment)) if spec.members else []
        if dataset in members:
            st.session_state[_selection_key(spec.key, 0)] = experiment
            st.session_state[_member_state(spec.key, 0, experiment)] = dataset
            st.session_state[_show_state(spec.key, 0)] = _MEMBER
            return True
    return False


def _apply_picks(spec: ViewerSpec, linked: Optional[str]) -> None:
    pending = st.session_state.pop(f"{spec.key}_show_pending", None)
    if pending is not None and _locate(spec, pending):
        return
    if linked is not None and _locate(spec, linked):
        return
    seen = f"{spec.key}_pick_seen"
    if spec.pick is not None and st.session_state.get(seen) != spec.pick:
        st.session_state[seen] = spec.pick
        _locate(spec, spec.pick)


def _wholes(spec: ViewerSpec, experiment: str, members: Sequence[str]) -> bool:
    return spec.whole(experiment) if spec.whole else bool(members)


def resolve(spec: ViewerSpec, index: int, datasets: Optional[Mapping[str, str]] = None) -> Optional[ViewerContext]:
    """The context of experiment ``index`` as picked so far (nothing is drawn)."""
    experiment = _picked(spec.key, index, datasets if datasets is not None else spec.datasets)
    if experiment is None:
        return None
    members = list(spec.members(experiment)) if spec.members else []
    dataset, member = experiment, None
    picked = st.session_state.get(_member_state(spec.key, index, experiment))
    if spec.member_mode == FILES:
        if len(members) > 1:
            member = picked if picked in members else members[0]
            st.session_state[_member_state(spec.key, index, experiment)] = member
    elif members and _wholes(spec, experiment, members) \
            and st.session_state.get(_show_state(spec.key, index)) == _MEMBER:
        member = picked if picked in members else members[0]
        st.session_state[_member_state(spec.key, index, experiment)] = member
        dataset = member
    kind = spec.kind(dataset)
    return ViewerContext(key=spec.key, index=index, experiment=experiment, dataset=dataset, kind=kind,
                         member=member, members=members, view_key=spec.view_key(kind))


# -- the controls beside a selector -------------------------------------------

def _copy(widget: str, state: str) -> None:
    """A segmented control cleared by a second click keeps what it showed."""
    value = st.session_state.get(widget)
    if value is not None:
        st.session_state[state] = value


def _segmented(label: str, options: List[str], state: str, widget: str, value: str,
               format_func: Optional[Callable[[str], str]] = None, help_text: str = "",
               on_change: Optional[Callable[[], Any]] = None) -> None:
    st.session_state[widget] = value
    st.segmented_control(
        label, options, key=widget, format_func=format_func or str, help=help_text or None,
        on_change=on_change or (lambda: _copy(widget, state)),
    )


def _member_controls(spec: ViewerSpec, ctx: ViewerContext) -> None:
    """**Files of**, or **Single run | Comparison** with the run, for experiment ``ctx.index``."""
    key, index = spec.key, ctx.index
    label_of = spec.member_format or (lambda m: spec.datasets.get(m, m))
    member_state = _member_state(key, index, ctx.experiment)
    if spec.member_mode == FILES:
        if len(ctx.members) > 1:
            _segmented(spec.member_label, ctx.members, member_state, f"{member_state}_widget", ctx.member,
                       label_of, spec.member_help)
        return
    show_state = _show_state(key, index)
    choices = [_MEMBER, _WHOLE]
    names = {_MEMBER: spec.member_choice, _WHOLE: spec.whole_choice}
    if ctx.members and _wholes(spec, ctx.experiment, ctx.members):
        _segmented(spec.switch_label, choices, show_state, f"{show_state}_widget",
                   _WHOLE if ctx.whole else _MEMBER, names.get, spec.switch_help)
        if not ctx.whole:
            widget = f"{member_state}_widget"
            st.session_state[widget] = ctx.member
            st.selectbox(spec.member_select_label, ctx.members, key=widget,
                         format_func=label_of, on_change=lambda: _copy(widget, member_state))
    elif spec.lone_whole is not None:
        widget = f"{show_state}_lone"

        def _lone() -> None:
            if st.session_state.get(widget) == _WHOLE:
                st.session_state[widget] = _MEMBER
                spec.lone_whole(ctx)

        st.session_state[widget] = _MEMBER
        st.segmented_control(
            spec.switch_label, choices, key=widget, help=spec.lone_help or None, on_change=_lone,
            format_func=lambda c: names[c] + (" :material/add_circle:" if c == _WHOLE else ""),
        )


def _row(spec: ViewerSpec, index: int, datasets: Mapping[str, str], label: str,
         app_buttons: bool) -> Optional[ViewerContext]:
    """The selector of experiment ``index`` with its controls and buttons; returns its context."""
    ids = list(datasets)
    state = _selection_key(spec.key, index)
    widget = f"{state}_select"
    picked = _picked(spec.key, index, datasets)
    if picked is None:
        return None
    st.session_state[widget] = picked

    def _changed() -> None:
        st.session_state[state] = st.session_state.get(widget)
        # Another experiment opens as a whole
        st.session_state[_show_state(spec.key, index)] = _WHOLE

    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.selectbox(label, ids, key=widget, format_func=lambda i: datasets.get(i, i), on_change=_changed)
        ctx = resolve(spec, index, datasets)
        _member_controls(spec, ctx)
        if ctx.kind.buttons is not None:
            ctx.kind.buttons(ctx)
        if app_buttons and spec.buttons is not None:
            spec.buttons(ctx)
    return ctx


# -- the page -----------------------------------------------------------------

def _default_rows(ctx: ViewerContext) -> Optional[List[List[str]]]:
    kind = ctx.kind
    name = kind.default_view(ctx) if kind.default_view else None
    return next((p["layout"] for p in kind.presets if p["name"] == name), None) if name else None


def _later_datasets(spec: ViewerSpec, kind: DatasetKind) -> Mapping[str, str]:
    return spec.later(kind.name) if spec.later else spec.datasets


def show_viewer(spec: ViewerSpec) -> List[ViewerContext]:
    """Draw the Viewer ``spec`` describes; returns the context of each experiment drawn."""
    if not spec.datasets:
        if spec.empty is not None:
            spec.empty()
        else:
            st.info("Nothing to show yet.")
        return []
    linked_key = spec.view_key(spec.kinds[0])
    linked = linked_datasets(linked_key) if any(k.link for k in spec.kinds) else []
    _apply_picks(spec, linked[0] if linked else None)

    # What is shown, with what acts on it; then how it is shown; then the components
    first = _row(spec, 0, spec.datasets, spec.label, app_buttons=True)
    kind = first.kind
    if kind.before is not None:
        kind.before(first)
    later = _later_datasets(spec, kind)

    def context(index: int) -> Optional[ViewerContext]:
        return first if index == 0 else resolve(spec, index, later)

    def options(missing: List[str], view: Optional[Dict[str, Any]]) -> Sequence[Dict[str, Any]]:
        index = st.session_state.pop(f"{spec.key}_missing_index", 0) if view is None else 0
        ctx = context(index)
        if ctx is None or ctx.kind.unavailable_options is None:
            return []
        return ctx.kind.unavailable_options(missing, view, ctx)

    def experiment_states(index: int) -> Any:
        ctx = context(index)
        return ctx.kind.states(ctx) if ctx is not None and ctx.kind.states else None

    view_bar(
        kind.views_path, kind.components, kind.presets, kind.default_layout, key=first.view_key,
        actions=kind.actions, help_text=kind.help_text,
        default_view=kind.default_view(first) if kind.default_view else None,
        available=kind.available(first) if kind.available else None,
        analyses=kind.analyses, unavailable_options=options if kind.unavailable_options else None,
        dataset_label=kind.dataset_label,
        states=experiment_states if kind.states is not None else None,
        datasets=lambda index: (context(index).dataset if context(index) else None),
        link=kind.link, max_experiments=kind.max_experiments, target=kind.target,
        experiment_label=kind.experiment_label,
    )
    layout, side_by_side = resolve_layout(kind.views_path, kind.components, kind.default_layout)
    saved = load_layout(kind.views_path) is not None
    layout = layout[:max(1, kind.max_experiments)]

    def one(index: int, rows: List[List[str]]) -> Optional[ViewerContext]:
        if index == 0:
            ctx = first
        else:
            ctx = _row(spec, index, later, spec.later_label or spec.label, app_buttons=False)
        if ctx is None:
            return None
        if not saved:
            rows = _default_rows(ctx) or rows
        if ctx.kind.rows is not None:
            rows = ctx.kind.rows(ctx, rows, saved)
        if ctx.kind.render is not None:
            ctx.kind.render(ctx, rows)
        else:
            k = ctx.kind
            render_layout(
                rows, k.renderers(ctx) if k.renderers else {}, k.labels, components=k.components,
                available=k.available(ctx) if k.available else None, analyses=k.analyses,
                on_missing=lambda missing, name, c=ctx: c.request_analysis(missing, name),
                key=f"{spec.key}_{index}", dataset_label=k.dataset_label,
            )
        return ctx

    if side_by_side and len(layout) == 2:
        shown = []
        for column, (index, rows) in zip(st.columns(2), enumerate(layout)):
            with column:
                shown.append(one(index, rows))
    else:
        shown = []
        for index, rows in enumerate(layout):
            if index:
                st.divider()
            shown.append(one(index, rows))
    if spec.on_pick is not None:
        spec.on_pick(first)
    return [c for c in shown if c is not None]
