import streamlit as st
from src.common import page_setup
from st_pages import Page, show_pages
from pathlib import Path



def flashdeconvPages():
    show_pages([
        Page("pages/FLASHViewer.py", "FLASHViewer", "🏠"),
        Page("pages/FileUpload.py", "File Upload", "📁"),
        Page("pages/SequenceInput.py", "Sequence Input", "🧵"),
        Page("pages/LayoutManager.py", "Layout Manager", "⚙️"),
        Page("pages/FLASHDeconvViewer.py", "Viewer", "👀"),
    ])

def flashtagPages():
    show_pages([
        Page("pages/FLASHViewer.py", "FlashViewer", "🏠"),
        Page("pages/5_TOPP-Workflow.py", "Workflow", "⚙️"),
        Page("pages/FLASHTagViewer.py", "Viewer", "👀"),
    ])

def flashquantPages():
    show_pages([
        Page("pages/FLASHViewer.py", "FLASHViewer", "🏠"),
        Page("pages/FileUpload_FLASHQuant.py", "File Upload", "📁"),
        Page("pages/FLASHQuantViewer.py", "Viewer", "👀"),
    ])


page_names_to_funcs = {
    "FLASHTagViewer": flashtagPages,
    "FLASHDeconv": flashdeconvPages,
    "FLASHQuant": flashquantPages,
}


def onToolChange():
    if 'changed_tool_name' in st.session_state:
        st.session_state['tool_index'] = 0 if st.session_state.changed_tool_name == 'FLASHDeconv' else 1
        st.session_state['tool_index'] = 0


def content():
    # initializing the page
    page_setup("FLASHViewer")

    # main content
    st.markdown('#### FLASHViewer visualizes outputs from FLASH\* tools.')

    st.info("""
        **💡 How to run FLASHViewer**
        1. Go to the **⚙️ Workflow** page through the sidebar and run your analysis.
        2. Click the **👀 Viewer** page on the sidebar to view the results in detail.
        """)

    # sidebar to toggle between tools
    if 'tool_index' not in st.session_state:
        st.session_state['tool_index'] = 0
    # when entered into other page, key is resetting (emptied) - thus set the value with index
    # st.selectbox("Choose a tool", ['FLASHTagViewer', 'FLASHDeconv', 'FLASHQuant'], index=st.session_state.tool_index,
    st.selectbox("Choose a tool", ['FLASHTagViewer'], index=st.session_state.tool_index,
                 on_change=onToolChange(), key='changed_tool_name')
    page_names_to_funcs[st.session_state.changed_tool_name]()

    if Path("OpenMS-App.zip").exists():
        st.markdown("## Installation")
        with open("OpenMS-App.zip", "rb") as file:
            st.download_button(
                label="Download for Windows",
                data=file,
                file_name="OpenMS-App.zip",
                mime="archive/zip",
                type="primary",
            )


if __name__ == "__main__":
    content()