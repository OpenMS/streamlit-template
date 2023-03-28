import streamlit as st
from src.common import defaultPageSetup
from pathlib import Path
import os

def readingInputFiles():
    st.subheader('File uploads')

    # make sure directory for input mzML files are ready
    input_file_location = "mzML-files"
    if (input_file_location not in st.session_state) or \
        (not os.path.isdir(st.session_state[input_file_location])):
        st.session_state[input_file_location] = Path(st.session_state["workspace"], input_file_location)
        st.session_state[input_file_location].mkdir(parents=True, exist_ok=True)

    # input file form
    with st.form("fd-form", clear_on_submit=True):
        uploaded_mzML = st.file_uploader(
            "raw mzML files", accept_multiple_files=True
        )
        _, c2, _ = st.columns(3) # for center-align
        # User needs to click button to upload selected files
        submitted = c2.form_submit_button("Add the uploaded mzML files")
        if submitted:
            # Need to have a list of uploaded files to copy to the mzML dir,
            # in case of online only a single item is return, so we put it in the list
            if st.session_state.location == "online":
                uploaded_mzML = [uploaded_mzML]
            # Copy uploaded mzML files to mzML-files directory
            if uploaded_mzML:
                # opening file dialog and closing without choosing a file results in None upload
                for file in uploaded_mzML:
                    if file.name not in st.session_state[
                        "mzML-files"
                    ].iterdir() and file.name.endswith("mzML"):
                        with open(
                                Path(st.session_state["mzML-files"], file.name), "wb"
                        ) as f:
                            f.write(file.getbuffer())
                st.success("Successfully added uploaded files!")
            else:
                st.warning("Upload some files before adding them.")

    # show input file list
    input_file_paths = sorted(Path(st.session_state["mzML-files"]).iterdir())
    if input_file_paths:
        input_file_string = [f.name for f in input_file_paths]

        st.info("**Uploaded input file**")
        for file_name in input_file_string:
            st.info(file_name)
    return

def running_fd():
    return

def content():
    defaultPageSetup("Running FLASHDeconv")

    # handling input
    readingInputFiles()

    # setting parameter

    # running button
    running_fd()

    # log?



if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])