import streamlit as st
from src.common.common import page_setup
from src.Workflow import Workflow


params = page_setup()

wf = Workflow()

# A finished run links to its results
wf.show_execution_section(results_page="content/topp_workflow_results.py", results_label="Open results")
