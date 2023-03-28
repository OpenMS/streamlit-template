import numpy as np
import streamlit as st
from src.view import *
from src.common import *
from src.masstable import *
from streamlit_plotly_events import plotly_events

def content():
    defaultPageSetup("NativeMS Viewer")

    # if no input file is given, show blank page
    if "experiment-df" not in st.session_state:
        st.error('Upload input files first!')
        return

    # selecting experiment
    experiment_df = st.session_state["experiment-df"]

    st.selectbox(
        "choose experiment", experiment_df['Experiment Name'],
        key="selected_experiment",
    )

    # two main containers
    spectra_container, mass_container = st.columns(2)

    # getting data
    selected = experiment_df[experiment_df['Experiment Name'] == st.session_state.selected_experiment]
    selected_anno_file = selected['Annotated Files'][0]
    selected_deconv_file = selected['Deconvolved Files'][0]

    ## for now, test data
    spec_df, anno_df, tolerance, massoffset, chargemass = getMassTable(selected_anno_file, selected_deconv_file)
    st.dataframe(spec_df)

    with spectra_container:
        # drawing 3D spectra viewer (1st column, top)
        st.subheader('Signal View')
        signal_plot_container = st.empty() # initialzie space for drawing 3d plot

        # drawing spectra table (1st column, bottom)
        st.subheader('Spectrum Table')
        df_for_table = spec_df[['Scan', 'MSLevel', 'RT']]
        df_for_table['#Masses'] = [len(ele) for ele in spec_df['MinCharges']]
        df_for_table.reset_index(inplace=True)
        st.session_state["index_for_signal_view"] = drawSpectraTable(df_for_table)

        with signal_plot_container.container():
            response = st.session_state["index_for_signal_view"]
            if response["selected_rows"]:
                selected_index = response["selected_rows"][0]["index"]
                plot3DSignalView(spec_df.loc[selected_index])

if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])
