"""Layouts: which components a page shows, in which rows. Streamlit-free.

A layout is a list of experiments, each a list of rows, each a list of
component names (at most ``max_columns`` per row)::

    [[["peak_map"], ["spectra_table", "peak_list"], ["spectrum"]]]

Most pages show one experiment. Several experiments let a page show the same or
another arrangement once per file, for comparisons. The names come from a
catalog the page defines::

    COMPONENTS = [
        {"name": "peak_map", "label": "Peak map", "group": "Plots"},
        {"name": "peak_list", "label": "Peak list", "group": "Tables",
         "requires": "spectra_table"},
        ...
    ]

``requires`` names a component that has to be in the same experiment, e.g. a
peak list that follows the spectra table's selection.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MAX_EXPERIMENTS = 5
MAX_COLUMNS = 3

Layout = List[List[List[str]]]


def validate_layout(
    layout: Any,
    components: Sequence[Dict[str, Any]],
    max_experiments: int = MAX_EXPERIMENTS,
    max_columns: int = MAX_COLUMNS,
) -> str:
    """Return why ``layout`` cannot be saved, or '' if it can."""
    by_name = {c["name"]: c for c in components}
    if not isinstance(layout, list) or not layout:
        return "Empty layout"
    if len(layout) > max_experiments:
        return "At most %d experiments are supported" % max_experiments
    for exp_index, exp in enumerate(layout, start=1):
        if not isinstance(exp, list) or not any(exp):
            return "Experiment %d is empty" % exp_index
        names: List[str] = []
        for row in exp:
            if not isinstance(row, list) or not row:
                return "Experiment %d contains an empty row" % exp_index
            if len(row) > max_columns:
                return "A row holds at most %d components" % max_columns
            names.extend(row)
        for name in names:
            if name not in by_name:
                return 'Unknown component "%s"' % name
        if len(set(names)) != len(names):
            return "Experiment %d contains a component twice" % exp_index
        for name in names:
            required = by_name[name].get("requires")
            if required and required not in names:
                return "%s needs %s in experiment %d" % (
                    by_name[name]["label"], by_name[required]["label"], exp_index
                )
    return ""


def save_layout(path: Path, layout: Layout, side_by_side: bool = False) -> None:
    """Store a layout as JSON. ``side_by_side`` only applies to two experiments."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"layout": layout, "side_by_side": bool(side_by_side) and len(layout) == 2}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def load_layout(path: Path) -> Optional[Tuple[Layout, bool]]:
    """Return the stored ``(layout, side_by_side)``, or None if there is none."""
    try:
        data = json.loads(Path(path).read_text())
        return data["layout"], bool(data.get("side_by_side", False))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear_layout(path: Path) -> None:
    """Forget the stored layout, so the page falls back to its default."""
    Path(path).unlink(missing_ok=True)


def resolve_layout(
    path: Path,
    components: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
) -> Tuple[Layout, bool]:
    """The layout a page should render: the stored one, else ``[default_layout]``.

    Components that are not in ``components`` (e.g. offered only once some data
    exists) are left out instead of failing, and rows left empty are dropped. If
    nothing is left of an experiment, the default is used.
    """
    known = {c["name"] for c in components}
    default = [[n for n in row if n in known] for row in default_layout]
    default = [row for row in default if row]
    stored = load_layout(path)
    if stored is None:
        return [default], False
    layout, side_by_side = stored
    out: Layout = []
    for exp in layout if isinstance(layout, list) else []:
        rows = [[n for n in row if n in known] for row in exp if isinstance(row, list)]
        rows = [row for row in rows if row]
        out.append(rows or default)
    if not out:
        return [default], False
    return out, side_by_side and len(out) == 2
