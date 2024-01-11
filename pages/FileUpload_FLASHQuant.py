import streamlit as st
from pathlib import Path
import shutil
import pandas as pd
from src.flashquant import parseFLASHQuantOutput
from src.common import v_space, page_setup, reset_directory, save_params
from pages.FileUpload import initializeWorkspace
from src.flashquant import connectTraceWithResult


@st.cache_data
def getUploadedFileDF(quant_files, trace_files, resolution_files):
    # leave only names
    quant_files = [Path(f).name for f in quant_files]
    trace_files = [Path(f).name for f in trace_files]
    resolution_files = [Path(f).name for f in resolution_files]

    # getting experiment name from annotated file (tsv files can be multiple per experiment)
    experiment_names = [f[0: f.rfind('.fdq')] for f in quant_files]

    df = pd.DataFrame({'Experiment Name': experiment_names,
                       'Quant result Files': quant_files,
                       'Mass trace Files': trace_files})
    if resolution_files:
        df['Conflict resolution Files'] = resolution_files

    return df


def remove_selected_experiment_files(to_remove: list[str], params: dict) -> dict:
    """
    Removes selected mzML files from the mzML directory. (From fileUpload.py)

    Args:
        to_remove (List[str]): List of mzML files to remove.
        params (dict): Parameters.

    Returns:
        dict: parameters with updated mzML files
    """
    for input_type, df_type, file_postfix in zip(input_file_types, parsed_df_types,
                                                 ['.fdq.tsv', '.fdq.mts.tsv', '.fdq_shared.tsv']):
        input_type_dir = Path(st.session_state["workspace"], input_type)
        # remove all given files from mzML workspace directory and selected files
        for exp_name in to_remove:
            file_name = exp_name + file_postfix
            Path(input_type_dir, file_name).unlink()
            del st.session_state[df_type][file_name]  # removing key

    # update the experiment df table
    tmp_df = st.session_state["quant-experiment-df"]
    tmp_df.drop(tmp_df.loc[tmp_df['Experiment Name'].isin(to_remove)].index, inplace=True)
    st.session_state["quant-experiment-df"] = tmp_df

    st.success("Selected experiment files removed!")
    return params


def handleInputFiles(uploaded_files):
    for file in uploaded_files:
        if not file.name.endswith("tsv"):
            continue

        session_name = ''
        if file.name.endswith('fdq.tsv'):
            session_name = 'quant-files'
        elif file.name.endswith('fdq.mts.tsv'):
            session_name = 'trace-files'
        elif file.name.endswith('fdq_shared.tsv'):
            session_name = 'conflict-resolution-files'

        if file.name not in st.session_state[session_name]:
            with open(
                    Path(st.session_state["workspace"], session_name, file.name), "wb"
            ) as f:
                f.write(file.getbuffer())
            st.session_state[session_name].append(file.name)


def parseUploadedFiles():
    # get newly uploaded files
    quant_files = st.session_state['quant-files']
    trace_files = st.session_state['trace-files']
    resolution_files = st.session_state['conflict-resolution-files']

    new_quant_files = [f for f in quant_files if f not in st.session_state['quant_dfs']]
    new_trace_files = [f for f in trace_files if f not in st.session_state['trace_dfs']]
    new_resolution_files = [f for f in resolution_files if f not in st.session_state['conflict_resolution_dfs']]

    # if newly uploaded files are not as needed
    if len(new_quant_files) == 0 and len(new_trace_files) == 0:  # if no newly uploaded files, move on
        return
    elif len(new_quant_files) != len(new_trace_files):  # if newly uploaded files doesn't match, write message
        st.error('Added files are not in pair, so not parsed. \n Here are uploaded ones, but not parsed ones:')
        not_parsed = new_quant_files + new_trace_files
        for i in not_parsed:
            st.markdown("- " + i)
        return
    elif (len(new_resolution_files) > 0) & (len(new_quant_files) != len(new_resolution_files)):
        st.error('Added files (including conflict resolution) are not in pair, so not parsed. \n Here are uploaded ones, but not parsed ones:')
        not_parsed = new_quant_files + new_trace_files + new_resolution_files
        for i in not_parsed:
            st.markdown("- " + i)
        return

    # parse newly uploaded files
    new_deconv_files = sorted(new_quant_files)
    new_anno_files = sorted(new_trace_files)
    if new_resolution_files:
        new_resolution_files = sorted(new_resolution_files)
    parsingWithProgressBar(new_deconv_files, new_anno_files, new_resolution_files)


def parsingWithProgressBar(infiles_quant, infiles_trace, infiles_resolution):
    with st.session_state['progress_bar_space']:
        if not infiles_resolution:
            infiles_resolution = [''] * len(infiles_quant)
        for quant_f, trace_f, resolution_f in zip(infiles_quant, infiles_trace, infiles_resolution):
            if not quant_f.endswith('.tsv'):
                continue
            exp_name = quant_f[0: quant_f.rfind('.fdq')]

            with st.spinner('Parsing the experiment %s...' % exp_name):
                if resolution_f:
                    quant_df, trace_df, resolution_df = parseFLASHQuantOutput(
                        Path(st.session_state["workspace"], "quant-files", quant_f),
                        Path(st.session_state["workspace"], "trace-files", trace_f),
                        Path(st.session_state["workspace"], "conflict-resolution-files", resolution_f),
                    )
                    st.session_state['conflict_resolution_dfs'][resolution_f] = resolution_df
                else:
                    quant_df, trace_df, _ = parseFLASHQuantOutput(
                        Path(st.session_state["workspace"], "quant-files", quant_f),
                        Path(st.session_state["workspace"], "trace-files", trace_f),
                    )
                st.session_state['quant_dfs'][quant_f] = connectTraceWithResult(quant_df, trace_df)
                st.session_state['trace_dfs'][trace_f] = []  # need key name, so saving only empty array
            st.success('Done parsing the experiment %s!' % exp_name)


