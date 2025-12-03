import streamlit as st
from src.common.common import page_setup
from src.WorkflowTest import WorkflowTest

params = page_setup()
wf = WorkflowTest()

st.title("Upload mzML files")
wf.show_file_upload_section()  # 이 함수가 파일 업로드 및 workspace에 저장 처리