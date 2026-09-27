import streamlit as st
from src.common.common import page_setup
from src.Workflow import Workflow


params = page_setup()

wf = Workflow()

st.title("Download Results")

wf.show_results_download_section()
