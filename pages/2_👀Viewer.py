import numpy as np
import streamlit as st
from src.view import *
from src.common import *
from src.masstable import *
from src.components import *


DEFAULT_LAYOUT=[['ms1_deconv_heat_map'], ['scan_table', 'mass_table'],
                ['anno_spectrum', 'deconv_spectrum'], ['3D_SN_plot']]


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


def sendDataToJS(selected_data, layout_info_per_exp):
    # getting data
    selected_anno_file = selected_data.iloc[0]['Annotated Files']
    selected_deconv_file = selected_data.iloc[0]['Deconvolved Files']

    # getting data from mzML files
    spec_df = st.session_state['deconv_dfs'][selected_deconv_file]
    anno_df = st.session_state['anno_dfs'][selected_anno_file]

    # num of rows of layout
    num_of_rows = len(layout_info_per_exp)
    if any(col for row in layout_info_per_exp for col in row if col == '3D_SN_plot'):
        # for 3D_SN_plot, two row sizes are needed
        num_of_rows += 1

    components = []
    for row in layout_info_per_exp:
        # if this row contains 3D plot, height needs to be 2
        height = 2 if '3D_SN_plot' in row else 1
        width_factor = len(row)
        for col_index, comp_name in enumerate(row):
            print('component name: ', comp_name)
            selected_index = 0 # for test purpose

            # prepare component layout
            comp_layout = ComponentLayout(width=6/width_factor, height=height)

            # prepare component arguments
            if comp_name == 'ms1_raw_heatmap':
                df_for_ms1_raw = getMSSignalDF(anno_df)
                component_arguments = PlotlyHeatmap(df=df_for_ms1_raw, title="Raw MS1 Heatmap")
            elif comp_name == 'ms1_deconv_heat_map':
                df_for_ms1_deconv = getMSSignalDF(spec_df)
                component_arguments = PlotlyHeatmap(df=df_for_ms1_deconv, title="Deconvolved MS1 Heatmap")
            elif comp_name == 'Scan table':
                df_for_spectra_table = getSpectraTableDF(spec_df)
                component_arguments = ScanTable(df=df_for_spectra_table, title='Scan Table')
            elif comp_name == 'Deconvolved Spectrum (Scan table needed)':
                x_deconv_spec, y_deconv_spec = create_spectra(spec_df.loc[selected_index])
                component_arguments = PlotlyLineplot(title="Deconvolved spectrum", x=x_deconv_spec, y=y_deconv_spec)
            elif comp_name == 'Annotated Spectrum (Scan table needed)':
                x_anno_spec, y_anno_spec = create_spectra(anno_df.loc[selected_index])
                component_arguments = PlotlyLineplot(title = "Annotated spectrum", x=x_anno_spec, y=y_anno_spec)
            elif comp_name == 'Mass table (Scan table needed)':
                selected_index = 2
                df_for_mass_table = getMassTableDF(spec_df.loc[selected_index])
                component_arguments = MassTable(df=df_for_mass_table, title='Mass Table')
            # elif comp_name == '3D S/N plot (Mass table needed)':

            components.append(FlashViewerComponent(component_args=component_arguments, component_layout=comp_layout))

    FlashViewerGrid(
        columns=6,
        rows=num_of_rows,
        components=components
    ).addGrid()


def content():
    defaultPageSetup("FLASHViewer")

    ### if no input file is given, show blank page
    if "experiment-df" not in st.session_state:
        st.error('Upload input files first!')
        return

    # input experiment file names (for select-box later)
    experiment_df = st.session_state["experiment-df"]

    ### for only single experiment on one view
    st.selectbox("choose experiment", experiment_df['Experiment Name'], key="selected_experiment0")
    selected_exp0 = experiment_df[experiment_df['Experiment Name'] == st.session_state.selected_experiment0]
    layout_info = DEFAULT_LAYOUT
    if "saved_layout_setting" in st.session_state:  # when layout manager was used
        layout_info = st.session_state["saved_layout_setting"][0]
    sendDataToJS(selected_exp0, layout_info)

    ### for multiple experiments on one view
    if "saved_layout_setting" in st.session_state and len(st.session_state["saved_layout_setting"]) > 1:

        for exp_index, exp_layout in enumerate(st.session_state["saved_layout_setting"]):
            if exp_index == 0: continue  # skip the first experiment

            st.divider() # horizontal line
            st.selectbox("choose experiment", experiment_df['Experiment Name'],
                         key="selected_experiment%d"%exp_index,
                         index=exp_index if exp_index<len(experiment_df) else 0)
            # if #experiment input files are less than #layouts, all the pre-selection will be the first experiment

            selected_exp = experiment_df[
                experiment_df['Experiment Name'] == st.session_state["selected_experiment%d"]%exp_index]
            layout_info = st.session_state["saved_layout_setting"][exp_index]
            sendDataToJS(selected_exp, layout_info)

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
