import streamlit as st
from pathlib import Path
import json
# For some reason the windows version only works if this is imported here
import pyopenms
import os
import time
import pyautogui
import psutil
import platform

if "settings" not in st.session_state:
    with open("settings.json", "r") as f:
        st.session_state.settings = json.load(f)

if __name__ == '__main__':
    pages = {
        str(st.session_state.settings["app-name"]) : [
            st.Page(Path("content", "quickstart.py"), title="Quickstart", icon="👋"),
            st.Page(Path("content", "documentation.py"), title="Documentation", icon="📖"),
        ],
        "TOPP Workflow Framework": [
            st.Page(Path("content", "topp_workflow_file_upload.py"), title="File Upload", icon="📁"),
            st.Page(Path("content", "topp_workflow_parameter.py"), title="Configure", icon="⚙️"),
            st.Page(Path("content", "topp_workflow_execution.py"), title="Run", icon="🚀"),
            st.Page(Path("content", "topp_workflow_results.py"), title="Results", icon="📊"),
        ],
        "pyOpenMS Workflow" : [
            st.Page(Path("content", "file_upload.py"), title="File Upload", icon="📂"),
            st.Page(Path("content", "raw_data_viewer.py"), title="View MS data", icon="👀"),
            st.Page(Path("content", "run_example_workflow.py"), title="Run Workflow", icon="⚙️"),
            st.Page(Path("content", "download_section.py"), title="Download Results", icon="⬇️"),
        ],
        "Others Topics": [
            st.Page(Path("content", "simple_workflow.py"), title="Simple Workflow", icon="⚙️"),
            st.Page(Path("content", "run_subprocess.py"), title="Run Subprocess", icon="🖥️"),
        ]
    }

    pg = st.navigation(pages)
    pg.run()

def close_app():
    """
    Closes the Streamlit app by terminating the Python process and
    attempting to close the browser tab with keystrokes.
    """
    with st.spinner("Shutting down..."):
        time.sleep(3)  # give the user a small window to see the spinner

        # Attempt to close the current browser tab (keystroke-based)
        try:
            if platform.system() == "Darwin":
                # macOS typically uses 'command + w'
                pyautogui.hotkey('command', 'w')
            else:
                # Windows/Linux typically use 'ctrl + w'
                pyautogui.hotkey('ctrl', 'w')
        except Exception as error:
            st.warning(
                "We tried closing the browser window, but failed. "
                "You may need to close it manually. For macOS, ensure that:"
                " System Preferences → Security & Privacy → Accessibility → Terminal is checked."
            )

        # Terminate the Streamlit python process
        pid = os.getpid()
        p = psutil.Process(pid)
        p.terminate()

    # Place the “Stop/Close” button in the sidebar
with st.sidebar:
    st.write("")  # just an empty line for spacing
    if st.button("Stop/Close"):
        st.write("Terminating the app... please wait.")
        close_app()