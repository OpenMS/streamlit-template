import streamlit as st
from src.common import page_setup, v_space
from pathlib import Path
import os, subprocess

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
        input_file_string = ["* %s"%f.name for f in input_file_paths]
        if len(input_file_string) > 1:
            input_file_string = '\n'.join(input_file_string)
        else:
            input_file_string = input_file_string[0]

        output_string = "**Uploaded Files**\n" + input_file_string
        st.markdown(output_string)
    return

def popupForFLASHDeconvPath(error_msg=''):
    modal = st.expander("FLASHDeconv executable file path")
    modal.text_input("Enter absolute path for FLASHDeconv file 👇",
                     placeholder="i.e., /Applications/OpenMS/bin/FLASHDeconv",
                     key='input_fd_file_path')
    if error_msg:
        modal.error(error_msg)

def readFLASHDeconvPath():
    file_to_read_fd = 'flashdeconv_path.txt'
    if not os.path.exists(file_to_read_fd):
        # file doesn't exist. need to write one.
        popupForFLASHDeconvPath()
    else:
        st.write('reading existing file...')
        # read file
        f = open(file_to_read_fd, 'r')
        fd_path = f.read()
        f.close()

        # check if the file path is available
        if not os.path.exists(fd_path):
            popupForFLASHDeconvPath()
        else:
            st.session_state['flashdeconv-path'] = fd_path

def newFDpathListener():
    input_path = st.session_state['input_fd_file_path']
    if os.path.exists(input_path) and os.path.basename(input_path)=='FLASHDeconv':
        st.success('Sucessfully added!')
        st.session_state['flashdeconv-path'] = input_path
        # write it in the file
        f = open('flashdeconv_path.txt', "w")
        f.write(input_path)
        f.close()
        del st.session_state['input_fd_file_path']
    elif input_path != '': # something is given, but not appropriate
        popupForFLASHDeconvPath('Wrong file detected. Please set FLASHDeconv again')

def log_subprocess_output(pipe):
    for line in iter(pipe.readline, b''): # b'\n'-separated lines
        st.write(line)
        # logging.info('got line from subprocess: %r', line)

def runFLASHDeconv():
    # header part
    c1, c2 = st.columns([0.8, 0.2])
    c1.subheader('Run FLASHDeconv')

    if c2.button('Set FLASHDeconvPath'):
        readFLASHDeconvPath()

    # display if new FLASHDeconv path is detected
    if "input_fd_file_path" in st.session_state:
        st.write('lstener')
        newFDpathListener()

    # if FLASHDeconv is not ready, error message
    if "flashdeconv-path" not in st.session_state \
            or not st.session_state["flashdeconv-path"]:
        st.error('Please set FLASHDeconvPath first ☝️')
        return

    st.write(st.session_state["flashdeconv-path"])
    process = subprocess.Popen(st.session_state["flashdeconv-path"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # with process.stdout:
    #     log_subprocess_output(process.stdout)
    # exitcode = process.wait()  # 0 means success

    return

def content():
    page_setup("Running FLASHDeconv")

    # handling input
    readingInputFiles()

    # setting parameter

    # running button
    runFLASHDeconv()
    # log?



if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])