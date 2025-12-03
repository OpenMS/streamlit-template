import streamlit as st
from src.common.common import page_setup
from src.Workflow import Workflow


params = page_setup()

wf = Workflow()

wf.show_file_upload_section()

