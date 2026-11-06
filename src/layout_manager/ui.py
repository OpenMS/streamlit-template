"""Streamlit side of the layout manager: the editor and the grid renderer.

The editor runs entirely in the browser (``frontend/index.html``, plain
JavaScript with no build step), so arranging components never reruns the
script. Python only hears from it when the user presses Save or Reset.
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence

import streamlit as st
import streamlit.components.v1 as st_components

from src.layout_manager.layout import (
    MAX_COLUMNS,
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
) -> None:
    """Drag-and-drop editor that saves a layout to ``path`` (JSON).

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
    if submitted and submitted.get("nonce") != st.session_state.get(handled_key):
        st.session_state[handled_key] = submitted.get("nonce")
        if submitted.get("action") == "save":
            layout = submitted.get("layout")
            error = validate_layout(layout, components, max_experiments, max_columns)
            if not error:
                save_layout(path, layout, bool(submitted.get("side_by_side")))
        elif submitted.get("action") == "reset":
            clear_layout(path)
            st.session_state[revision_key] += 1

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
