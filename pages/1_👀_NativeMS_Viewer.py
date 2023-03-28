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

    ## getting data from mzML files
    spec_df, anno_df, tolerance, massoffset, chargemass = getMassTable(selected_anno_file, selected_deconv_file)

    with spectra_container:
        # drawing 3D spectra viewer (1st column, top)
        st.subheader('Spectrum View')
        signal_plot_container = st.empty() # initialize space for drawing spectrum plot

        # drawing spectra table (1st column, bottom)
        # st.subheader('Spectrum Table')
        df_for_spectra_table = spec_df[['Scan', 'MSLevel', 'RT']]
        df_for_spectra_table['#Masses'] = [len(ele) for ele in spec_df['MinCharges']]
        df_for_spectra_table.reset_index(inplace=True)
        st.session_state["index_for_selected_spectrum"] = drawSpectraTable(df_for_spectra_table)

        # listening selecting row from the spectra table
        with signal_plot_container.container():
            response = st.session_state["index_for_selected_spectrum"]
            if response["selected_rows"]:
                selected_index = response["selected_rows"][0]["index"]
                plotAnnotatedMS(anno_df.loc[selected_index])
                plotDeconvolvedMS(spec_df.loc[selected_index])

    with mass_container:
        st.subheader('Deconvoluted Masses')

        response = st.session_state["index_for_selected_spectrum"]
        if response["selected_rows"]:
            selected_index = response["selected_rows"][0]["index"]
            selected_spectrum = spec_df.loc[selected_index]
            # dft = pd.DataFrame()
            mass_df = pd.DataFrame({'Mono mass': selected_spectrum['mzarray'],
                                    'Sum intensity': selected_spectrum['intarray'],
                                    'Min charge': selected_spectrum['MinCharges'],
                                    'Max charge': selected_spectrum['MaxCharges'],
                                    'Min isotope': selected_spectrum['MinIsotopes'],
                                    'Max isotope': selected_spectrum['MaxIsotopes'],
                                    })
            st.write("Spectrum index: %d"%selected_index)
            st.session_state["index_for_selected_mass"] = drawSpectraTable(mass_df)

if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])
