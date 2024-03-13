import streamlit as st
from pathlib import Path
import pyopenms as poms
import pandas as pd
import time
from src.common import reset_directory


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


def run_workflow(params, result_dir):
    """Load each mzML file into pyOpenMS Experiment and get the number of spectra."""

    # delete old workflow results and set new directory
    reset_directory(result_dir)

    # collect spectra numbers
    num_spectra = []

    # use st.status to print info while running the workflow
    with st.status(
        "Loading mzML files and getting number of spectra...", expanded=True
    ) as status:
        # get selected mzML files from parameters
        for file in params["example-workflow-selected-mzML-files"]:
            # logging file name in status
            st.write(f"Reading mzML file: {file} ...")

            # reading mzML file, getting num spectra and adding some extra time
            num_spectra.append(
                mzML_file_get_num_spectra(
                    str(
                        Path(
                            st.session_state["workspace"], "mzML-files", file + ".mzML"
                        )
                    )
                )
            )

        # set status as complete and collapse box
        status.update(label="Complete!", expanded=False)

    # create and save result dataframe
    df = pd.DataFrame(
        {
            "filenames": params["example-workflow-selected-mzML-files"],
            "number of spectra": num_spectra,
        }
    )
    df.to_csv(Path(result_dir, "result.tsv"), sep="\t", index=False)
