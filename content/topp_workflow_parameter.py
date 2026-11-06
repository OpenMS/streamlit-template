import streamlit as st
from src.common.common import page_setup
from src.Workflow import Workflow


params = page_setup()

wf = Workflow()

wf.show_parameter_section()

# Straight on to the Run page, which starts the workflow at once
wf.show_run_button("content/topp_workflow_execution.py", label="Run workflow")
