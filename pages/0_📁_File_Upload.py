from pathlib import Path

import streamlit as st
import pandas as pd

from src.common import *
from src.fileupload import *

params = page_setup()

# Make sure "selected-mzML-files" is in session state
if "selected-mzML-files" not in st.session_state:
    st.session_state["selected-mzML-files"] = params["selected-mzML-files"]

st.title("File Upload")

tabs = ["File Upload", "Example Data"]
if st.session_state.location == "local":
    tabs.append("Files from local folder")

tabs = st.tabs(tabs)

with tabs[0]:
    with st.form("mzML-upload", clear_on_submit=True):
        files = st.file_uploader(
            "mzML files", accept_multiple_files=(st.session_state.location == "local"))
        cols = st.columns(3)
        if cols[1].form_submit_button("Add files to workspace", type="primary"):
            save_uploaded_mzML(files)

# Example mzML files
with tabs[1]:
    st.markdown("Short information text about the example data.")
    cols = st.columns(3)
    if cols[1].button("Load Example Data", type="primary"):
        load_example_mzML_files()

# Local file upload option: via directory path
if st.session_state.location == "local":
    with tabs[2]:
        # with st.form("local-file-upload"):
        local_mzML_dir = st.text_input(
            "path to folder with mzML files")
        # raw string for file paths
        local_mzML_dir = r"{}".format(local_mzML_dir)
        cols = st.columns(3)
        if cols[1].button("Copy files to workspace", type="primary", disabled=(local_mzML_dir == "")):
            copy_local_mzML_files_from_directory(local_mzML_dir)

if any(Path(mzML_dir).iterdir()):
    v_space(2)
    # Display all mzML files currently in workspace
    df = pd.DataFrame(
        {"file name": [f.name for f in Path(mzML_dir).iterdir()]})
    st.markdown("##### mzML files in current workspace:")
    show_table(df)
    v_space(1)
    # Remove files
    with st.expander("🗑️ Remove mzML files"):
        to_remove = st.multiselect("select mzML files",
                                   options=[f.stem for f in sorted(mzML_dir.iterdir())])
        c1, c2 = st.columns(2)
        if c2.button("Remove **selected**", type="primary", disabled=not any(to_remove)):
            remove_selected_mzML_files(to_remove)
            st.experimental_rerun()

        if c1.button("⚠️ Remove **all**", disabled=not any(mzML_dir.iterdir())):
            remove_all_mzML_files()
            st.experimental_rerun()

save_params(params)
