import shutil
from pathlib import Path

import streamlit as st

from src.common.common import reset_directory


@st.cache_data
def save_uploaded_fasta(uploaded_files: list[bytes]) -> None:
    """
    Saves uploaded fasta files to the fasta directory.

    Args:
        uploaded_files (List[bytes]): List of uploaded fasta files.

    Returns:
        None
    """
    fasta_dir = Path(st.session_state.workspace, "fasta-files")
    # A list of files is required, since online allows only single upload, create a list
    if st.session_state.location == "online":
        uploaded_files = [uploaded_files]
    # If no files are uploaded, exit early
    if not uploaded_files:
        st.warning("Upload some files first.")
        return
    # Write files from buffer to workspace fasta directory, add to selected files
    for f in uploaded_files:
        if f.name not in [f.name for f in fasta_dir.iterdir()] and f.name.endswith(
            "fasta"
        ):
            with open(Path(fasta_dir, f.name), "wb") as fh:
                fh.write(f.getbuffer())
    st.success("Successfully added uploaded files!")


def copy_local_fasta_files_from_directory(local_fasta_directory: str) -> None:
    """
    Copies local fasta files from a specified directory to the fasta directory.

    Args:
        local_fasta_directory (str): Path to the directory containing the fasta files.

    Returns:
        None
    """
    fasta_dir = Path(st.session_state.workspace, "fasta-files")
    # Check if local directory contains fasta files, if not exit early
    if not any(Path(local_fasta_directory).glob("*.fasta")):
        st.warning("No fasta files found in specified folder.")
        return
    # Copy all fasta files to workspace fasta directory, add to selected files
    files = Path(local_fasta_directory).glob("*.fasta")
    for f in files:
        shutil.copy(f, Path(fasta_dir, f.name))
    st.success("Successfully added local files!")


def load_example_fasta_files() -> None:
    """
    Copies example fasta files to the fasta directory.

    Args:
        None

    Returns:
        None
    """
    fasta_dir = Path(st.session_state.workspace, "fasta-files")
    # Copy files from example-data/fasta to workspace fasta directory, add to selected files
    for f in Path("example-data", "fasta").glob("*.fasta"):
        shutil.copy(f, fasta_dir)
    st.success("Example fasta files loaded!")


def remove_selected_fasta_files(to_remove: list[str], params: dict) -> dict:
    """
    Removes selected fasta files from the fasta directory.

    Args:
        to_remove (List[str]): List of fasta files to remove.
        params (dict): Parameters.


    Returns:
        dict: parameters with updated fasta files
    """
    fasta_dir = Path(st.session_state.workspace, "fasta-files")
    # remove all given files from fasta workspace directory and selected files
    for f in to_remove:
        Path(fasta_dir, f + ".fasta").unlink()
    for k, v in params.items():
        if isinstance(v, list):
            if f in v:
                params[k].remove(f)
    st.success("Selected fasta files removed!")
    return params


def remove_all_fasta_files(params: dict) -> dict:
    """
    Removes all fasta files from the fasta directory.

    Args:
        params (dict): Parameters.

    Returns:
        dict: parameters with updated fasta files
    """
    fasta_dir = Path(st.session_state.workspace, "fasta-files")
    # reset (delete and re-create) fasta directory in workspace
    reset_directory(fasta_dir)
    # reset all parameter items which have fasta in key and are list
    for k, v in params.items():
        if "fasta" in k and isinstance(v, list):
            params[k] = []
    st.success("All fasta files removed!")
    return params
