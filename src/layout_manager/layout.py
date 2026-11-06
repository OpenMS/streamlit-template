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
peak list that follows the spectra table's selection. A list names several of
which one has to be there; ``requires_label`` then names them in messages
("a protein or proteoform table").

A page can also offer preset views, ready-made layouts for one purpose::

    PRESETS = [
        {"name": "overview", "label": "Overview", "layout": [["peak_map"], ["spectrum"]]},
        {"name": "spectra", "label": "Spectra", "layout": [["spectra_table", "peak_list"]],
         "help": "Browse the spectra one by one."},
    ]

``apply_preset`` stores a preset's rows for every experiment, and
``match_preset`` tells which preset the current layout is, if any.
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
            required = requirements(by_name[name])
            if required and not any(r in names for r in required):
                return "%s needs %s in experiment %d" % (
                    by_name[name]["label"], requirement_label(by_name[name], by_name), exp_index
                )
    return ""


def requirements(component: Dict[str, Any]) -> List[str]:
    """The components one of which has to be in the same experiment as ``component``."""
    required = component.get("requires")
    if not required:
        return []
    return [required] if isinstance(required, str) else list(required)


def requirement_label(component: Dict[str, Any], by_name: Dict[str, Dict[str, Any]]) -> str:
    """How messages name what ``component`` requires."""
    if component.get("requires_label"):
        return component["requires_label"]
    return " or ".join(by_name[r]["label"] if r in by_name else r for r in requirements(component))


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


def _known_rows(rows: Sequence[Sequence[str]], known: set) -> List[List[str]]:
    rows = [[n for n in row if n in known] for row in rows]
    return [row for row in rows if row]


def match_preset(
    layout: Layout,
    presets: Sequence[Dict[str, Any]],
    components: Sequence[Dict[str, Any]],
) -> Optional[str]:
    """The name of the preset every experiment of ``layout`` shows, or None.

    Presets are compared as the page renders them, without the components
    ``components`` does not offer.
    """
    known = {c["name"] for c in components}
    for preset in presets:
        rows = _known_rows(preset["layout"], known)
        if layout and all(_known_rows(exp, known) == rows for exp in layout):
            return preset["name"]
    return None


def apply_preset(path: Path, rows: List[List[str]]) -> None:
    """Store ``rows`` as the layout of every experiment of the stored layout.

    The number of experiments and whether two are side by side stay as they
    are, so a comparison of runs keeps its runs when the view changes.
    """
    stored = load_layout(path)
    count, side_by_side = (len(stored[0]) or 1, stored[1]) if stored else (1, False)
    save_layout(path, [[list(row) for row in rows] for _ in range(count)], side_by_side)


# ---- Views: presets and the user's own layouts, in the order the bar shows them ----
#
# A page with presets keeps, next to its layout, the list of views the view bar
# shows and the one picked::
#
#     {"layout": [...], "side_by_side": false,      # what resolve_layout reads
#      "current": "overview",
#      "views": [{"name": "overview", "in_bar": true},            # a preset
#                {"name": "custom-1", "label": "Volcano + PCA",   # the user's own
#                 "rows": [["volcano", "pca"]], "in_bar": true}]}
#
# A preset's rows always come from the page, so a changed preset reaches every
# workspace; it cannot be edited, only duplicated. A preset the stored list does
# not name yet (added to the page later) is appended to the bar. The picked
# view's rows are stored as the layout of every experiment, so pages that only
# call resolve_layout render it unchanged.

CUSTOM_PREFIX = "custom-"


def _presets_or_default(presets: Sequence[Dict[str, Any]], default_layout) -> List[Dict[str, Any]]:
    if presets:
        return list(presets)
    return [{"name": "default", "label": "Default", "layout": default_layout}]


