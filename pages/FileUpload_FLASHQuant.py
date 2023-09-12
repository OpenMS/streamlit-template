import streamlit as st
from pathlib import Path
import shutil
import pandas as pd
from src.flashquant import parseFLASHQuantOutput
from src.common import v_space, defaultPageSetup, reset_directory
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


def showUploadedFilesTable():
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
        st.session_state["quant-experiment-df"] = getUploadedFileDF(quant_files, trace_files, res_files)
        st.markdown('**Uploaded experiments**')
        st.dataframe(st.session_state["quant-experiment-df"])


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


def content():
    defaultPageSetup()

    # make directory to store files & initialize data storage
    input_types = ["quant-files", "trace-files", "conflict-resolution-files"]
    parsed_df_types = ["quant_dfs", "trace_dfs", "conflict_resolution_dfs"]
    initializeWorkspace(input_types, parsed_df_types)

    c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
    c1.title("File Upload")

    # Load Example Data
    v_space(1, c2)
    if c2.button("Load Example Data"):
        # loading and copying example files into default workspace
        for filetype, session_name in zip(['*fdq.tsv', '*fdq.mts.tsv', '*fdq_shared.tsv'],
                                          input_types):
            for file in Path("example-data").glob(filetype):
                if file.name not in st.session_state[session_name]:
                    shutil.copy(file, Path(st.session_state["workspace"], session_name, file.name))
                    st.session_state[session_name].append(file.name)
        # parsing the example files is done in parseUploadedFiles later

    # Delete all uploaded files
    v_space(1, c3)
    if c3.button("Delete uploaded Data"):
        for file_option, df_option in zip(input_types, parsed_df_types):
            if file_option in st.session_state:
                reset_directory(Path(st.session_state["workspace"], file_option))
                st.session_state[file_option] = []
            if df_option in st.session_state:
                st.session_state[df_option] = {}

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

    # Upload files via upload widget
    st.subheader("**Upload FLASHQuant output files**")

    with st.form('files_uploader_form', clear_on_submit=True):
        uploaded_file = st.file_uploader(
            "FLASHQuant output files (multiple files are allowed)", accept_multiple_files=True
        )
        _, c2, _ = st.columns(3)
        # User needs to click button to upload selected files
        submitted = c2.form_submit_button("Add the tsv files")
        if submitted:
            # Need to have a list of uploaded files to copy to the files dir,
            # Copy uploaded files to *-files directory
            if uploaded_file:
                # opening file dialog and closing without choosing a file results in None upload
                handleInputFiles(uploaded_file)
                st.success("Successfully added uploaded files!")
            else:
                st.warning("Upload some files before adding them.")

    st.session_state['progress_bar_space'] = st.container()

    # parse files if newly uploaded
    parseUploadedFiles()

    # for error message or list of uploaded files
    showUploadedFilesTable()


if __name__ == "__main__":
    # try:
    content()
# except:
#     st.error(ERRORS["general"])
