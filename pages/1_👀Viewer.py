import numpy as np
import streamlit as st
from src.view import *
from src.common import *
from src.masstable import *
from src.components import *

@st.cache_data
def draw3DSignalView(df, title):
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
    plot3d = plot3DSignalView(signal_df, noise_df, title)
    st.plotly_chart(plot3d, use_container_width=True)

def content():
    defaultPageSetup("FLASHViewer")

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

    selected_anno_file = selected.iloc[0]['Annotated Files']
    selected_deconv_file = selected.iloc[0]['Deconvolved Files']

    # getting data from mzML files
    spec_df = st.session_state['deconv_dfs'][selected_deconv_file]
    anno_df = st.session_state['anno_dfs'][selected_anno_file]

    #### Showing MS1 heatmap & Scan table ####
    df_for_ms1_deconv = getMSSignalDF(spec_df)
    df_for_spectra_table = getSpectraTableDF(spec_df)
    df_for_mass_table = getMassTableDF(spec_df.loc[0])
    FlashViewerGrid(
        columns=2,
        rows=2,
        components=[
            FlashViewerComponent(
                component_args=PlotlyHeatmap(
                    title = "Deconvolved MS1 Heatmap", 
                    x = list(df_for_ms1_deconv['rt']), 
                    y = list(df_for_ms1_deconv['mass']), 
                    intensity = list(df_for_ms1_deconv['intensity'])
                ),
                component_layout=ComponentLayout(
                    width=1,
                    height=1
                )
            ),
            FlashViewerComponent(
                component_args=ScanTable(
                    dataframe=df_for_spectra_table
                ),
                component_layout=ComponentLayout(
                    width=1,
                    height=1
                )
            ),
            FlashViewerComponent(
                component_args=MassTable(
                    dataframe=df_for_mass_table
                ),
                component_layout=ComponentLayout(
                    width=2,
                    height=1
                )
            )
        ]
    ).addGrid()

    #### Spectrum plots ####
    # listening selecting row from the spectra table
    # if st.session_state.selected_scan["selected_rows"]:
    # selected_index = st.session_state.selected_scan["selected_rows"][0]["index"]
    selected_index = 0
    # anno_spec_view, deconv_spec_view = st.columns(2)
    # with anno_spec_view:
    #     st.plotly_chart(plotAnnotatedMS(anno_df.loc[selected_index]), use_container_width=True)
    # with deconv_spec_view:
    #     st.plotly_chart(plotDeconvolvedMS(spec_df.loc[selected_index]), use_container_width=True)

    #### 3D signal plot ####
    # plot3d_view, _ = st.columns([9, 1])  # for little space on the right
    # # listening to the selected row from the scan table
    # if st.session_state.selected_scan["selected_rows"]:
    #     selected_spec = spec_df.loc[st.session_state.selected_scan["selected_rows"][0]["index"]]
    #
    #     # listening to the selected row from the mass table
    #     if ("selected_mass" in st.session_state) and \
    #         (st.session_state.selected_mass["selected_rows"]):
    #         mass_signal_df = getMassSignalDF(selected_spec)
    #         selected_mass_index = st.session_state.selected_mass["selected_rows"][0]["index"]
    #         with plot3d_view:
    #             draw3DSignalView(mass_signal_df.loc[selected_mass_index], 'Mass signals')
    #     else: # draw precursor signals
    #         precursor_signal = getPrecursorMassSignalDF(selected_spec, spec_df)
    #         if precursor_signal.size > 0:
    #             with plot3d_view:
    #                 draw3DSignalView(getPrecursorMassSignalDF(selected_spec, spec_df), 'Precursor signals')

if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])
