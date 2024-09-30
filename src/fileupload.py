import shutil
from pathlib import Path

import streamlit as st

from src.common.common import reset_directory


@st.cache_data
def save_uploaded_mzML(uploaded_files: list[bytes]) -> None:
    """
    Saves uploaded mzML files to the mzML directory.

    Args:
        uploaded_files (List[bytes]): List of uploaded mzML files.

    Returns:
        None
    """
    mzML_dir = Path(st.session_state.workspace, "mzML-files")
    # A list of files is required, since online allows only single upload, create a list
    if st.session_state.location == "online":
        uploaded_files = [uploaded_files]
    # If no files are uploaded, exit early
    if not uploaded_files:
        st.warning("Upload some files first.")
        return
    # Write files from buffer to workspace mzML directory, add to selected files
    for f in uploaded_files:
        if f.name not in [f.name for f in mzML_dir.iterdir()] and f.name.endswith(
            "mzML"
        ):
            with open(Path(mzML_dir, f.name), "wb") as fh:
                fh.write(f.getbuffer())
    st.success("Successfully added uploaded files!")



def copy_local_mzML_files_from_directory(local_mzML_directory: str, make_copy: bool=True) -> None:
    """
    Copies local mzML files from a specified directory to the mzML directory.

    Args:
        local_mzML_directory (str): Path to the directory containing the mzML files.
        make_copy (bool): Whether to make a copy of the files in the workspace. Default is True. If False, local file paths will be written to an external_files.txt file.

    Returns:
        None
    """
    mzML_dir = Path(st.session_state.workspace, "mzML-files")
    # Check if local directory contains mzML files, if not exit early
    if not any(Path(local_mzML_directory).glob("*.mzML")):
        st.warning("No mzML files found in specified folder.")
        return
    # Copy all mzML files to workspace mzML directory, add to selected files
    files = Path(local_mzML_directory).glob("*.mzML")
    for f in files:
        if make_copy:
            shutil.copy(f, Path(mzML_dir, f.name))
        else:
            # Create a temporary file to store the path to the local directories
            external_files = Path(mzML_dir, "external_files.txt")
            # Check if the file exists, if not create it
            if not external_files.exists():
                external_files.touch()
            # Write the path to the local directories to the file
            with open(external_files, "a") as f_handle:
                f_handle.write(f"{f}\n")
                
    st.success("Successfully added local files!")


def load_example_mzML_files() -> None:
    """
    Copies example mzML files to the mzML directory.

    Args:
        None

    Returns:
        None
    """
    mzML_dir = Path(st.session_state.workspace, "mzML-files")
    # Copy files from example-data/mzML to workspace mzML directory, add to selected files
    for f in Path("example-data", "mzML").glob("*.mzML"):
        shutil.copy(f, mzML_dir)
    st.success("Example mzML files loaded!")


def remove_selected_mzML_files(to_remove: list[str], params: dict) -> dict:
    """
    Removes selected mzML files from the mzML directory.

    Args:
        to_remove (List[str]): List of mzML files to remove.
        params (dict): Parameters.


    Returns:
        dict: parameters with updated mzML files
    """
    mzML_dir = Path(st.session_state.workspace, "mzML-files")
    # remove all given files from mzML workspace directory and selected files
    for f in to_remove:
        Path(mzML_dir, f + ".mzML").unlink()
    for k, v in params.items():
        if isinstance(v, list):
            if f in v:
                params[k].remove(f)
    st.success("Selected mzML files removed!")
    return params


def remove_all_mzML_files(params: dict) -> dict:
    """
    Removes all mzML files from the mzML directory.

    Args:
        params (dict): Parameters.

    Returns:
        dict: parameters with updated mzML files
    """
    mzML_dir = Path(st.session_state.workspace, "mzML-files")
    # reset (delete and re-create) mzML directory in workspace
    reset_directory(mzML_dir)
    # reset all parameter items which have mzML in key and are list
    for k, v in params.items():
        if "mzML" in k and isinstance(v, list):
            params[k] = []
    st.success("All mzML files removed!")
    return params

