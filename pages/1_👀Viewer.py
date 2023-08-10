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

def create_spectra(input_df):
    x = np.repeat(input_df["mzarray"], 3)
    y = np.repeat(input_df["intarray"], 3)
    y[::3] = y[2::3] = -100000
    return x.tolist(), y.tolist()

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
    selected_index = 0
    df_for_mass_table = getMassTableDF(spec_df.loc[selected_index])
    x_anno_spec, y_anno_spec = create_spectra(anno_df.loc[selected_index])
    x_deconv_spec, y_deconv_spec = create_spectra(spec_df.loc[selected_index])
    FlashViewerGrid(
        columns=2,
        rows=3,
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
                    dataframe=df_for_spectra_table,
                    title='Scan Table'
                ),
                component_layout=ComponentLayout(
                    width=1,
                    height=1
                )
            ),
            FlashViewerComponent(
                component_args=MassTable(
                    dataframe=df_for_mass_table,
                    title='Mass Table'
                ),
                component_layout=ComponentLayout(
                    width=2,
                    height=1
                )
            ),
            FlashViewerComponent(
                component_args=PlotlyLineplot(
                    title = "Annotated spectrum",
                    x = x_anno_spec,
                    y = y_anno_spec,
                ),
                component_layout=ComponentLayout(
                    width=1,
                    height=1
                )
            ),
            FlashViewerComponent(
                component_args=PlotlyLineplot(
                    title = "Deconvolved spectrum",
                    x = x_deconv_spec,
                    y = y_deconv_spec,
                ),
                component_layout=ComponentLayout(
                    width=1,
                    height=1
                )
            ),
        ]
    ).addGrid()

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
