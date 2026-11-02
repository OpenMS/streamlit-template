"""Dashboard layouts: panels, the layout format, validation and storage.

Streamlit-free. An app describes the panels it can draw (:class:`Panel`), the
template stores which panels the user put where and draws them
(:mod:`src.common.dashboard.ui`).

Layout format (the same as FLASHApp's Layout Manager): a list of views, each a
list of rows, each a list of panel names::

    [[["key_figures"], ["volcano", "abundance"], ["statistics_table"]]]

Most dashboards have one view. Several views show the same kind of panels for
several datasets (FLASHApp's experiments); two views can sit side by side.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_COLUMNS = 3

LAYOUT_DIR = "dashboards"


@dataclass
class Panel:
    """One thing a dashboard can show.

    ``render(context)`` draws the panel into the current Streamlit container;
    ``context`` is whatever the page passes to every panel (data, a shared
    selection state, settings). ``requires`` names a panel that must be in the
    same view, e.g. a plot that follows a table's selection.
    """

    name: str
    label: str
    render: Callable[[dict], None] | None = None
    group: str = ""
    requires: str | None = None
    description: str = ""
    extra: dict = field(default_factory=dict)

    def catalog_entry(self) -> dict:
        """The panel as the layout editor lists it."""
        entry = {"name": self.name, "label": self.label, "group": self.group}
        if self.requires:
            entry["requires"] = self.requires
        if self.description:
            entry["description"] = self.description
        return entry


def catalog(panels: list[Panel]) -> list[dict]:
    return [p.catalog_entry() for p in panels]


def validate_layout(
    layout,
    panels: list[Panel],
    max_views: int = 1,
    max_columns: int = MAX_COLUMNS,
    view_label: str = "View",
) -> str:
    """An error message for an invalid layout, or ``''`` if it can be saved."""
    by_name = {p.name: p for p in panels}
    if not isinstance(layout, list) or not layout:
        return "Empty layout"
    if len(layout) > max_views:
        return f"At most {max_views} {view_label.lower()}s are supported"

    def where(index):
        return f" in {view_label.lower()} {index + 1}" if max_views > 1 else ""

    for index, view in enumerate(layout):
        if not isinstance(view, list) or not any(view):
            return (
                f"{view_label} {index + 1} is empty"
                if max_views > 1
                else f"{view_label} is empty"
            )
        names = []
        for row in view:
            if not isinstance(row, list) or not row:
                return f"Empty row{where(index)}"
            if len(row) > max_columns:
                return f"A row holds at most {max_columns} panels"
            names.extend(row)
        for name in names:
            if name not in by_name:
                return f'Unknown panel "{name}"'
        if len(set(names)) != len(names):
            return f"A panel is placed twice{where(index)}"
        for name in names:
            required = by_name[name].requires
            if required and required not in names:
                return (
                    f"{by_name[name].label} needs "
                    f"{by_name[required].label if required in by_name else required}"
                    f"{where(index)}"
                )
    return ""


def drop_unknown(layout, panels: list[Panel]) -> list:
    """``layout`` without panels this app does not offer, and without empty rows.

    Lets a layout saved by another app (or an older version) still open.
    """
    names = {p.name for p in panels}
    out = []
    for view in layout:
        rows = [[n for n in row if n in names] for row in view]
        out.append([row for row in rows if row])
    return [view for view in out if view]


def layout_path(directory: str | Path, name: str) -> Path:
    """Where the layout of dashboard ``name`` is saved under ``directory``."""
    if not name.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"Invalid dashboard name: {name!r}")
    return Path(directory, LAYOUT_DIR, f"{name}.json")


def load_layout(directory: str | Path, name: str) -> dict | None:
    """``{"layout": ..., "side_by_side": bool}`` saved for ``name``, or None."""
    path = layout_path(directory, name)
    if not path.exists():
        return None
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(saved, dict) or not isinstance(saved.get("layout"), list):
        return None
    return {
        "layout": saved["layout"],
        "side_by_side": bool(saved.get("side_by_side")),
    }


def save_layout(
    directory: str | Path, name: str, layout: list, side_by_side: bool = False
) -> None:
    path = layout_path(directory, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(
            {"layout": layout, "side_by_side": bool(side_by_side) and len(layout) == 2},
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)


def delete_layout(directory: str | Path, name: str) -> None:
    layout_path(directory, name).unlink(missing_ok=True)


def active_layout(
    directory: str | Path, name: str, panels: list[Panel], default_layout: list
) -> tuple[list, bool]:
    """The saved layout (unknown panels dropped) or ``[default_layout]``."""
    saved = load_layout(directory, name)
    if saved:
        layout = drop_unknown(saved["layout"], panels)
        if layout:
            return layout, saved["side_by_side"] and len(layout) == 2
    return [drop_unknown([default_layout], panels)[0]], False