@st.cache_data

def add_to_selected_fasta(filename: str):
    """
    Add the given filename to the list of selected fasta files.

    Args:
        filename (str): The filename to be added to the list of selected fasta files.

    Returns:
        None
    """
    # Check if file in params selected fasta files, if not add it
    if filename not in st.session_state["selected-fasta-files"]:
        #st.write("")
        st.session_state["selected-fasta-files"].append(filename)

def save_uploaded_fasta(uploaded_files: list[bytes]) -> None:
    """
    Saves uploaded fasta files to the fasta directory.

    Args:
        uploaded_files (List[bytes]): List of uploaded fasta files.

    Returns:
        None
    """
    fasta_dir: Path = Path(st.session_state.workspace, "fasta-files")

    # A list of files is required, since online allows only single upload, create a list
    if st.session_state.location == "online":
        uploaded_files = [uploaded_files]

    # If no files are uploaded, exit early
    for f in uploaded_files:
        if f is None:
            st.warning("Upload some files first.")
            return
        
    # Write files from buffer to workspace fasta directory, add to selected files
    for f in uploaded_files:
        if f.name not in [f.name for f in fasta_dir.iterdir()] and f.name.endswith("fasta"):
            with open(Path(fasta_dir, f.name), "wb") as fh:
                fh.write(f.getbuffer())
        add_to_selected_fasta(Path(f.name).stem)
    st.success("Successfully added uploaded files!")

def load_example_fasta_files() -> None:
    """
    Copies example fasta files to the fasta directory.

    Args:
        None

    Returns:
        None
    """

    fasta_dir: Path = Path(st.session_state.workspace, "fasta-files")

    # Copy files from example-data/fasta to workspace fasta directory, add to selected files
    for f in Path("example-data", "fasta").glob("*.fasta"):
        shutil.copy(f, fasta_dir)
        add_to_selected_fasta(f.stem)
    #st.success("Example fasta files loaded!")

@st.cache_data
def copy_local_fasta_files_from_directory(local_fasta_directory: str) -> None:
    """
    Copies local fasta files from a specified directory to the fasta directory.

    Args:
        local_fasta_directory (str): Path to the directory containing the fasta files.

    Returns:
        None
    """
    fasta_dir: Path = Path(st.session_state.workspace, "fasta-files")

    # Check if local directory contains fasta files, if not exit early
    if not any(Path(local_fasta_directory).glob("*.fasta")):
        st.warning("No fasta files found in specified folder.")
        return
    # Copy all fasta files to workspace fasta directory, add to selected files
    files = Path(local_fasta_directory).glob("*.fasta")
    for f in files:
        if f.name not in fasta_dir.iterdir():
            shutil.copy(f, fasta_dir)
        add_to_selected_fasta(f.stem)
    st.success("Successfully added local files!")

def remove_selected_fasta_files(to_remove: list[str]) -> None:
    """
    Removes selected fasta files from the fasta directory.

    Args:
        to_remove (List[str]): List of fasta files to remove.

    Returns:
        None
    """
    fasta_dir: Path = Path(st.session_state.workspace, "fasta-files")

    # remove all given files from fasta workspace directory and selected files
    for f in to_remove:
        Path(fasta_dir, f+".fasta").unlink()
        st.session_state["selected-fasta-files"].remove(f)
    st.success("Selected fasta files removed!")


def remove_all_fasta_files() -> None:
    """
    Removes all fasta files from the fasta directory.

    Args:
        None

    Returns:
        None
    """
    fasta_dir: Path = Path(st.session_state.workspace, "fasta-files")

    # reset (delete and re-create) fasta directory in workspace
    reset_directory(fasta_dir)
    # reset selected fasta list
    st.session_state["selected-fasta-files"] = []
    st.success("All fasta files removed!")