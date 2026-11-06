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

``layout.py`` is Streamlit-free; ``ui.py`` holds the editor and the grid.
Ported from FLASHApp's Layout Manager.
"""

from src.layout_manager.layout import (
    MAX_COLUMNS,
    MAX_EXPERIMENTS,
    clear_layout,
    load_layout,
    resolve_layout,
    save_layout,
    validate_layout,
)
from src.layout_manager.ui import (
    layout_button,
    layout_editor,
    render_experiments,
    render_layout,
    selected_datasets,
)

__all__ = [
    "MAX_COLUMNS",
    "MAX_EXPERIMENTS",
    "clear_layout",
    "layout_button",
    "layout_editor",
    "load_layout",
    "render_experiments",
    "render_layout",
    "resolve_layout",
    "save_layout",
    "selected_datasets",
    "validate_layout",
]
