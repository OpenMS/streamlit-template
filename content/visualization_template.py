"""Linked Grid Demo — a self-contained showcase of the reusable OpenMS-Insight grid.

Exercises the full visualization stack on small example parquet under
``example-data/insight/``: a ``Table <-> LinePlot <-> Heatmap <-> SequenceView`` linked grid,
the :class:`~src.view.grid.LayoutManager` (edit/save/upload the layout), and the
multi-experiment + side-by-side wrapping owned by
:func:`~src.common.common.show_linked_grid`.

The four panels cross-link through one shared StateManager per experiment:
- click a row in the Spectrum table -> sets ``spectrum`` (= ``scan_id``)
- the Spectrum plot, Peak map and Sequence view all filter by ``spectrum``
- clicking a peak (in the plot / heatmap / sequence view) sets ``peak`` (= ``peak_id``)
"""

from pathlib import Path

import streamlit as st

from src.common.common import page_setup, save_params, show_linked_grid
from src.workflow.FileManager import FileManager
from src.view.grid import LayoutManager
from openms_insight import Table, LinePlot, Heatmap, SequenceView

params = page_setup()

st.title("🔗 Linked Grid Demo")
st.markdown(
    "A demo of the reusable OpenMS-Insight linked grid built on the streamlit-template "
    "`src/view/grid.py` module. Click a row in the **Spectrum table** to drive the linked "
    "**Spectrum plot**, **Peak map** and **Sequence view**; click a peak to cross-highlight it."
)

# Example fixtures shipped with the template.
DATA = Path("example-data", "insight")

# Per-workspace results store + a dedicated Insight cache dir inside the workspace.
fm = FileManager(
    st.session_state.workspace, cache_path=Path(st.session_state.workspace, "cache")
)
cache = str(Path(st.session_state.workspace, "cache", "insight"))

# Component vocabulary for the LayoutManager (human label <-> internal name).
OPTIONS = ["Spectrum table", "Spectrum plot", "Peak map", "Sequence view"]
NAMES = ["spectra_table", "spectrum_plot", "peak_map", "sequence_view"]


def builders():
    """Return the comp_name -> () -> BaseComponent factory map for one experiment."""
    return {
        "spectra_table": lambda: Table(
            cache_id="demo_spectra",
            data_path=str(DATA / "spectra.parquet"),
            cache_path=cache,
            interactivity={"spectrum": "scan_id"},
            index_field="scan_id",
            default_row=0,
            title="Spectrum Table",
        ),
        "spectrum_plot": lambda: LinePlot(
            cache_id="demo_spectrum_plot",
            data_path=str(DATA / "peaks.parquet"),
            cache_path=cache,
            filters={"spectrum": "scan_id"},
            interactivity={"peak": "peak_id"},
            x_column="mass",
            y_column="intensity",
            highlight_column="is_annotated",
            annotation_column="ion_label",
            title="MS/MS Spectrum",
        ),
        "peak_map": lambda: Heatmap(
            cache_id="demo_peak_map",
            data_path=str(DATA / "heat.parquet"),
            cache_path=cache,
            x_column="rt",
            y_column="mass",
            intensity_column="intensity",
            interactivity={"spectrum": "scan_id", "peak": "peak_id"},
            title="Peak Map",
        ),
        "sequence_view": lambda: SequenceView(
            cache_id="demo_seq",
            sequence_data_path=str(DATA / "sequences.parquet"),
            peaks_data_path=str(DATA / "peaks.parquet"),
            cache_path=cache,
            filters={"spectrum": "scan_id"},
            interactivity={"peak": "peak_id"},
            deconvolved=True,
            title="Fragment Coverage",
        ),
    }


# Default layout used when nothing is saved (one experiment, 2x2 grid).
DEFAULT_LAYOUT = [["spectra_table", "spectrum_plot"], ["peak_map", "sequence_view"]]

tab_view, tab_layout = st.tabs(["Viewer", "Layout Manager"])

lm = LayoutManager(
    OPTIONS, NAMES, store=fm, layout_id="demo_layout", session_prefix="demo"
)

with tab_layout:
    lm.render()

with tab_view:
    saved = lm.get_layout()
    layout, side_by_side = saved if saved else ([DEFAULT_LAYOUT], False)
    show_linked_grid(layout, builders(), tool="demo", side_by_side=side_by_side)

save_params(params)
