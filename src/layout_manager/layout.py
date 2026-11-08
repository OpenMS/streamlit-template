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
import math
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
# Keys of a view of the user's own that are kept as they are: views made by
# the AI assistant carry them ("by": "assistant", the runs shown, ...)
VIEW_EXTRAS = ("by", "runs", "explanation", "question", "created")


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
            view = {"name": name, "label": str(entry.get("label") or name), "rows": rows,
                    "preset": False, "in_bar": in_bar}
            view.update({k: entry[k] for k in VIEW_EXTRAS if k in entry})
            defaults = clean_defaults(entry.get("defaults"))
            if defaults:
                view["defaults"] = defaults
            views.append(view)
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
            entry.update({k: v[k] for k in VIEW_EXTRAS if k in v})
            if v.get("defaults"):
                entry["defaults"] = v["defaults"]
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


# ---- Analyses: which components a dataset's processing allows ----
#
# A component that shows results only some runs have (identifications after a
# deconvolution-only run, a group comparison) names the analysis it needs::
#
#     {"name": "volcano", "label": "Volcano plot", "needs": "comparison"}
#
# ``needs`` may be a list, all of which are needed. The page tells which
# analyses a dataset has (``available``); a view needing one it lacks is shown
# disabled in the view bar, and the component in a layout draws a note instead.


def needs(component: Dict[str, Any]) -> List[str]:
    """The analyses ``component`` needs (its ``needs``, as a list)."""
    value = component.get("needs")
    if not value:
        return []
    return [value] if isinstance(value, str) else list(value)


def missing_analyses(
    names: Any,
    components: Sequence[Dict[str, Any]],
    available: Optional[Any],
) -> List[str]:
    """The analyses the components ``names`` (or rows of them) need that are not ``available``.

    ``available`` None means everything is; the result keeps the order of first need.
    """
    if available is None:
        return []
    flat: List[str] = []
    for item in names or []:
        flat.extend(item if isinstance(item, list) else [item])
    by_name = {c["name"]: c for c in components}
    out: List[str] = []
    for name in flat:
        for need in needs(by_name.get(name, {})):
            if need not in available and need not in out:
                out.append(need)
    return out


def analysis_label(name: str, analyses: Optional[Dict[str, Any]] = None) -> str:
    """How messages name the analysis ``name``: its label in ``analyses``, else the name."""
    entry = (analyses or {}).get(name)
    if isinstance(entry, dict):
        return str(entry.get("label") or name)
    return str(entry or name)


