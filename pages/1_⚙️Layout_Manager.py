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
    st.selectbox("New component to add", ['Select...'] + COMPONENT_OPTIONS,
                 key='SelectNewComponent%d%d%d'%(exp_index, row_index, col_index),
                 on_change=addNewComponent,
                 kwargs=dict(exp_num=exp_index, row=row_index, col=col_index),
                 placeholder='Select...',
                 )

def layoutEditorPerExperiment(exp_index):
    layout_info = st.session_state.layout_setting[exp_index]

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

def validateSubmittedLayout():
    # check if submitted layout is empty
    if not any(col for exp in st.session_state.layout_setting for row in exp for col in row if col):
        return 'Empty input'

    # TODO: Err if "needed" components are not added
    print(st.session_state.layout_setting)
    return ''

def handleEditAndSaveButtons():
    # return: "validation"

    # if "Edit" button was clicked,
    if "edit_btn_clicked" in st.session_state and st.session_state["edit_btn_clicked"]:
        # reset variables based on "saved_layout_setting"
        st.session_state["num_of_experiment_to_show"] = len(st.session_state["saved_layout_setting"])
        st.session_state["layout_setting"] = [[[COMPONENT_OPTIONS[COMPONENT_NAMES.index(col)]
                                                for col in row if col]
                                               for row in exp if row]
                                              for exp in st.session_state.saved_layout_setting]
        # remove saved state, if any
        del st.session_state["saved_layout_setting"]

    # if "Save" button was clicked,
    if "layout_saved" in st.session_state and st.session_state["layout_saved"]:
        got_error = validateSubmittedLayout()
        st.session_state['save_btn_error_message'] = got_error # to show error msg at the end
        if not got_error:
            # get only submitted info from "layout_setting"
            cleared_layout_setting = []
            for exp in st.session_state.layout_setting:
                rows = []
                for row in exp:
                    cols = []
                    for col in row:
                        if col:
                            cols.append(COMPONENT_NAMES[COMPONENT_OPTIONS.index(col)])
                    if cols:
                        rows.append(cols)
                if rows:
                    cleared_layout_setting.append(rows)
            st.session_state["saved_layout_setting"] = cleared_layout_setting

def handleSettingButtons():
    if "reset_btn_clicked" in st.session_state and st.session_state.reset_btn_clicked:
        resetSettingsToDefault()
        if "saved_layout_setting" in st.session_state:
            del st.session_state["saved_layout_setting"]


def content():
    defaultPageSetup()
    # handles "onclick" of buttons
    handleSettingButtons()
    handleEditAndSaveButtons()

    # initialize setting information
    if "layout_setting" not in st.session_state:
        resetSettingsToDefault()
    # the "num_of_experiment_to_show" changed
    elif "num_of_experiment_to_show" in st.session_state and \
            len(st.session_state.layout_setting) != st.session_state.num_of_experiment_to_show:
        resetSettingsToDefault(st.session_state.num_of_experiment_to_show)

    ### title and setting buttons
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
    c4.button("Reset Setting", "reset_btn_clicked")

    ### Main part
    if "saved_layout_setting" in st.session_state:
        # show saved-mode
        for index_of_experiment in range(len(st.session_state.saved_layout_setting)):
            layout_info_per_experiment = st.session_state.saved_layout_setting[index_of_experiment]
            with st.expander("Experiment #%d"%(index_of_experiment+1), expanded=True):
                for row_index, row in enumerate(layout_info_per_experiment):
                    st_cols = st.columns(len(row))
                    for col_index, col in enumerate(row):
                        st_cols[col_index].info(COMPONENT_OPTIONS[COMPONENT_NAMES.index(col)])
    else:
        # show edit-mode
        st.selectbox("**#Experiments to view at once**", [1, 2, 3, 4, 5],
                     key="num_of_experiment_to_show",
        )

        for index_of_experiment in range(st.session_state.num_of_experiment_to_show):
            with st.expander("Experiment #%d"%(index_of_experiment+1)):
                layoutEditorPerExperiment(index_of_experiment)

    ### buttons for edit/save
    _, edit_btn_col, save_btn_col = st.columns([9, 1, 1])
    edit_btn_col.button("Edit", key="edit_btn_clicked")
    save_btn_col.button("Save", key="layout_saved")

    if "save_btn_error_message" in st.session_state and st.session_state.layout_saved:
        error_message = st.session_state["save_btn_error_message"]
        if error_message:
            st.error('Error: '+error_message, icon="🚨")
        else:
            st.success('Layouts Saved')

    ### TIPs (TODO: Add image)
    st.info("""
    **💡 Tips**
    """)


if __name__ == "__main__":
    # try:
    content()
# except:
#     st.error(ERRORS["general"])
