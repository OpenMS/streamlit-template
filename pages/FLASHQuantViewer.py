import streamlit as st
from src.common import defaultPageSetup
from src.flashquant import connectTraceWithResult
from src.components import FlashViewerGrid, FlashViewerComponent, FLASHQuant
import streamlit.components.v1 as st_components
import pandas as pd

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

    # SEND DATA
    # getting data
    selected_quant_file = selected_exp0.iloc[0]['Quant result Files']
    selected_trace_file = selected_exp0.iloc[0]['Mass trace Files']

    # getting data from mzML files
    quant_df = st.session_state['quant_dfs'][selected_quant_file]
    trace_df = st.session_state['trace_dfs'][selected_trace_file]

    _flash_viewer_grid = st_components.declare_component("flash_viewer_grid",
                                                         url="http://localhost:5173")
    _flash_viewer_grid(components=[[{'componentArgs': {'componentName': 'FLASHQuantView'}}]],
                       data_for_drawing={'quant_data': connectTraceWithResult(quant_df, trace_df).to_json(orient='records')},
                       key=None)


if __name__ == "__main__":
    content()
