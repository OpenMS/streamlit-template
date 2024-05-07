import streamlit as st
import json
from src.common import page_setup, save_params

# to convert between FLASHDeconv and FLASHQuant
from st_pages import Page, show_pages


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
    if 'changed_tool_name' not in st.session_state:  # this is needed for initialization
        return
    for key in params.keys():
        if key == 'controllo':  # don't remove controllo
            continue
        if key in st.session_state.keys():
            del st.session_state[key]
    st.session_state['tool_index'] = 0 if st.session_state.changed_tool_name == 'FLASHDeconv' else 1
    st.rerun()  # reload the page to sync the change


# initializing the page
params = page_setup(page="main")
st.title("FLASHViewer")

# main content
st.markdown("""
    #### FLASHViewer visualizes outputs from [FLASHDeconv](https://www.cell.com/cell-systems/fulltext/S2405-4712(20)30030-2) or FLASHQuant.

    Detailed information and the latest version of \\
    $\quad$ FLASHDeconv can be downloaded from the [OpenMS webpage](https://openms.de/flashdeconv/) \\
    $\quad$ FLASHQuant can be downloaded from the [OpenMS webpage](https://openms.de/flashquant/)
    """
            )

st.info("""
    **💡 How to run FLASHViewer (with FLASHDeconv)**
    1. Go to the **📁 File Upload** page through the sidebar and upload FLASHDeconv output files (\*_annotated.mzML & \*_deconv.mzML)
    2. Click the **👀 Viewer** page on the sidebar to view the deconvolved results in detail.
    """)

# selectbox to toggle between tools
if 'tool_index' not in st.session_state:
    st.session_state['tool_index'] = 0
# when entered into other page, key is resetting (emptied) - thus set the value with index
st.selectbox("Choose a tool", ['FLASHDeconv', 'FLASHQuant'], index=st.session_state.tool_index,
             on_change=onToolChange(), key='changed_tool_name')
page_names_to_funcs[st.session_state.changed_tool_name]()

# make sure new default params are saved in workspace params
with open("assets/default-params.json", "r") as f:
    default_params = json.load(f)
for key, value in default_params.items():
    if key not in params.keys():
        params[key] = value

save_params(params)
