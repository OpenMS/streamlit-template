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
    clear_layout,
    load_layout,
    save_layout,
    validate_layout,
)

_editor = st_components.declare_component(
    "layout_manager_editor", path=str(Path(__file__).parent / "frontend")
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
