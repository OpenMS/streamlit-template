import streamlit as st
from pathlib import Path
import pyopenms as poms
import pandas as pd
import time
from datetime import datetime
from src.common.common import reset_directory, show_fig, show_table
import plotly.express as px
from src.workflow.mzmlfileworkflowstatus import log_mzml_workflow_progress

def mzML_file_get_num_spectra(filepath):
    """
    Load an mzML file, retrieve the number of spectra, and return it.

    This function loads an mzML file specified by `filepath` and extracts the number of spectra
    contained within the file using the OpenMS library. It temporarily pauses for 2 seconds to
    simulate a heavy task before retrieving the number of spectra.

    Args:
        filepath (str): The path to the mzML file to be loaded and analyzed.

    Returns:
        int: The number of spectra present in the mzML file.
    """
    exp = poms.MSExperiment()
    poms.MzMLFile().load(filepath, exp)
    time.sleep(2)
    return exp.size()

def run_workflow(params, result_dir, workspace_path):
    """Load each mzML file into pyOpenMS Experiment and get the number of spectra."""

    result_dir = Path(result_dir, datetime.now().strftime("%Y-%m-%d %H_%M_%S"))
    # delete old workflow results and set new directory
    reset_directory(result_dir)

    # collect spectra numbers
    num_spectra = []

    log_mzml_workflow_progress("Loading mzML files and getting number of spectra...")
    for file in params["example-workflow-selected-mzML-files"]:
        # reading mzML file, getting num spectra and adding some extra time
        log_mzml_workflow_progress(f"Reading mzML file: {file} ...")
        num_spectra.append(
            mzML_file_get_num_spectra(
                str(
                    Path(
                        workspace_path, "mzML-files", file + ".mzML"
                    )
                )
            )
        )
    # create and save result dataframe
    df = pd.DataFrame(
        {
            "filenames": params["example-workflow-selected-mzML-files"],
            "number of spectra": num_spectra,
        }
    )
    df.to_csv(Path(result_dir, "result.tsv"), sep="\t", index=False)

@st.fragment
def result_section(result_dir):
    if not Path(result_dir).exists():
        st.error("No results to show yet. Please run a workflow first!")
        return

    date_strings = [f.name for f in Path(result_dir).iterdir() if f.is_dir()]

    result_dirs = sorted(date_strings, key=lambda date: datetime.strptime(date, "%Y-%m-%d %H_%M_%S"))[::-1]

    run_dir = st.selectbox("select result from run", result_dirs)

    if run_dir is None:
        st.error("Please select a result from a run!")
        return

    result_dir = Path(result_dir, run_dir)
    # visualize workflow results if there are any
    result_file_path = Path(result_dir, "result.tsv")

    if result_file_path.exists():
        df = pd.read_csv(result_file_path, sep="\t", index_col="filenames")

        if not df.empty:
            tabs = st.tabs(["📁 data", "📊 plot"])

            with tabs[0]:
                show_table(df, "mzML-workflow-result")

            with tabs[1]:
                fig = px.bar(df)
                st.info(
                    "💡 Download figure with camera icon in top right corner. File format can be specified in settings."
                )
                show_fig(fig, "mzML-workflow-results")