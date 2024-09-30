from pathlib import Path

import streamlit as st
import pandas as pd

from src.common.common import page_setup, save_params, v_space, show_table, TK_AVAILABLE, tk_directory_dialog
from src import fileupload

params = page_setup()

st.title("File Upload")

tabs = ["mzML-File Upload", "Fasta File Upload",  "Example Data"]
if st.session_state.location == "local":
    tabs.append("Files from local folder")

tabs = st.tabs(tabs)

with tabs[0]:
    with st.form("mzML-upload", clear_on_submit=True):
        files = st.file_uploader(
            "mzML files", accept_multiple_files=(st.session_state.location == "local")
        )
        cols = st.columns(3)
        if cols[1].form_submit_button("Add files to workspace", type="primary"):
            if files:
                fileupload.save_uploaded_mzML(files)
            else:
                st.warning("Select files first.")

with tabs[1]:
    with st.form("fasta-upload", clear_on_submit=True):
        files = st.file_uploader(
            "fasta files", accept_multiple_files=(st.session_state.location == "local")
        )
        cols = st.columns(3)
        if cols[1].form_submit_button("Add files to workspace", type="primary"):
            if files:
                fileupload.save_uploaded_fasta(files)
            else:
                st.warning("Select files first.")

# Example mzML files
with tabs[2]:
    st.markdown("Short information text on example data.")
    cols = st.columns(3)
    if cols[1].button("Load Example Data", type="primary"):
        fileupload.load_example_mzML_files()

# Local file upload option: via directory path
if st.session_state.location == "local":
    with tabs[2]:
        st_cols = st.columns([0.05, 0.95], gap="small")
        with st_cols[0]:
            st.write("\n")
            st.write("\n")
            dialog_button = st.button("📁", key='local_browse', help="Browse for your local directory with MS data.", disabled=not TK_AVAILABLE)
            if dialog_button:
                st.session_state["local_dir"] = tk_directory_dialog("Select directory with your MS data", st.session_state["previous_dir"])
                st.session_state["previous_dir"] = st.session_state["local_dir"]
        with st_cols[1]:
            # with st.form("local-file-upload"):
            local_mzML_dir = st.text_input("path to folder with mzML files", value=st.session_state["local_dir"])
        # raw string for file paths
        local_mzML_dir = rf"{local_mzML_dir}"
        cols = st.columns([0.65, 0.3, 0.4, 0.25], gap="small")
        copy_button = cols[1].button("Copy files to workspace", type="primary", disabled=(local_mzML_dir == ""))
        use_copy = cols[2].checkbox("Make a copy of files", key="local_browse-copy_files", value=True, help="Create a copy of files in workspace.")
        if not use_copy:
                st.warning(
        "**Warning**: You have deselected the `Make a copy of files` option. "
        "This **_assumes you know what you are doing_**. "
        "This means that the original files will be used instead. "
    )
        if copy_button:
            fileupload.copy_local_mzML_files_from_directory(local_mzML_dir, use_copy)

mzML_dir = Path(st.session_state.workspace, "mzML-files")
fasta_dir = Path(st.session_state.workspace, "fasta-files")
if any(Path(mzML_dir).iterdir()):
    v_space(2)
    # Display all mzML files currently in workspace
    df = pd.DataFrame({"file name": [f.name for f in Path(mzML_dir).iterdir() if "external_files.txt" not in f.name]})
    df_fasta = pd.DataFrame({"file name": [f.name for f in Path(fasta_dir).iterdir() if "external_files.txt" not in f.name]})
    
    # Check if local files are available
    external_files = Path(mzML_dir, "external_files.txt")
    if external_files.exists():
        with open(external_files, "r") as f_handle:
            external_files = f_handle.readlines()
            external_files = [f.strip() for f in external_files]
            df = pd.concat([df, pd.DataFrame({"file name": external_files})], ignore_index=True)
    
    st.markdown("##### Files in current workspace:")
    show_table(df)
    show_table(df_fasta)
    v_space(1)
    # Remove files
    with st.expander("🗑️ Remove mzML files"):
        to_remove_mzML = st.multiselect(
            "select mzML files", options=[f.stem for f in sorted(mzML_dir.iterdir())]
        )
        c1, c2 = st.columns(2)
        if c2.button(
            "Remove **selected** mzML files", type="primary", disabled=not any(to_remove_mzML)
        ):
            params = fileupload.remove_selected_mzML_files(to_remove_mzML, params)
            save_params(params)
            st.rerun()

        if c1.button("⚠️ Remove **all** mzML files", disabled=not any(mzML_dir.iterdir())):
            params = fileupload.remove_all_mzML_files(params)
            save_params(params)
            st.rerun()
    #Remove fasta files 
    with st.expander("🗑️ Remove fasta files"):
        to_remove_fasta = st.multiselect(
            "select fasta files", options=[f.stem for f in sorted(fasta_dir.iterdir())]
        )
        c3, c4 = st.columns(2) #Change to c3 c4 maybe? 
        if c3.button(
            "Remove **selected** fasta files", type="primary", disabled=not any(to_remove_fasta)
        ):
            params = fileupload.remove_selected_fasta_files(to_remove_fasta, params)
            save_params(params)
            st.rerun()

        if c4.button("⚠️ Remove **all** fasta files", disabled=not any(fasta_dir.iterdir())):
            params = fileupload.remove_all_fasta_files(params)
            save_params(params)
            st.rerun()

save_params(params)
