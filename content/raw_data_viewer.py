from pathlib import Path

import streamlit as st

from src.common.common import page_setup
from src import view
from src.layout_manager.viewer import DatasetKind, ViewerSpec, show_viewer

# Components of this page, arranged in the views of the view bar
COMPONENTS = [
    {"name": "peak_map", "label": "Peak map (MS1)", "group": "Plots"},
    {"name": "spectrum", "label": "Spectra (MS1 + MS2)", "group": "Plots"},
    {"name": "chromatograms", "label": "Chromatograms (MS1)", "group": "Plots"},
]
DEFAULT_LAYOUT = [["peak_map"], ["spectrum"], ["chromatograms"]]
# Ready-made views; users reorder them and add their own with ✏️
PRESETS = [
    {"name": "all", "label": "All", "layout": DEFAULT_LAYOUT, "help": "Peak map, spectra and chromatograms."},
    {"name": "peak_map", "label": "Peak map", "layout": [["peak_map"]]},
    {"name": "spectra", "label": "Spectra", "layout": [["spectrum"]]},
    {"name": "chromatograms", "label": "Chromatograms", "layout": [["chromatograms"]]},
]
RENDERERS = {
    "peak_map": view.view_peak_map,
    "spectrum": view.view_spectrum,
    "chromatograms": view.view_bpc_tic,
}


params = page_setup()

st.title("View raw MS data")

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

def add_files_button(ctx=None) -> None:
    """Opens the upload page; drawn beside the file selector."""
    if st.button("Add files", icon="➕", key="raw_data_viewer_add"):
        st.switch_page(Path("content", "file_upload.py"))


def load_file(ctx) -> None:
    """Load the shown file for src/view.py, only when it changed (every view switch reruns the page)."""
    st.session_state["view_selected_file"] = ctx.dataset
    mzml = Path(st.session_state.workspace, "mzML-files", ctx.dataset)
    loaded = (str(mzml), mzml.stat().st_mtime_ns if mzml.exists() else None)
    if st.session_state.get("view_loaded_file") != loaded or "view_spectra" not in st.session_state:
        view.get_df(mzml)
        st.session_state["view_loaded_file"] = loaded


def no_files() -> None:
    st.info("No mzML files in this workspace yet.")
    add_files_button()


# The page reads top to bottom: the file shown (with what acts on it), the
# view bar, then the components. A link to a view (🔗) names the file it shows.
FILES = DatasetKind(
    name="file", components=COMPONENTS, presets=PRESETS, default_layout=DEFAULT_LAYOUT,
    views_path=Path(st.session_state.workspace, "layouts", "raw_data_viewer.json"),
    renderers=lambda ctx: RENDERERS, labels={c["name"]: c["label"] for c in COMPONENTS},
    before=load_file, states=None, link=True, view_key="raw_data_viewer_view",
    # One file is loaded at a time, so the page shows one experiment
    max_experiments=1, dataset_label="file", target="this page",
    help_text="Order the views, keep some out of the bar, or make your own, then press **Save**.",
)
show_viewer(ViewerSpec(
    key="raw_data_viewer", datasets={name: name for name in file_options}, kinds=[FILES],
    label="File", buttons=add_files_button, empty=no_files,
))
