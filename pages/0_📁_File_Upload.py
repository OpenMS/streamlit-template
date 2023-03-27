import streamlit as st
from src.common import *
from pathlib import Path
import os
import shutil


def showingUploadedFiles(param, param1):
    deconv_files = sorted(Path(st.session_state["deconv-mzMLs"]).iterdir())
    anno_files = sorted(Path(st.session_state["anno-mzMLs"]).iterdir())

    # Error message!
    if len(deconv_files) != len(anno_files):
        st.error("The same number of deconvolved and annotated mzML file should be uploaded!")
        return

    # leave only names
    deconv_files = [f.name for f in deconv_files]
    anno_files = [f.name for f in anno_files]

    # getting experiment name from deconv file
    experiment_names = [f[0: f.rfind('_')] for f in deconv_files]

    df = pd.DataFrame({'Experiment Name': experiment_names,
                       'Deconvolved Files': deconv_files,
                       'Annotated Files': anno_files})
    st.session_state["experiment-df"] = df
    st.markdown('**Uploaded experiments**')
    st.dataframe(df)
    return

def content():
    page_setup()

    # make directory to store deconv and anno mzML files
    input_types = ["deconv-mzMLs", "anno-mzMLs", "fasta-files"] # TODO: add raw mzML section
    for dirnames in input_types:
        if not os.path.isdir(st.session_state[dirnames]):
            os.mkdir(st.session_state[dirnames])

    c1, c2, c3 = st.columns([0.6, 0.2, 0.2])
    # c1, c2, c3 = st.columns(3)
    c1.title("File Upload")

    # Load Example Data
    v_space(1, c2)
    if c2.button("Load Example Data"): # TODO: change here!
        for file in Path("example-data", "mzML").glob("*.mzML"):
            shutil.copy(file, Path(st.session_state["mzML-files"]))

    # Delete all uploaded files
    v_space(1, c3)
    if c3.button("Delete uploaded Data"):
        for file_option in input_types:
            if file_option in st.session_state:
                reset_directory(st.session_state[file_option])

    # Display info how to upload files
    st.info(
        """
    **💡 How to upload files**

    1. Browse files on your computer or drag and drops files
    2. Click the **Add the uploaded mzML files** button to use them in the workflows

    Select data for analysis from the uploaded files shown in the sidebar.
    
    **💡 Make sure that the same number of deconvolved and annotated mzML files are uploaded!**
    """
    )

    # Online accept only one file per upload, local is unrestricted
    accept_multiple = True
    if st.session_state.location == "online":
        accept_multiple = False

    # Upload files via upload widget
    st.subheader("**Upload mzML files**")

    for form_name, title_on_button, session_name in zip(["deconv-form", "anno-form"],
                                                        ["deconvolved mzML", "annotated mzML"],
                                                        ["deconv-mzMLs", "anno-mzMLs"]):
        with st.form(form_name, clear_on_submit=True):
            uploaded_file = st.file_uploader(
                "%s files"%title_on_button, accept_multiple_files=accept_multiple
            )
            _, c2, _ = st.columns(3)
            # User needs to click button to upload selected files
            submitted = c2.form_submit_button("Add the uploaded %s files"%title_on_button)
            if submitted:
                # Need to have a list of uploaded files to copy to the mzML dir,
                # in case of online only a single item is return, so we put it in the list
                if st.session_state.location == "online":
                    uploaded_file = [uploaded_file]
                # Copy uploaded mzML files to deconv-mzML-files directory
                if uploaded_file:
                    # opening file dialog and closing without choosing a file results in None upload
                    for file in uploaded_file:
                        if file.name not in st.session_state[session_name].iterdir() and file.name.endswith("mzML"):
                            with open(
                                Path(st.session_state[session_name], file.name), "wb"
                            ) as f:
                                f.write(file.getbuffer())
                    st.success("Successfully added uploaded files!")
                else:
                    st.warning("Upload some files before adding them.")

    # for error message or list of uploaded files
    if "deconv-mzMLs" in st.session_state and "anno-mzMLs" in st.session_state:
        showingUploadedFiles(st.session_state["deconv-mzMLs"], st.session_state["anno-mzMLs"])
    elif ("deconv-mzMLs" not in st.session_state) and ("anno-mzMLs" not in st.session_state):
        st.info('No mzML added yet!', icon="ℹ️")
    elif "deconv-mzMLs" not in st.session_state:
        st.error("FLASHDeconv deconvolved mzML file is not added yet!")
    elif "anno-mzMLs" not in st.session_state:
        st.error("FLASHDeconv annotated mzML file is not added yet!")

    # Upload files via upload widget
    st.subheader("Upload fasta files")
    with st.form("fasta-form", clear_on_submit=True):
        uploaded_fasta = st.file_uploader(
            "fasta files", accept_multiple_files=accept_multiple
        )
        _, c2, _ = st.columns(3)
        # User needs to click button to upload selected files
        submitted = c2.form_submit_button("Add the uploaded fasta files")
        if submitted:
            # Need to have a list of uploaded files to copy to the mzML dir,
            # in case of online only a single item is return, so we put it in the list
            if st.session_state.location == "online":
                uploaded_fasta = [uploaded_fasta]
            # Copy uploaded mzML files to mzML-files directory
            if uploaded_fasta:
                # opening file dialog and closing without choosing a file results in None upload
                for file in uploaded_fasta:
                    if file.name not in st.session_state[
                        "fasta-files"
                    ].iterdir() and file.name.endswith("fasta"):
                        with open(
                                Path(st.session_state["fasta-files"], file.name), "wb"
                        ) as f:
                            f.write(file.getbuffer())
                st.success("Successfully added uploaded files!")
            else:
                st.warning("Upload some files before adding them.")

    # TODO: figure out what to do with here
    # # Local file upload option: via directory path
    # if st.session_state.location == "local":
    #     st.markdown("**OR specify the path to a folder containing your mzML files**")
    #     c1, c2 = st.columns([0.8, 0.2])
    #     upload_dir = c1.text_input("path to folder with mzML files")
    #     upload_dir = r"{}".format(upload_dir)
    #     c2.markdown("##")
    #     if c2.button("Upload"):
    #         uploaded_mzML = Path("example-data", "mzML").glob("*.mzML")
    #         with st.spinner("Uploading files..."):
    #             for file in Path(upload_dir).glob("*.mzML"):
    #                 if file.name not in st.session_state["mzML-files"].iterdir():
    #                     shutil.copy(file, st.session_state["mzML-files"])
    #             st.success("Successfully added uploaded files!")


if __name__ == "__main__":
    # try:
    content()
# except:
#     st.error(ERRORS["general"])
