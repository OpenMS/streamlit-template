import streamlit as st
from src.common import defaultPageSetup
import streamlit.components.v1 as st_components
from src.components import flash_viewer_grid_component, FlashViewerComponent, FLASHQuant


def content():
    defaultPageSetup('FLASHQuant Viewer')

    # if no input file is given, show blank page
    if "quant-experiment-df" not in st.session_state:
        st.error('Upload input files first!')
        return

    # input experiment file names (for select-box later)
    experiment_df = st.session_state["quant-experiment-df"]

    # for only single experiment on one view
    st.selectbox("choose experiment", experiment_df['Experiment Name'], key="selected_experiment0")
    selected_exp0 = experiment_df[experiment_df['Experiment Name'] == st.session_state.selected_experiment0]

    # preparing data to send
    selected_quant_file = selected_exp0.iloc[0]['Quant result Files']  # getting file name
    quant_df = st.session_state['quant_dfs'][selected_quant_file]  # getting data from file name

    component = [[FlashViewerComponent(FLASHQuant())]]
    flash_viewer_grid_component(components=component, data={'quant_data': quant_df})


if __name__ == "__main__":
    content()
