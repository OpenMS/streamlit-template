import streamlit as st
from src.common import defaultPageSetup, v_space


COMPONENT_OPTIONS=[
    'MS1 raw Heatmap',
    'MS1 deconvolved Heatmap',
    'Scan table',
    'Deconvolved Spectrum (Scan table needed)',
    'Annotated Spectrum (Scan table needed)',
    'Mass table (Scan table needed)',
    '3D S/N plot (Mass table needed)',
    # TODO: add Sequence view
]

COMPONENT_NAMES=[
    'ms1_raw_heatmap',
    'ms1_deconv_heat_map',
    'scan_table',
    'deconv_spectrum',
    'anno_spectrum',
    'mass_table',
    '3D_SN_plot',
    # TODO: add Sequence view
]


def resetSettingsToDefault(num_of_exp=1):
    st.session_state["layout_setting"] = [[['']]] # 1D: experiment, 2D: row, 3D: column, element=component name
    st.session_state["num_of_experiment_to_show"] = num_of_exp
    for index in range(1, num_of_exp):
        st.session_state.layout_setting.append([['']])

def containerForNewComponent(exp_index, row_index, col_index):
    # st.markdown(css_new_component_container, unsafe_allow_html=True)
    def addNewComponent(exp_num, row, col):
        new_component_option = 'SelectNewComponent%d%d%d'%(exp_index, row_index, col_index)
        # TODO: check if new_component_option is duplicated!
        # st.session_state.layout_setting[exp_num][row][col] = COMPONENT_NAMES[
        #     COMPONENT_OPTIONS.index(st.session_state[new_component_option])]
        st.session_state.layout_setting[exp_num][row][col] = st.session_state[new_component_option]

    # new component
    st.selectbox("New component to add", COMPONENT_OPTIONS,
                 key='SelectNewComponent%d%d%d'%(exp_index, row_index, col_index),
                 on_change=addNewComponent,
                 kwargs=dict(exp_num=exp_index, row=row_index, col=col_index),
                 placeholder='Select...',
                 )

def layoutEditorPerExperiment(exp_index):
    layout_info = st.session_state.layout_setting[exp_index]
    st.write('current layout', layout_info)

    for row_index, row in enumerate(layout_info):
        st_cols = st.columns(len(row)+1 if  len(row)<3 else len(row))
        for col_index, col in enumerate(row):
            if not col: # if empty, add newComponent container
                with st_cols[col_index].container():
                    containerForNewComponent(exp_index, row_index, col_index)
            else:
                st_cols[col_index].info(col)

        # new column button
        if len(row) < 3: # limit for #column is 3
            v_space(1, st_cols[-1])
            if st_cols[-1].button("***+***", key='NewColumnButton%d%d'%(exp_index, row_index)):
                layout_info[row_index].append('')
                st.experimental_rerun()

    # new row button
    if st.button("***+***", key='NewRowButton%d'%exp_index):
        layout_info.append([''])
        st.experimental_rerun()


def content():
    defaultPageSetup()

    # initialize setting information
    if "layout_setting" not in st.session_state:
        resetSettingsToDefault()
    elif len(st.session_state.layout_setting) != st.session_state.num_of_experiment_to_show:
        # the "num_of_experiment_to_show" changed
        resetSettingsToDefault(st.session_state.num_of_experiment_to_show)

    # title and setting buttons
    c1, c2, c3, c4 = st.columns([6, 1, 1, 1])
    c1.title("Layout Manager")

    # Load existing layout setting file
    # TODO: change the loading data part (from writing)
    v_space(1, c2)
    if c2.button("Load Setting"):
        uploaded_ini_file = st.file_uploader("Choose a ini file", type="ini")
        if uploaded_ini_file is not None:
            bytes_data = uploaded_ini_file.read()
            st.write(bytes_data)

    # Save current layout setting
    # TODO: change the saving location
    v_space(1, c3)
    c3.download_button(
        label="Save Setting",
        data="st.session_state.layout_setting", # TODO: add a function to format this
        file_name='FLASHViewer_layout_settings.ini',
        mime='text/plain',  # TODO: change this to JSON?
    )

    # Reset settings to default
    v_space(1, c4)
    if c4.button("Reset Setting"):
        resetSettingsToDefault()

    # show default
    st.selectbox("**#Experiments to view at once**", [1, 2, 3, 4, 5],
        key="num_of_experiment_to_show",
    )

    for index_of_experiment in range(st.session_state.num_of_experiment_to_show):
        with st.expander("Experiment #%d"%(index_of_experiment+1)):
            layoutEditorPerExperiment(index_of_experiment)

        # save current status

    # TODO: Send the layout info to JSON
    _, button_col = st.columns([7,1])
    if button_col.button("Save"):
        st.success('Layouts Saved')
        st.write(st.session_state.layout_setting)
        # TODO: Err if "needed" components are not added
        # TODO: show saved layout (with correct column sizes)

    ## TIPs (TODO: Add image)
    st.info("""
    **💡 Tips**
    """)


if __name__ == "__main__":
    # try:
    content()
# except:
#     st.error(ERRORS["general"])