def load_views(
    path: Path,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
) -> Dict[str, Any]:
    """The views of a page: ``{"views", "current", "experiments", "side_by_side"}``.

    Each view is ``{"name", "label", "rows", "preset", "in_bar", "help"?}`` with
    the rows the page can render. A layout stored before views existed becomes
    the current view: the preset it matches, else a view of the user's own.
    """
    presets = _presets_or_default(presets, default_layout)
    known = {c["name"] for c in components}
    by_name = {p["name"]: p for p in presets}

    def preset_view(p: Dict[str, Any], in_bar: bool = True) -> Dict[str, Any]:
        view = {"name": p["name"], "label": p.get("label", p["name"]),
                "rows": _known_rows(p["layout"], known), "preset": True, "in_bar": in_bar}
        if p.get("help"):
            view["help"] = p["help"]
        return view

    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        data = {}
    layout, side_by_side = resolve_layout(path, components, presets[0]["layout"]) if data else (
        [_known_rows(presets[0]["layout"], known)], False)

    views: List[Dict[str, Any]] = []
    seen = set()
    for entry in data.get("views") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        name = entry["name"]
        if name in seen:
            continue
        in_bar = bool(entry.get("in_bar", True))
        if name in by_name:
            views.append(preset_view(by_name[name], in_bar))
        elif name.startswith(CUSTOM_PREFIX) and isinstance(entry.get("rows"), list):
            rows = _known_rows([r for r in entry["rows"] if isinstance(r, list)], known)
            if not rows:
                continue
            views.append({"name": name, "label": str(entry.get("label") or name), "rows": rows,
                          "preset": False, "in_bar": in_bar})
        else:
            continue
        seen.add(name)
    # Presets new to this file go to the end of the bar
    missing = [p for p in presets if p["name"] not in seen]
    in_bar_count = sum(v["in_bar"] for v in views)
    for p in missing:
        views.insert(in_bar_count, preset_view(p))
        in_bar_count += 1

    names = [v["name"] for v in views]
    current = data.get("current")
    if current not in names:
        # A file without views: the stored layout is a preset or the user's own
        current = match_preset(layout, presets, components)
        if current is None and data.get("layout") is not None:
            custom = {"name": CUSTOM_PREFIX + "1", "label": "My layout", "rows": layout[0],
                      "preset": False, "in_bar": True}
            views.insert(sum(v["in_bar"] for v in views), custom)
            current = custom["name"]
        current = current or names[0]
    return {"views": views, "current": current, "experiments": max(1, len(layout)),
            "side_by_side": side_by_side}


def save_views(path: Path, state: Dict[str, Any]) -> None:
    """Store ``state`` (as ``load_views`` returns it) and the current view's layout."""
    views = state["views"]
    current = next((v for v in views if v["name"] == state["current"]), views[0])
    experiments = max(1, int(state.get("experiments", 1)))
    stored = []
    for v in views:
        entry: Dict[str, Any] = {"name": v["name"], "in_bar": bool(v.get("in_bar", True))}
        if not v.get("preset"):
            entry["label"] = v["label"]
            entry["rows"] = v["rows"]
        stored.append(entry)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "layout": [[list(r) for r in current["rows"]] for _ in range(experiments)],
        "side_by_side": bool(state.get("side_by_side")) and experiments == 2,
        "current": current["name"],
        "views": stored,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def validate_views(
    state: Any,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    max_experiments: int = MAX_EXPERIMENTS,
    max_columns: int = MAX_COLUMNS,
) -> str:
    """Return why the views sent by the editor cannot be saved, or '' if they can.

    Presets are checked by name only: their rows always come from the page.
    """
    presets = _presets_or_default(presets, default_layout)
    preset_names = {p["name"] for p in presets}
    if not isinstance(state, dict) or not isinstance(state.get("views"), list) or not state["views"]:
        return "No views"
    names = set()
    labels = {p["label"].lower() for p in presets}
    for view in state["views"]:
        if not isinstance(view, dict) or not isinstance(view.get("name"), str):
            return "A view without a name"
        name = view["name"]
        if name in names:
            return 'The view "%s" is listed twice' % name
        names.add(name)
        if name in preset_names:
            continue
        if not name.startswith(CUSTOM_PREFIX):
            return 'Unknown view "%s"' % name
        label = str(view.get("label") or "").strip()
        if not label:
            return "Every view needs a name"
        if label.lower() in labels:
            return 'Two views are called "%s"' % label
        labels.add(label.lower())
        error = validate_layout([view.get("rows")], components, 1, max_columns)
        if error:
            return "%s: %s" % (label, error.replace("Experiment 1", "the view").replace(" in experiment 1", ""))
    missing = preset_names - names
    if missing:
        return 'A ready-made view is missing: "%s"' % sorted(missing)[0]
    if state.get("current") not in names:
        return "The selected view is not in the list"
    experiments = state.get("experiments", 1)
    if not isinstance(experiments, int) or not 1 <= experiments <= max_experiments:
        return "Between 1 and %d runs can be shown" % max_experiments
    return ""


def select_view(
    path: Path,
    name: str,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
) -> bool:
    """Make ``name`` the current view; False if there is no such view."""
    state = load_views(path, components, presets, default_layout)
    if name not in {v["name"] for v in state["views"]}:
        return False
    state["current"] = name
    save_views(path, state)
    return True
