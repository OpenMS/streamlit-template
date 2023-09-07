import streamlit as st
from src.common import defaultPageSetup
from st_pages import Page, show_pages


def flashdeconvPages():
    show_pages([
        Page("FLASHViewer.py", "FLASHViewer", "🏠"),
        Page("pages/FileUpload.py", "File Upload", "📁"),
        Page("pages/SequenceInput.py", "Sequence Input", "🧵"),
        Page("pages/LayoutManager.py", "Layout Manager", "⚙️"),
        Page("pages/FLASHDeconvViewer.py", "Viewer", "👀"),
    ])


def flashquantPages():
    show_pages([
        Page("FLASHViewer.py", "FLASHViewer", "🏠"),
        Page("pages/FileUpload_FLASHQuant.py", "File Upload", "📁"),
        Page("pages/FLASHQuantViewer.py", "Viewer", "👀"),
    ])


page_names_to_funcs = {
    "FLASHDeconv": flashdeconvPages,
    "FLASHQuant": flashquantPages,
}


def onToolChange():
    if 'changed_tool_name' in st.session_state:
        st.session_state['tool_index'] = 0 if st.session_state.changed_tool_name == 'FLASHDeconv' else 1


def content():
    # initializing the page
    defaultPageSetup("FLASHViewer")

    # main content
    st.markdown("""
        #### FLASHViewer visualizes outputs from [FLASHDeconv](https://www.cell.com/cell-systems/fulltext/S2405-4712(20)30030-2).
    
        Detailed information and the latest version of FLASHDeconv can be downloaded from the [OpenMS webpage](https://openms.de/application/flashdeconv/).
        """
                )

    st.info("""
        **💡 How to run FLASHViewer**
        1. Go to the **📁 File Upload** page through the sidebar and upload FLASHDeconv output files (\*_annotated.mzML & \*_deconv.mzML)
        2. Click the **👀 Viewer** page on the sidebar to view the deconvolved results in detail.
        """)

    # sidebar to toggle between tools
    if 'tool_index' not in st.session_state:
        st.session_state['tool_index'] = 0
    # when entered into other page, key is resetting (emptied) - thus set the value with index
    st.selectbox("Choose a tool", ['FLASHDeconv', 'FLASHQuant'], index=st.session_state.tool_index,
                 on_change=onToolChange(), key='changed_tool_name')
    page_names_to_funcs[st.session_state.changed_tool_name]()


if __name__ == "__main__":
    content()