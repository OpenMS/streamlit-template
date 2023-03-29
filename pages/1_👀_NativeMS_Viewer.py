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
    plot3d = plot3DSignalView(signal_df, noise_df)
    st.plotly_chart(plot3d, use_container_width=True)

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
    selected_deconv_file = selected['MSn tsv Files'][0]

    # setting MS1 and MS2 input file
    st.session_state['MS1_file'] = selected_deconv_file[0]
    st.session_state['MS2_file'] = selected_deconv_file[1]

    # this is for testing (TODO:remove)
    selected_deconv_file = Path('default-workspace/deconv-mzMLs', st.session_state.selected_experiment+'_deconv.mzML')

    # getting data from mzML files
    spec_df, anno_df, tolerance, massoffset, chargemass = parseFLASHDeconvOutput(selected_anno_file, selected_deconv_file)
    df_for_spectra_table = getSpectraTableDF(spec_df)

    #### Showing MS1 heatmaps ####
    # if st.session_state['MS1_file']:
    #     df_for_ms1_raw = getMSSignalDF(anno_df) # TODO: lots of 0 intensities...
    #     df_for_ms1_deconv = getMSSignalDF(spec_df)
    #
    #     raw_ms1_view, deconv_ms1_view = st.columns(2)
    #     with raw_ms1_view: # drawing heatmap
    #         raw_ms1_plot_fig = plotMS1HeatMap(df_for_ms1_raw, "Raw MS1 Heatmap")
    #         st.plotly_chart(raw_ms1_plot_fig, use_container_width=True)
    #     with deconv_ms1_view:
    #         deconv_ms1_plot_fig = plotMS1HeatMap(df_for_ms1_deconv, "Deconvolved MS1 Heatmap")
    #         st.plotly_chart(deconv_ms1_plot_fig, use_container_width=True)

    #### SpectrumView and Tables ####
    spectrumView, tableView = st.columns(2)

    selected_scan_response = None
    if "index_for_selected_spectrum" in st.session_state:
        selected_scan_response = st.session_state["index_for_selected_spectrum"]

    with tableView:
        # scan table
        st.write('**Scan Table**')
        st.session_state["index_for_selected_spectrum"] = drawSpectraTable(df_for_spectra_table, 250)
        # mass table
        # listening selecting row from the spectra table
        if selected_scan_response["selected_rows"]:
            selected_index = selected_scan_response["selected_rows"][0]["index"]
            selected_spectrum = spec_df.loc[selected_index]
            # preparing data for plotting (cached)
            mass_df = getMassTableDF(selected_spectrum)
            st.write('**Mass Table** of selected spectrum index: %d'%selected_index)
            # drawing interactive mass table
            st.session_state["index_for_selected_mass"] = drawSpectraTable(mass_df, 250)

    with spectrumView:
        # listening selecting row from the spectra table
        if selected_scan_response["selected_rows"]:
            selected_index = selected_scan_response["selected_rows"][0]["index"]
            plotAnnotatedMS(anno_df.loc[selected_index])
            plotDeconvolvedMS(spec_df.loc[selected_index])

    #### 3D signal plot ####
    # listening selecting row from the spectra table
    selected_mass_response = st.session_state["index_for_selected_mass"]
    if selected_mass_response["selected_rows"]:
        selected_spec = spec_df.loc[selected_scan_response["selected_rows"][0]["index"]]
        mass_signal_df = getMassSignalDF(selected_spec)

        selected_mass_index = selected_mass_response["selected_rows"][0]["index"]
        draw3DSignalView(mass_signal_df.loc[selected_mass_index])

if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])
