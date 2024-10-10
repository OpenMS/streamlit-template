import streamlit as st
from src.common.common import page_setup
from src.Workflow import Workflow


params = page_setup()

wf = Workflow()

st.title(wf.name)

wf.show_execution_section()


