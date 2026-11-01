import streamlit as st
from pathlib import Path
import json
# For some reason the windows version only works if this is imported here
import pyopenms

if "settings" not in st.session_state:
        with open("settings.json", "r") as f:
            st.session_state.settings = json.load(f)

if __name__ == '__main__':
    # A local install exports results to a folder instead of downloading them.
    export = "Export" if not st.session_state.settings["online_deployment"] else "Download"
    pages = {
        str(st.session_state.settings["app-name"]) : [
            st.Page(Path("content", "quickstart.py"), title="Quickstart", icon="👋"),
            st.Page(Path("content", "documentation.py"), title="Documentation", icon="📖"),
        ],
        "pyOpenMS Toolbox": [
            st.Page(Path("content", "digest.py"), title="In Silico Digest", icon="✂️"),
            st.Page(Path("content", "peptide_mz_calculator.py"), title="m/z Calculator", icon="⚖️"),
            st.Page(Path("content", "isotope_pattern_generator.py"), title="Isotopic Pattern Calculator", icon="📶"),
            st.Page(Path("content", "fragmentation.py"), title="Fragment Ion Generation", icon="💥"),
        ],
        "TOPP Workflow Framework": [
            st.Page(Path("content", "topp_workflow_file_upload.py"), title="File Upload", icon="📁"),
            st.Page(Path("content", "topp_workflow_parameter.py"), title="Configure", icon="⚙️"),
            st.Page(Path("content", "topp_workflow_execution.py"), title="Run", icon="🚀"),
            st.Page(Path("content", "topp_workflow_results.py"), title="Results", icon="📊"),
            st.Page(Path("content", "topp_workflow_download.py"), title=export, icon="⬇️" if export == "Download" else "📤"),
        ],
        "pyOpenMS Workflow" : [
            st.Page(Path("content", "file_upload.py"), title="File Upload", icon="📂"),
            st.Page(Path("content", "raw_data_viewer.py"), title="View MS data", icon="👀"),
            st.Page(Path("content", "run_example_workflow.py"), title="Run Workflow", icon="⚙️"),
            st.Page(Path("content", "download_section.py"), title=f"{export} Results", icon="⬇️" if export == "Download" else "📤"),
        ],
        "Others Topics": [
            st.Page(Path("content", "simple_workflow.py"), title="Simple Workflow", icon="⚙️"),
            st.Page(Path("content", "run_subprocess.py"), title="Run Subprocess", icon="🖥️"),
        ]
    }

    # Workspace sync with an online workspace (off unless enabled in settings.json).
    # It is opened from its sidebar panel, so its menu entry is hidden: this
    # Streamlit cannot register a page without listing it.
    sync = st.session_state.settings.get("workspace_sync", {}).get("enabled")
    if sync:
        pages["Others Topics"].append(
            st.Page(Path("content", "workspace_sync.py"), title="Workspace Sync", icon="🔄")
        )

    pg = st.navigation(pages)
    if sync:
        st.html('<style>[data-testid="stSidebarNav"] li:has(a[href$="/workspace_sync"])'
                '{display: none;}</style>')
    pg.run()