def join_labels(labels: Sequence[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    labels = list(labels)
    if len(labels) < 2:
        return "".join(labels)
    return ", ".join(labels[:-1]) + " and " + labels[-1]


# ---- A view's zoom and selection ----
#
# A view of the user's own may keep a zoom and selection as its defaults: the
# page applies them when the view is opened, and the view bar's ↺ brings them
# back. One entry per experiment (index 0 is the first one shown)::
#
#     {"name": "custom-3", "label": "Ribosome", "rows": [...],
#      "defaults": [{"dataset": "run-1",                         # optional
#                    "selection": {"protein": "P12345", "scan@psm_table": 12},
#                    "zoom": {"spectrum": {"x": [400.0, 900.0]},
#                             "peak_map": {"x": [10.0, 20.0], "y": [400.0, 900.0]}}}]}
#
# ``selection`` holds the identifiers of the experiment's OpenMS-Insight
# ``StateManager`` (a private one as ``<identifier>@<component>``, see
# ``experiment_state``); pagination is never kept. ``zoom`` is keyed by
# component name; in the ``StateManager`` it lives under
# ``zoom_identifier(<component>)``, which the component is given as its
# ``zoom_identifier``. An axis left out shows its full extent. With
# ``dataset``, the selection is applied only while that dataset is shown (the
# zoom always is). Plain JSON, so a view can be written without a browser.

ZOOM_PREFIX = "zoom@"


ANNOTATIONS_PREFIX = "annotations@"


def annotations_identifier(component: str) -> str:
    """The ``StateManager`` identifier a view's point annotations for ``component`` are kept under.

    The value is ``{point_id: {"highlight": bool, "annotation": str}}``, the
    point ids being the component's own; pass it to the component's
    ``set_dynamic_annotations``.
    """
    return ANNOTATIONS_PREFIX + component


def _annotations(value: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """``value`` as point annotations (a dict of dicts with JSON values), or None."""
    if not isinstance(value, dict):
        return None
    out = {str(k): v for k, v in value.items() if isinstance(v, dict) and _plain(v)}
    return out or None


def zoom_identifier(component: str) -> str:
    """The ``StateManager`` identifier a component keeps its zoom under.

    Pass it as the OpenMS-Insight component's ``zoom_identifier``, so a view
    can keep and restore the component's zoom.
    """
    return ZOOM_PREFIX + component


def _range(value: Any) -> Optional[List[float]]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        low, high = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(low) and math.isfinite(high)) or low == high or (low == -1 and high == -1):
        return None
    return [min(low, high), max(low, high)]


def normalize_zoom(value: Any) -> Optional[Dict[str, List[float]]]:
    """A zoom as ``{"x": [lo, hi], "y": [lo, hi]}`` (axes optional), or None for the full view.

    Reads the heatmap's ``{"xRange", "yRange"}`` too, with ``[-1, -1]`` for no zoom.
    """
    if not isinstance(value, dict):
        return None
    zoom = {}
    for axis in ("x", "y"):
        r = _range(value.get(axis, value.get(axis + "Range")))
        if r is not None:
            zoom[axis] = r
    return zoom or None


def _is_pagination(identifier: str) -> bool:
    return identifier.endswith("_page")


def _plain(value: Any) -> bool:
    """Whether ``value`` survives a JSON round trip unchanged."""
    try:
        return json.loads(json.dumps(value)) == value
    except (TypeError, ValueError):
        return False


def capture_defaults(selections: Dict[str, Any], dataset: Optional[str] = None) -> Dict[str, Any]:
    """The defaults entry of one experiment, from its ``StateManager.get_all_selections()``."""
    selection: Dict[str, Any] = {}
    zoom: Dict[str, Any] = {}
    annotations: Dict[str, Any] = {}
    for identifier, value in (selections or {}).items():
        if not isinstance(identifier, str) or _is_pagination(identifier) or value is None:
            continue
        if identifier.startswith(ZOOM_PREFIX):
            normalized = normalize_zoom(value)
            if normalized:
                zoom[identifier[len(ZOOM_PREFIX):]] = normalized
        elif identifier.startswith(ANNOTATIONS_PREFIX):
            points = _annotations(value)
            if points:
                annotations[identifier[len(ANNOTATIONS_PREFIX):]] = points
        elif _plain(value):
            selection[identifier] = value
    entry: Dict[str, Any] = {}
    if dataset is not None:
        entry["dataset"] = dataset
    if selection:
        entry["selection"] = selection
    if zoom:
        entry["zoom"] = zoom
    if annotations:
        entry["annotations"] = annotations
    return entry


def has_defaults(view: Optional[Dict[str, Any]]) -> bool:
    """Whether ``view`` keeps a zoom or selection."""
    return any(_holds(e) for e in (view or {}).get("defaults") or [])


def _holds(entry: Dict[str, Any]) -> bool:
    return bool(entry.get("selection") or entry.get("zoom") or entry.get("annotations"))


def clean_defaults(defaults: Any) -> List[Dict[str, Any]]:
    """``defaults`` as stored, without what cannot be applied; [] if nothing is left."""
    if not isinstance(defaults, list):
        return []
    out: List[Dict[str, Any]] = []
    for entry in defaults[:MAX_EXPERIMENTS]:
        if not isinstance(entry, dict):
            out.append({})
            continue
        selection = entry.get("selection") if isinstance(entry.get("selection"), dict) else {}
        selection = {k: v for k, v in selection.items()
                     if isinstance(k, str) and not _is_pagination(k)
                     and not k.startswith((ZOOM_PREFIX, ANNOTATIONS_PREFIX))
                     and v is not None and _plain(v)}
        zoom = entry.get("zoom") if isinstance(entry.get("zoom"), dict) else {}
        zoom = {k: z for k, z in ((k, normalize_zoom(v)) for k, v in zoom.items()) if isinstance(k, str) and z}
        annotations = entry.get("annotations") if isinstance(entry.get("annotations"), dict) else {}
        annotations = {k: a for k, a in ((k, _annotations(v)) for k, v in annotations.items())
                       if isinstance(k, str) and a}
        clean: Dict[str, Any] = {}
        if isinstance(entry.get("dataset"), str):
            clean["dataset"] = entry["dataset"]
        if selection:
            clean["selection"] = selection
        if zoom:
            clean["zoom"] = zoom
        if annotations:
            clean["annotations"] = annotations
        out.append(clean)
    while out and not _holds(out[-1]):
        out.pop()
    return out


def selections_to_apply(entry: Dict[str, Any], dataset: Optional[str] = None) -> Dict[str, Any]:
    """What applying one experiment's defaults sets: identifier -> value.

    Every zoom the experiment's state holds and the entry does not name is
    reset (None) by the caller; see ``apply_defaults``. The selection is left
    out while another dataset than the entry's is shown.
    """
    values: Dict[str, Any] = {}
    same = entry.get("dataset") is None or dataset is None or entry.get("dataset") == dataset
    if same:
        values.update(entry.get("selection") or {})
        for component, points in (entry.get("annotations") or {}).items():
            values[annotations_identifier(component)] = points
    for component, zoom in (entry.get("zoom") or {}).items():
        values[zoom_identifier(component)] = zoom
    return values


def apply_defaults(state: Any, entry: Dict[str, Any], dataset: Optional[str] = None) -> bool:
    """Set one experiment's defaults on its ``StateManager``; True if anything changed.

    The saved selection, zoom and point annotations are set; a zoom or the
    annotations of a component the entry does not name are removed (full
    view, no annotations). Other identifiers stay as they are.
    """
    values = selections_to_apply(entry, dataset)
    changed = False
    for identifier in list(state.get_all_selections()):
        if identifier.startswith((ZOOM_PREFIX, ANNOTATIONS_PREFIX)) and identifier not in values:
            changed = state.clear_selection(identifier) or changed
    for identifier, value in values.items():
        current = state.get_selection(identifier)
        if identifier.startswith(ZOOM_PREFIX) and normalize_zoom(current) == value:
            continue
        changed = state.set_selection(identifier, value) or changed
    return changed


def differs_from_defaults(selections: Dict[str, Any], entry: Dict[str, Any],
                          dataset: Optional[str] = None) -> bool:
    """Whether the state shown is not (any more) the experiment's defaults."""
    for identifier, value in selections_to_apply(entry, dataset).items():
        current = selections.get(identifier)
        if identifier.startswith(ZOOM_PREFIX):
            if normalize_zoom(current) != value:
                return True
        elif current != value:
            return True
    values = selections_to_apply(entry, dataset)
    return any((k.startswith(ZOOM_PREFIX) and normalize_zoom(v) or k.startswith(ANNOTATIONS_PREFIX) and v)
               and k not in values for k, v in selections.items())


def set_view_defaults(
    path: Path,
    name: str,
    defaults: Optional[List[Dict[str, Any]]],
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
) -> bool:
    """Store ``defaults`` (None or [] removes them) on the view ``name``.

    False if there is no such view or it is a ready-made one, which keeps none.
    """
    state = load_views(path, components, presets, default_layout)
    view = next((v for v in state["views"] if v["name"] == name), None)
    if view is None or view.get("preset"):
        return False
    cleaned = clean_defaults(defaults)
    if cleaned:
        view["defaults"] = cleaned
    else:
        view.pop("defaults", None)
    save_views(path, state)
    return True
