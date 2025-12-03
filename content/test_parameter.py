import streamlit as st
from src.common.common import page_setup
from src.WorkflowTest import WorkflowTest


params = page_setup()

wf = WorkflowTest()

wf.show_parameter_section()
