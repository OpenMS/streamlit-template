from pathlib import Path

import streamlit as st

from src.common.common import page_setup
from src import view
from src.layout_manager import layout_button, render_layout, resolve_layout

# Components of this page, arranged with Edit layout
COMPONENTS = [
    {"name": "peak_map", "label": "Peak map (MS1)", "group": "Plots"},
    {"name": "spectrum", "label": "Spectra (MS1 + MS2)", "group": "Plots"},
    {"name": "chromatograms", "label": "Chromatograms (MS1)", "group": "Plots"},
]
DEFAULT_LAYOUT = [["peak_map"], ["spectrum"], ["chromatograms"]]
RENDERERS = {
    "peak_map": view.view_peak_map,
    "spectrum": view.view_spectrum,
    "chromatograms": view.view_bpc_tic,
}


params = page_setup()

st.title("View raw MS data")

# File selection can not be in fragment since it influences the subsequent sections
cols = st.columns(3)

mzML_dir = Path(st.session_state.workspace, "mzML-files")
# Only mzML files: the directory also holds external_files.txt and, in the
# shipped demo workspaces, a .gitkeep that pyOpenMS cannot parse.
file_options = [f.name for f in mzML_dir.iterdir() if f.suffix.lower() == ".mzml"]

# Check if local files are available
external_files = Path(mzML_dir, "external_files.txt")
if external_files.exists():
    with open(external_files, "r") as f_handle:
        external_files = f_handle.readlines()
        external_files = [f.strip() for f in external_files]
        file_options += external_files

selected_file = cols[0].selectbox(
    "choose file",
    file_options,
    key="view_selected_file"
)
if selected_file:
    view.get_df(Path(st.session_state.workspace, "mzML-files", selected_file))


    layout_path = Path(st.session_state.workspace, "layouts", "raw_data_viewer.json")
    with cols[1].container(height="stretch", vertical_alignment="bottom"):
        layout_button(
            layout_path, COMPONENTS, DEFAULT_LAYOUT, key="raw_data_viewer_layout",
            help_text="Drag components into the grid (up to 3 per row), then press **Save**.",
            target="this page",
        )
    layout, _ = resolve_layout(layout_path, COMPONENTS, DEFAULT_LAYOUT)
    render_layout(layout[0], RENDERERS, {c["name"]: c["label"] for c in COMPONENTS})
