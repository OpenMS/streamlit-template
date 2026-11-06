"""Streamlit side of the layout manager: the editor and the grid renderer.

The editor runs entirely in the browser (``frontend/index.html``, plain
JavaScript with no build step), so arranging components never reruns the
script. Python only hears from it when the user presses Save or Reset.
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import streamlit as st
import streamlit.components.v1 as st_components

from src.layout_manager.layout import (
    MAX_COLUMNS,
    Layout,
    apply_preset,
    clear_layout,
    load_layout,
    load_views,
    match_preset,
    resolve_layout,
    save_layout,
    save_views,
    select_view,
    validate_layout,
    validate_views,
)

_editor = st_components.declare_component(
    "layout_manager_editor", path=str(Path(__file__).parent / "frontend")
)
_view_bar = st_components.declare_component(
    "layout_manager_view_bar", path=str(Path(__file__).parent / "view_bar")
)


def layout_editor(
    path: Path,
    components: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    max_experiments: int = 1,
    max_columns: int = MAX_COLUMNS,
    target: str = "the Viewer",
    experiment_label: str = "Experiment",
    export_filename: str = "layout.json",
) -> bool:
    """Drag-and-drop editor that saves a layout to ``path`` (JSON).

    Returns True in the run that saved or reset the layout (not after a
    refused save), so a caller drawing it in a dialog can rerun the page.

    Args:
        path: Where the layout is stored, e.g. ``<workspace>/layouts/viewer.json``.
            The page that shows the components reads it with ``resolve_layout``.
        components: Catalog entries ``{"name", "label", "group", "requires"?}``.
        default_layout: Rows of component names used until a layout is saved.
        key: Streamlit key of the editor.
        max_experiments: More than 1 lets users add experiments (one grid per
            file, e.g. to compare runs) and put two of them side by side.
        max_columns: Components per row.
        target: How the editor refers to the page that shows the layout.
        experiment_label: What one experiment is called in the editor.
        export_filename: File name of the Export download.
    """
    revision_key = f"{key}_revision"
    handled_key = f"{key}_handled"
    st.session_state.setdefault(revision_key, 0)

    # A submitted value is in session state at the start of the rerun it
    # triggers, so persist it before rendering and the editor gets fresh args.
    submitted = st.session_state.get(key)
    error = ""
    done = False
    if submitted and submitted.get("nonce") != st.session_state.get(handled_key):
        st.session_state[handled_key] = submitted.get("nonce")
        if submitted.get("action") == "save":
            layout = submitted.get("layout")
            error = validate_layout(layout, components, max_experiments, max_columns)
            if not error:
                save_layout(path, layout, bool(submitted.get("side_by_side")))
                done = True
        elif submitted.get("action") == "reset":
            clear_layout(path)
            st.session_state[revision_key] += 1
            done = True

    saved = load_layout(path)
    _editor(
        components=list(components),
        default_layout=default_layout,
        saved_layout=saved[0] if saved else None,
        side_by_side=saved[1] if saved else False,
        max_experiments=max_experiments,
        max_columns=max_columns,
        revision=st.session_state[revision_key],
        server_error=error,
        target=target,
        experiment_label=experiment_label,
        export_filename=export_filename,
        key=key,
        default=None,
    )
    return done


def render_layout(
    rows: List[List[str]],
    renderers: Mapping[str, Callable[[], Any]],
    labels: Mapping[str, str] | None = None,
) -> None:
    """Render one experiment: each row in ``st.columns``, each cell by its renderer.

    ``renderers`` maps component names to functions that draw the component in
    the current container. A component without a renderer shows a notice instead
    of stopping the page.
    """
    for row in rows:
        columns = st.columns(len(row)) if len(row) > 1 else [st.container()]
        for column, name in zip(columns, row):
            with column:
                renderer = renderers.get(name)
                if renderer is None:
                    st.info(f"{(labels or {}).get(name, name)} is not available here.")
                else:
                    renderer()


def layout_button(
    path: Path,
    components: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    label: str = "Edit layout",
    help_text: str = "",
    **editor_args: Any,
) -> None:
    """A button that opens ``layout_editor`` in a dialog over the page.

    A dialog reruns on its own when its widgets change, so after a save or a
    reset it reruns the whole page, which closes the dialog and shows the new
    layout. A refused save keeps the dialog open with the editor's message.
    The dialog stays open over a rerun of the page it did not ask for (a
    component on the page can rerun it right after the click), until it is
    closed or saved. ``editor_args`` go to ``layout_editor``
    (``max_experiments``, ``experiment_label``, ...).
    """
    open_key = f"{key}_dialog_open"

    def _closed() -> None:
        st.session_state[open_key] = False

    @st.dialog(label, width="large", on_dismiss=_closed)
    def _dialog() -> None:
        if help_text:
            st.caption(help_text)
        if layout_editor(path, components, default_layout, key=key, **editor_args):
            _closed()
            st.rerun()

    if st.button(label, key=f"{key}_open", icon=":material/dashboard_customize:"):
        st.session_state[open_key] = True
    if st.session_state.get(open_key):
        _dialog()


CUSTOM = "_custom"


def layout_presets(
    path: Path,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    label: str = "View",
    custom_label: str = "Custom",
) -> Optional[str]:
    """A selector of preset views; picking one stores its layout at ``path``.

    ``presets`` are ``{"name", "label", "layout": rows, "help"?}``. The
    selector shows the preset the current layout is, or ``custom_label`` for a
    layout saved in the editor that is none of them. Picking a preset keeps
    the experiments and their datasets, only their components change. Returns
    the name of the preset shown, or None for a custom layout.
    """
    layout, _ = resolve_layout(path, components, default_layout)
    current = match_preset(layout, presets, components)
    labels = {p["name"]: p["label"] for p in presets}
    options = list(labels) + ([] if current else [CUSTOM])
    labels[CUSTOM] = custom_label
    # The selector follows the stored layout, also after a save in the editor
    st.session_state[key] = current or CUSTOM

    def _picked() -> None:
        preset = next((p for p in presets if p["name"] == st.session_state.get(key)), None)
        if preset is not None:
            apply_preset(path, preset["layout"])

    tips = [f"**{p['label']}**: {p['help']}" for p in presets if p.get("help")]
    # A radio rather than st.segmented_control, whose string value AppTest
    # cannot hold (it reads it as a list of characters on the next run)
    st.radio(
        label, options, format_func=lambda name: labels.get(name, name), key=key,
        on_change=_picked, help="\n\n".join(tips) or None, horizontal=True,
    )
    return current


def _views(path, components, presets, default_layout, default_view) -> Dict[str, Any]:
    """``load_views``, with ``default_view`` current while nothing is saved."""
    state = load_views(path, components, presets, default_layout)
    if default_view and load_layout(path) is None and any(v["name"] == default_view for v in state["views"]):
        state["current"] = default_view
    return state


def views_editor(
    path: Path,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    max_experiments: int = 1,
    max_columns: int = MAX_COLUMNS,
    target: str = "the Viewer",
    experiment_label: str = "Experiment",
    new_view: bool = False,
    default_view: Optional[str] = None,
) -> bool:
    """The editor of a page's views: their order, which are in the bar, their components.

    Ready-made views (``presets``) can be reordered and kept out of the bar but
    not changed; users duplicate one to change it, or start a new view. Returns
    True in the run that saved or reset (not after a refused save).
    ``new_view`` opens the editor on a new view, a copy of the current one; until
    its components change, a "Start from" choice swaps in another view's.
    ``default_view`` is the current view while nothing is saved (see ``view_bar``).
    """
    revision_key = f"{key}_revision"
    handled_key = f"{key}_handled"
    st.session_state.setdefault(revision_key, 0)
    submitted = st.session_state.get(key)
    error = ""
    done = False
    if submitted and submitted.get("nonce") != st.session_state.get(handled_key):
        st.session_state[handled_key] = submitted.get("nonce")
        if submitted.get("action") == "save":
            error = validate_views(submitted, components, presets, default_layout, max_experiments, max_columns)
            if not error:
                state = load_views(path, components, presets, default_layout)
                by_name = {v["name"]: v for v in state["views"]}
                views = []
                for sent in submitted["views"]:
                    view = dict(by_name.get(sent["name"], {}))
                    if not view.get("preset"):
                        view.update(name=sent["name"], label=str(sent["label"]).strip(),
                                    rows=sent["rows"], preset=False)
                    view["in_bar"] = bool(sent.get("in_bar", True))
                    views.append(view)
                save_views(path, {"views": views, "current": submitted["current"],
                                  "experiments": submitted.get("experiments", 1),
                                  "side_by_side": submitted.get("side_by_side")})
                done = True
        elif submitted.get("action") == "reset":
            clear_layout(path)
            st.session_state[revision_key] += 1
            done = True

    state = _views(path, components, presets, default_layout, default_view)
    fresh = None
    if new_view:
        source = next(v for v in state["views"] if v["name"] == state["current"])
        taken = {v["name"] for v in state["views"]}
        number = next(n for n in range(1, len(taken) + 2) if f"custom-{n}" not in taken)
        labels = {v["label"].lower() for v in state["views"]}
        base = f"{source['label']} (copy)"
        label = next(c for c in [base] + [f"{base} {n}" for n in range(2, len(labels) + 3)]
                     if c.lower() not in labels)
        fresh = f"custom-{number}"
        # Right after the view it starts from, or at the end of the bar
        index = state["views"].index(source) + 1 if source["in_bar"] else sum(v["in_bar"] for v in state["views"])
        state["views"].insert(index, {"name": fresh, "label": label,
                                      "rows": [list(r) for r in source["rows"]],
                                      "preset": False, "in_bar": True})
        state["current"] = fresh
    _editor(
        components=list(components),
        default_layout=default_layout,
        saved_layout=None,
        side_by_side=state["side_by_side"],
        views=state["views"],
        current=state["current"],
        experiments=state["experiments"],
        fresh=fresh,
        max_experiments=max_experiments,
        max_columns=max_columns,
        revision=f"{st.session_state[revision_key]}-{int(new_view)}",
        server_error=error,
        target=target,
        experiment_label=experiment_label,
        key=key,
        default=None,
    )
    return done


def view_bar(
    path: Path,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    actions: Optional[Sequence[Dict[str, Any]]] = None,
    details: bool = False,
    label: str = "View",
    dialog_title: str = "Customize views",
    help_text: str = "",
    default_view: Optional[str] = None,
    **editor_args: Any,
) -> str:
    """The view bar: as many views as fit, the rest in More, and ✏️ Customize.

    Views are the page's ``presets`` (``{"name", "label", "layout", "help"?}``)
    and the views users make in the editor, in the order users give them.
    Picking one stores its components as the layout ``resolve_layout`` reads,
    so call this before ``resolve_layout``. The bar ends in +, which opens the
    editor on a new view that starts as a copy of the current one. ``details`` adds the number of components below each
    name while there is room. ``actions`` are icon
    buttons drawn after ✏️, ``{"id", "icon", "help", "on_click"}``; their
    ``on_click`` runs in the rerun after the click (open a dialog there).
    ``default_view`` names the view that is current while nothing is saved
    (the default is the first): a page that picks its default by what a
    dataset holds renders that view's rows itself until the user picks one.
    ``editor_args`` go to ``views_editor`` (``max_experiments``, ...).
    Returns the name of the current view.
    """
    open_key = f"{key}_dialog_open"
    new_key = f"{key}_dialog_new"
    handled_key = f"{key}_bar_handled"
    clicked = None
    submitted = st.session_state.get(f"{key}_bar")
    if submitted and submitted.get("nonce") != st.session_state.get(handled_key):
        st.session_state[handled_key] = submitted.get("nonce")
        if submitted.get("action") == "pick":
            select_view(path, submitted.get("view"), components, presets, default_layout)
        elif submitted.get("action") == "edit":
            st.session_state[open_key] = True
            st.session_state[new_key] = bool(submitted.get("new_view"))
        elif submitted.get("action") == "button":
            clicked = submitted.get("id")

    state = _views(path, components, presets, default_layout, default_view)
    _view_bar(
        views=[{k: v[k] for k in ("name", "label", "rows", "preset", "in_bar", "help") if k in v}
               for v in state["views"]],
        current=state["current"],
        details=details,
        label=label,
        customize_help="Customize views",
        actions=[{k: a[k] for k in ("id", "icon", "label", "help") if k in a} for a in actions or []],
        key=f"{key}_bar",
        default=None,
    )

    def _closed() -> None:
        st.session_state[open_key] = False
        st.session_state[new_key] = False

    @st.dialog(dialog_title, width="large", on_dismiss=_closed)
    def _dialog() -> None:
        if help_text:
            st.caption(help_text)
        new = st.session_state.get(new_key, False)
        if views_editor(path, components, presets, default_layout, key=f"{key}_editor",
                        new_view=new, default_view=default_view, **editor_args):
            _closed()
            st.rerun()

    if st.session_state.get(open_key):
        _dialog()
    for action in actions or []:
        if action.get("id") == clicked and action.get("on_click"):
            action["on_click"]()
    return state["current"]


def _selection_key(key: str, index: int) -> str:
    return f"{key}_experiment_{index}"


def selected_datasets(key: str, count: int) -> List[Optional[str]]:
    """The dataset ids picked in the selectors of ``render_experiments``."""
    return [st.session_state.get(_selection_key(key, i)) for i in range(count)]


def _selector(
    key: str,
    index: int,
    datasets: Mapping[str, str],
    label: str,
    buttons: Optional[Callable[[int], Any]],
) -> Optional[str]:
    """The dataset selector of experiment ``index``; returns the picked id."""
    ids = list(datasets)
    state = _selection_key(key, index)
    widget = f"{state}_select"
    # Keep the pick by id, so a renamed or added dataset does not move it.
    picked = st.session_state.get(state)
    if picked not in datasets:
        picked = ids[index] if index < len(ids) else (ids[0] if ids else None)
        st.session_state[state] = picked
    if st.session_state.get(widget) != picked:
        st.session_state[widget] = picked

    def _changed() -> None:
        st.session_state[state] = st.session_state.get(widget)

    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.selectbox(
            label, ids, key=widget, format_func=lambda i: datasets.get(i, i),
            on_change=_changed,
        )
        if buttons is not None:
            buttons(index)
    return st.session_state.get(state)


def render_experiments(
    layout: Layout,
    side_by_side: bool,
    datasets: Mapping[str, str],
    renderers: Callable[[str, int], Mapping[str, Callable[[], Any]]],
    key: str,
    labels: Optional[Mapping[str, str]] = None,
    experiment_label: str = "Experiment",
    buttons: Optional[Callable[[int], Any]] = None,
) -> List[Optional[str]]:
    """Render every experiment of ``layout``, each below its own dataset selector.

    This is FLASHApp's Viewer: one grid per experiment, each showing the dataset
    (a run, a file, a comparison) picked above it, so users compare datasets by
    adding experiments in the layout editor. Two experiments marked side by side
    share the width; any other number are drawn one below the other.

    Args:
        layout: Experiments as ``resolve_layout`` returns them.
        side_by_side: Draw two experiments in two columns.
        datasets: Dataset id -> label, in the order the selectors offer them.
            Experiment ``n`` starts on the ``n``-th dataset.
        renderers: ``renderers(dataset_id, index)`` returns the renderers of
            experiment ``index`` for that dataset (component name -> function).
            Give each experiment its own widget keys and, with Insight, its own
            ``StateManager``, so selections in one do not move the other.
        key: Prefix of the selectors' session keys.
        labels: Component name -> label, for the notice of a missing renderer.
        experiment_label: Label of each selector.
        buttons: ``buttons(index)`` draws buttons right of a selector, such as
            ``layout_button``.

    Returns:
        The dataset id picked in each experiment (None without datasets).
    """
    if not datasets:
        return [None] * len(layout)

    def one(index: int, rows: List[List[str]]) -> Optional[str]:
        dataset = _selector(key, index, datasets, experiment_label, buttons)
        if dataset is not None:
            render_layout(rows, renderers(dataset, index), labels)
        return dataset

    if side_by_side and len(layout) == 2:
        picked = []
        for column, (index, rows) in zip(st.columns(2), enumerate(layout)):
            with column:
                picked.append(one(index, rows))
        return picked
    picked = []
    for index, rows in enumerate(layout):
        if index:
            st.divider()
        picked.append(one(index, rows))
    return picked



def experiment_state(
    key: str,
    index: int,
    dataset_id: Optional[str] = None,
    private: Sequence[str] = (),
    owner: str = "",
) -> Any:
    """The OpenMS-Insight ``StateManager`` all components of one experiment share.

    Keyed by experiment, not by view or component: a protein, peptide or
    spectrum picked in one view stays picked when the user switches views,
    and two experiments side by side keep their own selections. Pass the
    experiment's ``dataset_id`` so that picking another dataset clears the
    selection.

    An identifier that means something else in each component (a row number
    of that component's own table, say) is listed in ``private`` with the
    component's name as ``owner``: it is then kept apart for that component,
    while every other identifier stays shared. Needs ``openms-insight``, which
    the template does not install.
    """
    from openms_insight import StateManager  # pylint: disable=import-outside-toplevel

    name = f"{key}_state_{index}"
    shown = f"{name}_dataset"
    if dataset_id is not None and st.session_state.get(shown) != dataset_id:
        st.session_state.pop(name, None)
        st.session_state[shown] = dataset_id
    # Also without private identifiers: other components' private ones stay hidden
    return _private_state(StateManager)(name, {i: f"{i}@{owner}" for i in private})


def _private_state(base: type) -> type:
    """A ``StateManager`` that keeps some identifiers apart under other names."""

    class PrivateState(base):  # type: ignore[misc, valid-type]
        def __init__(self, session_key: str, renamed: Dict[str, str]):
            self._renamed = renamed
            self._back = {v: k for k, v in renamed.items()}
            super().__init__(session_key)

        def _to_store(self, identifier: str) -> str:
            return self._renamed.get(identifier, identifier)

        def _from_store(self, values: Dict[str, Any]) -> Dict[str, Any]:
            # The shared names this component keeps apart are hidden, its own shown under them
            out = {k: v for k, v in values.items() if k not in self._renamed and "@" not in k}
            out.update({self._back[k]: v for k, v in values.items() if k in self._back})
            return out

        def get_selection(self, identifier: str) -> Any:
            return super().get_selection(self._to_store(identifier))

        def set_selection(self, identifier: str, value: Any) -> bool:
            return super().set_selection(self._to_store(identifier), value)

        def clear_selection(self, identifier: str) -> bool:
            return super().clear_selection(self._to_store(identifier))

        def get_all_selections(self) -> Dict[str, Any]:
            return self._from_store(super().get_all_selections())

        def get_state_for_vue(self) -> Dict[str, Any]:
            return self._from_store(super().get_state_for_vue())

        def update_from_vue(self, vue_state: Dict[str, Any]) -> bool:
            if vue_state is None:
                return super().update_from_vue(vue_state)
            return super().update_from_vue({self._to_store(k): v for k, v in vue_state.items()})

    return PrivateState
