from pathlib import Path

import streamlit as st
import pandas as pd

from src.captcha_ import captcha_control
from src.common import page_setup, save_params, v_space, show_table
from src import fastaupload

params = page_setup()

# If run in hosted mode, show captcha as long as it has not been solved
if "controllo" not in st.session_state or params["controllo"] is False:
    # Apply captcha by calling the captcha_control function
    captcha_control()

st.title("fasta Upload")

tabs = ["File Upload", "Example Data"]
if st.session_state.location == "local":
    tabs.append("Files from local folder")

tabs = st.tabs(tabs)

with tabs[0]:
    with st.form("fasta-upload", clear_on_submit=True):
        files = st.file_uploader(
            "fasta file", accept_multiple_files=False
        )
        cols = st.columns(3)
        if cols[1].form_submit_button("Add files to workspace", type="primary"):
            if files:
                fastaupload.save_uploaded_fasta(files)
            else:
                st.warning("Select files first.")

# Example fasta files
with tabs[1]:
    st.markdown("sequence database for a minimal RNA experiment.")
    cols = st.columns(3)
    if cols[1].button("Load Example Data", type="primary"):
        fastaupload.load_example_fasta_files() #FIXME CHANGE FILES

fasta_dir = Path(st.session_state.workspace, "fasta-files")
if any(Path(fasta_dir).iterdir()):
    v_space(2)
    # Display all fasta files currently in workspace
    df = pd.DataFrame({"file name": [f.name for f in Path(fasta_dir).iterdir()]})
    st.markdown("##### fasta files in current workspace:")
    show_table(df)
    v_space(1)
    # Remove files
    with st.expander("🗑️ Remove fasta files"):
        to_remove = st.multiselect(
            "select fasta files", options=[f.stem for f in sorted(fasta_dir.iterdir())]
        )
        c1, c2 = st.columns(2)
        if c2.button(
            "Remove **selected**", type="primary", disabled=not any(to_remove)
        ):
            params = fastaupload.remove_selected_fasta_files(to_remove, params)
            save_params(params)
            st.rerun()

save_params(params)
