from pathlib import Path

import streamlit as st

from src.common.common import page_setup
from src import view


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


    tabs = st.tabs(
        ["📈 Peak map (MS1)", "📈 Spectra (MS1 + MS2)", "📈 Chromatograms (MS1)"]
    )
    with tabs[0]:
        view.view_peak_map()
    with tabs[1]:
        view.view_spectrum()
    with tabs[2]:
        view.view_bpc_tic()
