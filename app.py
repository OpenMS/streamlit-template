import json
import asyncio
import streamlit as st
from pathlib import Path

def ensure_event_loop():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

ensure_event_loop()

def load_settings():
    settings_path = Path(__file__).parent / "settings.json" 
    if not settings_path.exists():
        st.error("⚠️ Error: 'settings.json' is missing! Using default settings.")
        return {
            "app-name": "Default App",
            "version": "1.0.0",
            "analytics": {"google-analytics": {"enabled": False, "tag": ""}},
        }
    with open(settings_path, "r") as f:
        return json.load(f)

if "settings" not in st.session_state:
    st.session_state.settings = load_settings()
if "current_page" not in st.session_state:
    st.session_state.current_page = None

def main():
    pages = {
        str(st.session_state.settings.get("app-name", "My App")): [
            ("content/quickstart.py", "Quickstart", "👋"),
            ("content/documentation.py", "Documentation", "📖"),
        ],
        "TOPP Workflow Framework": [
            ("content/topp_workflow_file_upload.py", "File Upload", "📁"),
            ("content/topp_workflow_parameter.py", "Configure", "⚙️"),
            ("content/topp_workflow_execution.py", "Run", "🚀"),
            ("content/topp_workflow_results.py", "Results", "📊"),
        ],
        "pyOpenMS Workflow": [
            ("content/file_upload.py", "File Upload", "📂"),
            ("content/raw_data_viewer.py", "View MS data", "👀"),
            ("content/run_example_workflow.py", "Run Workflow", "⚙️"),
            ("content/download_section.py", "Download Results", "⬇️"),
        ],
        "Others Topics": [
            ("content/simple_workflow.py", "Simple Workflow", "⚙️"),
            ("content/run_subprocess.py", "Run Subprocess", "🖥️"),
        ],
    }

    st.sidebar.title("Navigation")

    selected_page = None
    for category, items in pages.items():
        with st.sidebar.expander(category, expanded=False):
            for page_path, page_title, icon in items:
                if st.sidebar.button(f"{icon} {page_title}", key=page_path):
                    selected_page = page_path

    if selected_page:
        st.session_state.current_page = selected_page

    if st.session_state.current_page:
        st.write(f"Loading page: {st.session_state.current_page}")

if __name__ == "__main__":
    main()
