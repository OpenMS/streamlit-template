"""Draw a dashboard and its layout editor.

``render_dashboard`` draws the saved (or default) layout, one Streamlit column
per panel in a row, and hands every panel the same ``context`` so they can
share data and one selection state. ``layout_editor`` is FLASHApp's
drag-and-drop Layout Manager (plain JavaScript in ``frontend/``, no build
step); arranging panels never reruns the script, Python only hears from it on
Save or Reset.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as st_components

from src.common.dashboard.layout import (
    MAX_COLUMNS,
    Panel,
    active_layout,
    catalog,
    delete_layout,
    load_layout,
    save_layout,
    validate_layout,
)

_editor = st_components.declare_component(
    "dashboard_layout_editor", path=str(Path(__file__).parent / "frontend")
)


def layout_editor(
    directory: str | Path,
    name: str,
    panels: list[Panel],
    default_layout: list,
    key: str,
    max_views: int = 1,
    view_label: str = "Dashboard",
) -> None:
    """Edit and save the layout of dashboard ``name`` under ``directory``."""
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
            error = validate_layout(
                submitted.get("layout"), panels, max_views, MAX_COLUMNS, view_label
            )
            if not error:
                save_layout(
                    directory,
                    name,
                    submitted["layout"],
                    bool(submitted.get("side_by_side")),
                )
        elif submitted.get("action") == "reset":
            delete_layout(directory, name)
            st.session_state[revision_key] += 1

    saved = load_layout(directory, name)
    _editor(
        components=catalog(panels),
        default_layout=default_layout,
        saved_layout=saved["layout"] if saved else None,
        side_by_side=saved["side_by_side"] if saved else False,
        max_experiments=max_views,
        max_columns=MAX_COLUMNS,
        view_label=view_label,
        export_name=f"{name}-layout",
        revision=st.session_state[revision_key],
        server_error=error,
        key=key,
        default=None,
    )


def _render_panel(panel: Panel, context: dict) -> None:
    if panel.render is None:
        st.info(f"{panel.label} is not available here.")
        return
    try:
        panel.render(context)
    except Exception as err:  # one broken panel must not take the page down
        st.error(f"{panel.label} could not be shown: {err}")


def render_view(view: list, panels: list[Panel], context: dict) -> None:
    """Draw one view: one row of columns per layout row."""
    by_name = {p.name: p for p in panels}
    for row in view:
        columns = st.columns(len(row)) if len(row) > 1 else [st.container()]
        for column, name in zip(columns, row):
            with column:
                _render_panel(by_name[name], context)


def render_dashboard(
    directory: str | Path,
    name: str,
    panels: list[Panel],
    default_layout: list,
    context: dict | None = None,
    contexts: list[dict] | None = None,
) -> list:
    """Draw dashboard ``name`` with its saved layout, or ``default_layout``.

    Pass ``context`` for a one-view dashboard, or ``contexts`` (one per view,
    e.g. per dataset) for several. Returns the layout drawn.
    """
    layout, side_by_side = active_layout(directory, name, panels, default_layout)
    contexts = contexts or [context or {}]
    views = list(zip(layout, contexts))
    if side_by_side and len(views) == 2:
        for column, (view, ctx) in zip(st.columns(2), views):
            with column:
                render_view(view, panels, ctx)
    else:
        for view, ctx in views:
            render_view(view, panels, ctx)
    return layout
