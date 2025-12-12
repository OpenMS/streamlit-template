import streamlit as st
from pathlib import Path
import json
# For some reason the windows version only works if this is imported here
import pyopenms

if "settings" not in st.session_state:
        with open("settings.json", "r") as f:
            st.session_state.settings = json.load(f)

if __name__ == '__main__':
    pages = {
        "Workflow Test": [
             st.Page(Path("content", "test_fileupload.py"), title="File Upload", icon="📁"),
             st.Page(Path("content", "test_parameter.py"), title="Configure", icon="⚙️"),
             st.Page(Path("content", "test_execution.py"), title="Run", icon="🚀"),
             st.Page(Path("content", "test_results.py"), title="Results", icon="📊"),
        ],
    }

    pg = st.navigation(pages)
    pg.run()
