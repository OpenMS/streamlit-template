"""Layout manager: users arrange a page's components, the page renders them.

A page that shows several components defines a catalog of named components
and a renderer per name. A Layout Manager page puts the drag-and-drop editor in
front of the catalog; the page reads the saved layout and renders it::

    # content/viewer_layout.py
    layout_editor(LAYOUT_PATH, COMPONENTS, DEFAULT_LAYOUT, key="viewer_layout")

    # content/viewer.py
    layout, _ = resolve_layout(LAYOUT_PATH, COMPONENTS, DEFAULT_LAYOUT)
    render_layout(layout[0], {"peak_map": draw_peak_map, "spectrum": draw_spectrum})

A Viewer that compares datasets (runs, files, comparisons) lets users add
experiments and renders each below its own dataset selector::

    layout, side_by_side = resolve_layout(LAYOUT_PATH, COMPONENTS, DEFAULT_LAYOUT)
    render_experiments(
        layout, side_by_side, {"run1": "Run 1", "run2": "Run 2"},
        lambda dataset, index: renderers_for(dataset, index), key="viewer",
        buttons=lambda i: layout_button(
            LAYOUT_PATH, COMPONENTS, DEFAULT_LAYOUT, key="viewer_layout",
            max_experiments=MAX_EXPERIMENTS) if i == 0 else None,
    )

A page with ready-made layouts (presets) draws ``view_bar`` instead of a
layout button: as many views as fit in one row, the rest in More, and ✏️,
which opens ``views_editor``, where users order the views, keep some out of
the bar, and make views of their own (presets are duplicated, not changed)::

    view_bar(LAYOUT_PATH, COMPONENTS, PRESETS, DEFAULT_LAYOUT, key="viewer_view")
    layout, side_by_side = resolve_layout(LAYOUT_PATH, COMPONENTS, DEFAULT_LAYOUT)

The first preset's layout should be ``DEFAULT_LAYOUT``. The bar ends in +,
which opens the editor on a new view that starts as a copy of the current one.

Give all components of one experiment the same OpenMS-Insight state,
``experiment_state(key, index, dataset_id)``, so a selection stays when the
user switches views; side-by-side experiments keep their own.

A component that shows results only some runs have names the analysis it
needs (``"needs": "identification"``). Pass the analyses the shown run has as
``view_bar(available=...)``: views it cannot show are drawn disabled, and a
click offers ``unavailable_options`` (run the missing analysis, add files,
bring in another run). ``render_layout``/``render_experiments`` draw a note
with the same offer for such a component in a view of the user's own.

Pass ``view_bar(states=lambda i: experiment_state(...))`` and give each
Insight plot ``zoom_identifier=zoom_identifier(name)``: a view of the user's
own then keeps the zoom and selection of each experiment as its defaults
(📌 stores them, ↺ brings them back, opening the view applies them).

``layout_presets`` is the earlier, simpler selector of presets.

``layout.py`` is Streamlit-free; ``ui.py`` holds the editor and the grid.
Ported from FLASHApp's Layout Manager.
"""

from src.layout_manager.layout import (
    ANNOTATIONS_PREFIX,
    ASSISTANT,
    MAX_COLUMNS,
    MAX_EXPERIMENTS,
    VIEW_EXTRAS,
    ZOOM_PREFIX,
    annotations_identifier,
    apply_defaults,
    apply_preset,
    by_assistant,
    capture_defaults,
    clean_defaults,
    differs_from_defaults,
    explanation,
    has_defaults,
    clear_layout,
    load_layout,
    load_views,
    match_preset,
    missing_analyses,
    needs,
    normalize_zoom,
    read_only,
    resolve_layout,
    save_layout,
    save_views,
    select_view,
    set_view_defaults,
    validate_layout,
    validate_views,
    view_runs,
    zoom_identifier,
)
from src.layout_manager.ui import (
    experiment_state,
    layout_button,
    layout_editor,
    layout_presets,
    missing_analysis_dialog,
    missing_note,
    render_experiments,
    render_layout,
    request_analysis,
    selected_datasets,
    view_bar,
    views_editor,
)

__all__ = [
    "ANNOTATIONS_PREFIX",
    "ASSISTANT",
    "MAX_COLUMNS",
    "MAX_EXPERIMENTS",
    "VIEW_EXTRAS",
    "ZOOM_PREFIX",
    "annotations_identifier",
    "apply_defaults",
    "apply_preset",
    "by_assistant",
    "capture_defaults",
    "clean_defaults",
    "clear_layout",
    "differs_from_defaults",
    "experiment_state",
    "explanation",
    "has_defaults",
    "layout_button",
    "layout_editor",
    "layout_presets",
    "load_layout",
    "load_views",
    "match_preset",
    "missing_analyses",
    "missing_analysis_dialog",
    "missing_note",
    "needs",
    "normalize_zoom",
    "read_only",
    "render_experiments",
    "render_layout",
    "request_analysis",
    "resolve_layout",
    "save_layout",
    "save_views",
    "select_view",
    "selected_datasets",
    "set_view_defaults",
    "validate_layout",
    "validate_views",
    "view_bar",
    "view_runs",
    "views_editor",
    "zoom_identifier",
]
