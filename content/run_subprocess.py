import streamlit as st
import threading
import os

from pathlib import Path

from src.common.common import page_setup, save_params
from src.run_subprocess import run_subprocess

# Page name "workflow" will show mzML file selector in sidebar
params = page_setup()

st.title("Run subprocess")
st.markdown(
    """                 
        This example demonstrates how to run an external process (in this case, the Linux command 'grep' or 'findstr' for windows) as a subprocess to extract IDs from the selected mzML file while displaying the process output. 
        It also works with longer-running processes, such as calling an OpenMS TOPP tool.
        """
)

# Define the directory where mzML files are located
mzML_dir: Path = Path(st.session_state.workspace, "mzML-files")

# Create two columns for the Streamlit app layout
col1, col2 = st.columns(2)

# Use the `glob` method to get a list of all files in the directory
file_list = list(mzML_dir.glob("*"))

# select box to select file from user
file_name = st.selectbox("**Please select file**", [file.stem for file in file_list])

# full path of file
mzML_file_path = os.path.join(mzML_dir, str(file_name) + ".mzML")

# Create a dictionary to capture the output and status of the subprocess
result_dict = {}
result_dict["success"] = False
result_dict["log"] = " "

# Create a flag to terminate the subprocess
terminate_flag = threading.Event()
terminate_flag.set()


# Function to terminate the subprocess
def terminate_subprocess():
    """Set flag to terminate subprocess."""
    global terminate_flag
    terminate_flag.set()


# Check if the "Extract ids" button is clicked
if st.button("Extract ids"):
    # Check if the "Terminate/Clear" button is clicked to stop the subprocess and clear the form
    if st.button("Terminate/Clear"):
        # Terminate the subprocess
        terminate_subprocess()
        st.warning("Process terminated. The analysis may not be complete.")
        # Reset the page
        st.rerun()

    # Display a status message while running the analysis
    with st.status("Please wait until fetching all ids from mzML 😑"):

        # Define the command to run as a subprocess (example: grep or findstr (for windows))
        # 'nt' indicates Windows
        if os.name == 'nt':  
            args = ["findstr", "idRef", mzML_file_path]
        else:  
            # Assume 'posix' for Linux and macOS
            args =["grep", "idRef", mzML_file_path]

        # Display the command that will be executed
        message = f"Running command: {' '.join(args)}"
        st.code(message)

        # Run the subprocess command
        run_subprocess(args, result_dict)

    # Check if the subprocess was successful
    if result_dict["success"]:
        # Here can add code here to handle the results, e.g., display them to the user

        pass  # Placeholder for result handling


# At the end of each page, always save parameters (including any changes via widgets with key)
save_params(params)
