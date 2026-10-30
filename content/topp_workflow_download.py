import streamlit as st
from src.common.common import page_setup
from src.Workflow import Workflow


params = page_setup()

wf = Workflow()

st.title("Export Results" if st.session_state.location == "local" else "Download Results")

wf.show_results_download_section()
