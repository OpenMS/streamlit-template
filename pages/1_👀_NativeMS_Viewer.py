import numpy as np
import streamlit as st
from src.view import *
from src.common import *
from src.masstable import *
from streamlit_plotly_events import plotly_events

@st.cache_resource
def draw3DSignalView(df):
    signal_df, noise_df = None, None # initialization
    for index, peaks in enumerate([df['Signal peaks'], df['Noisy peaks']]):
        xs, ys, zs = [], [], []
        for sm in peaks:
            xs.append(sm[1] * sm[-1])
            ys.append(sm[-1])
            zs.append(sm[2])

        out_df = pd.DataFrame({'mass': xs, 'charge': ys, 'intensity': zs})
        if index == 0:
            signal_df = out_df
        else:
            noise_df = out_df
    plot3DSignalView(signal_df, noise_df)

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

    # getting data
    selected = experiment_df[experiment_df['Experiment Name'] == st.session_state.selected_experiment]
    selected_anno_file = selected['Annotated Files'][0]
    selected_deconv_file = selected['Deconvolved Files'][0]

    # getting data from mzML files
    spec_df, anno_df, tolerance, massoffset, chargemass = parseFLASHDeconvOutput(selected_anno_file, selected_deconv_file)
    df_for_spectra_table = getSpectraTableDF(spec_df)

    #### Showing spectra information ####
    st.subheader('Select a spectrum to view')
    spectra_view_col1, spectra_view_col2 = st.columns(2)
    with spectra_view_col1: # drawing heatmap
        plotHeatMap()
    with spectra_view_col2: # drawing spectra table (1st column, bottom)
        st.session_state["index_for_selected_spectrum"] = drawSpectraTable(df_for_spectra_table, 200)

    #### two main containers for plotting ####
    spectrumView, massView = st.columns(2)

    with spectrumView:
        # listening selecting row from the spectra table
        response = st.session_state["index_for_selected_spectrum"]
        if response["selected_rows"]:
            selected_index = response["selected_rows"][0]["index"]
            plotAnnotatedMS(anno_df.loc[selected_index])
            plotDeconvolvedMS(spec_df.loc[selected_index])

    with massView:
        # listening selecting row from the spectra table
        response = st.session_state["index_for_selected_spectrum"]
        if response["selected_rows"]:
            selected_index = response["selected_rows"][0]["index"]
            selected_spectrum = spec_df.loc[selected_index]
            # preparing data for plotting (cached)
            mass_df = getMassTableDF(selected_spectrum)
            mass_signal_df = getMassSignalDF(selected_spectrum)

            st.write("Selected spectrum index: %d"%selected_index)
            # drawing interactive mass table
            st.session_state["index_for_selected_mass"] = drawSpectraTable(mass_df)

            # drawing 3D signal plot of selected mass
            response_for_mass_table = st.session_state["index_for_selected_mass"]
            if response_for_mass_table["selected_rows"]:
                selected_mass_index = response_for_mass_table["selected_rows"][0]["index"]
                draw3DSignalView(mass_signal_df.loc[selected_mass_index])

if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])