# page initialization
params = page_setup()

# make directory to store files & initialize data storage
input_file_types = ["quant-files", "trace-files", "conflict-resolution-files"]
parsed_df_types = ["quant_dfs", "trace_dfs", "conflict_resolution_dfs"]
initializeWorkspace(input_file_types, parsed_df_types)

st.title("File Upload")

tabs = st.tabs(["File Upload", "Example Data"])

# Load Example Data
with tabs[1]:
    st.markdown("An example truncated file from the E. coli dataset.")
    _, c2, _ = st.columns(3)
    if c2.button("Load Example Data", type="primary"):
        # loading and copying example files into default workspace
        for filetype, session_name in zip(['*fdq.tsv', '*fdq.mts.tsv', '*fdq_shared.tsv'],
                                          input_file_types):
            for file in Path("example-data").glob(filetype):
                if file.name not in st.session_state[session_name]:
                    shutil.copy(file, Path(st.session_state["workspace"], session_name, file.name))
                    st.session_state[session_name].append(file.name)
        # parsing the example files is done in parseUploadedFiles later
        st.success("Example mzML files loaded!")

# Upload files via upload widget
with tabs[0]:
    # Upload files via upload widget
    st.subheader("**Upload FLASHQuant output files**")

    # Display info how to upload files
    st.info(
        """
    **💡 How to upload files**
    
    1. Browse files on your computer or drag and drops files
    2. Click the **Add the uploaded quant files** button to use them in the workflows
    
    Select data for analysis from the uploaded files shown below.
    
    **💡 Make sure that the same number of FLASHQuant result files (\*fdq.tsv and \*fdq.mts.tsv) are uploaded!**
    
    **💡 To visualize conflict resolution, \*fdq_shared.tsv files should be uploaded**
    """
    )
    with st.form('files_uploader_form', clear_on_submit=True):
        uploaded_file = st.file_uploader(
            "FLASHQuant output files", accept_multiple_files=True
        )
        _, c2, _ = st.columns(3)
        # User needs to click button to upload selected files
        if c2.form_submit_button("Add the tsv files", type="primary"):
            # Copy uploaded files to *-files directory
            if uploaded_file:
                # A list of files is required, since online allows only single upload, create a list
                if type(uploaded_file) != list:
                    uploaded_file = [uploaded_file]

                # opening file dialog and closing without choosing a file results in None upload
                handleInputFiles(uploaded_file)
                st.success("Successfully added uploaded files!")
            else:
                st.warning("Upload some files before adding them.")

# parse files if newly uploaded
st.session_state['progress_bar_space'] = st.container()
parseUploadedFiles()

# for error message or list of uploaded files
quant_files = sorted(st.session_state["quant_dfs"].keys())
trace_files = sorted(st.session_state["trace_dfs"].keys())
res_files = sorted(st.session_state["conflict_resolution_dfs"].keys())

# error message if files not exist
if len(quant_files) == 0 and len(trace_files) == 0:
    st.info('No mzML added yet!', icon="ℹ️")
elif len(quant_files) == 0:
    st.error("FLASHQuant result file is not added yet!")
elif len(trace_files) == 0:
    st.error("FLASHQuant mass trace file is not added yet!")
elif len(quant_files) != len(trace_files):
    st.error("The same number of quant result and trace tsv file should be uploaded!")
else:
    v_space(2)
    st.session_state["quant-experiment-df"] = getUploadedFileDF(quant_files, trace_files, res_files)
    st.markdown('**Uploaded experiments in current workspace**')
    st.dataframe(st.session_state["quant-experiment-df"])  # show table
    v_space(1)

    # Remove files
    with st.expander("🗑️ Remove uploaded files"):
        to_remove = st.multiselect(
            "select uploaded experiments", options=st.session_state["quant-experiment-df"]['Experiment Name']
        )
        c1, c2 = st.columns(2)
        if c2.button(
                "Remove **selected**", type="primary", disabled=not any(to_remove)
        ):
            params = remove_selected_experiment_files(to_remove, params)
            st.rerun()

        if c1.button("⚠️ Remove **all**", disabled=not any(st.session_state["quant-experiment-df"])):
            for file_option, df_option in zip(input_file_types, parsed_df_types):
                if file_option in st.session_state:
                    reset_directory(Path(st.session_state.workspace, file_option))
                    st.session_state[file_option] = []
                if df_option in st.session_state:
                    st.session_state[df_option] = {}

            st.success("All experiment files removed!")
            del st.session_state["quant-experiment-df"]  # reset the experiment df table
            st.rerun()

save_params(params)
