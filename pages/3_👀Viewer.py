from src.common import *
from src.masstable import *
from src.components import *
from src.sequence import getFragmentDataFromSeq


DEFAULT_LAYOUT = [['ms1_deconv_heat_map'], ['scan_table', 'mass_table'],
                  ['anno_spectrum', 'deconv_spectrum'], ['3D_SN_plot']]


# @st.cache_resource
def sendDataToJS(selected_data, layout_info_per_exp):
    # getting data
    selected_anno_file = selected_data.iloc[0]['Annotated Files']
    selected_deconv_file = selected_data.iloc[0]['Deconvolved Files']

    # getting data from mzML files
    spec_df = st.session_state['deconv_dfs'][selected_deconv_file]
    anno_df = st.session_state['anno_dfs'][selected_anno_file]

    # num of rows of layout
    num_of_rows = len(layout_info_per_exp)
    # if any(col for row in layout_info_per_exp for col in row if (col == '3D_SN_plot') or (col == 'sequence_view')):
    #     for 3D_SN_plot, two row sizes are needed
        # num_of_rows += 1

    components = []
    data_to_send = {}
    per_scan_contents = {'mass_table': False, 'anno_spec': False, 'deconv_spec': False, '3d': False}
    for row in layout_info_per_exp:
        # if this row contains 3D plot, height needs to be 2
        height = 2 if '3D_SN_plot' or 'sequence_view' in row else 1
        width_factor = len(row)
        for col_index, comp_name in enumerate(row):
            # prepare component layout
            comp_layout = ComponentLayout(width=6/width_factor, height=height)
            component_arguments = None

            # prepare component arguments
            if comp_name == 'ms1_raw_heatmap':
                data_to_send['raw_heatmap_df'] = getMSSignalDF(anno_df)
                component_arguments = PlotlyHeatmap(title="Raw MS1 Heatmap")
            elif comp_name == 'ms1_deconv_heat_map':
                data_to_send['deconv_heatmap_df'] = getMSSignalDF(spec_df)
                component_arguments = PlotlyHeatmap(title="Deconvolved MS1 Heatmap")
            elif comp_name == 'scan_table':
                data_to_send['per_scan_data'] = getSpectraTableDF(spec_df)
                component_arguments = Tabulator('ScanTable')
            elif comp_name == 'deconv_spectrum':
                per_scan_contents['deconv_spec'] = True
                component_arguments = PlotlyLineplot(title="Deconvolved spectrum")
            elif comp_name == 'anno_spectrum':
                per_scan_contents['anno_spec'] = True
                component_arguments = PlotlyLineplot(title="Annotated spectrum")
            elif comp_name == 'mass_table':
                per_scan_contents['mass_table'] = True
                component_arguments = Tabulator('MassTable')
            elif comp_name == '3D_SN_plot':
                per_scan_contents['3d'] = True
                component_arguments = Plotly3Dplot(title="Precursor signals")
            elif comp_name == 'sequence_view':
                data_to_send['sequence_data'] = getFragmentDataFromSeq(st.session_state.input_sequence)
                component_arguments = SequenceView()

            components.append(FlashViewerComponent(component_args=component_arguments, component_layout=comp_layout))

    if any(per_scan_contents.values()):
        scan_table = data_to_send['per_scan_data']
        dfs = [scan_table]
        for key, exist in per_scan_contents.items():
            if not exist: continue

            if key == 'mass_table':
                tmp_df = spec_df[['mzarray', 'intarray', 'MinCharges', 'MaxCharges', 'MinIsotopes', 'MaxIsotopes',
                                  'cos', 'snr', 'qscore']].copy()
                tmp_df.rename(columns={'mzarray': 'MonoMass', 'intarray': 'SumIntensity', 'cos': 'CosineScore',
                                       'snr': 'SNR', 'qscore': 'QScore'},
                              inplace=True)
            elif key == 'deconv_spec':
                if per_scan_contents['mass_table']: continue  # deconv_spec shares same data with mass_table

                tmp_df = spec_df[['mzarray', 'intarray']].copy()
                tmp_df.rename(columns={'mzarray': 'MonoMass', 'intarray': 'SumIntensity'}, inplace=True)
            elif key == 'anno_spec':
                tmp_df = anno_df[['mzarray', 'intarray']].copy()
                tmp_df.rename(columns={'mzarray': 'MonoMass_Anno', 'intarray': 'SumIntensity_Anno'}, inplace=True)
            elif key == '3d':
                tmp_df = spec_df[['PrecursorScan', 'SignalPeaks', 'NoisyPeaks']].copy()
            else:  # shouldn't come here
                continue

            dfs.append(tmp_df)
        data_to_send['per_scan_data'] = pd.concat(dfs, axis=1)

    FlashViewerGrid(
        columns=6,
        rows=num_of_rows,
        components=components,
        data=data_to_send
    ).addGrid()


def setSequenceViewInDefaultView():
    if 'input_sequence' in st.session_state and st.session_state.input_sequence:
        global DEFAULT_LAYOUT
        DEFAULT_LAYOUT = DEFAULT_LAYOUT + [['sequence_view']]


def content():
    defaultPageSetup("FLASHViewer")
    setSequenceViewInDefaultView()

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
                experiment_df['Experiment Name'] == st.session_state["selected_experiment%d"%exp_index]]
            layout_info = st.session_state["saved_layout_setting"][exp_index]
            sendDataToJS(selected_exp, layout_info)


if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])
