import streamlit as st

from os.path import join, exists, dirname, isfile
from os import listdir

from src.common import page_setup
from io import StringIO, BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from pages.FileUpload import initializeWorkspace, showUploadedFilesTable


def content():
    page_setup("TaggerViewer")

    dirpath = join(st.session_state["workspace"], 'FLASHDeconvOutput')

    if exists(dirpath):
        directories = sorted(
            [
                entry for entry in listdir(dirpath) 
                if isfile(join(dirpath, entry, 'output.zip'))
            ]
        )
    else:
        directories = []

    if len(directories) == 0:
        st.error('No results to show yet. Please run a workflow first!')
        return
    
    # Table Header
    columns = st.columns((0.4, 0.6))
    columns[0].write('**Run**')
    columns[1].write('**Download**')

    # if 'FLASHDeconvButtons' not in st.session_state:
    #     all_buttons = {}
    #     for directory in directories:
    #         all_buttons[directory] = False
    #     st.session_state['FLASHDeconvButtons'] = all_buttons

    # Table Body
    for i, directory in enumerate(directories):
        st.divider()
        columns = st.columns((0.4, 0.6))
        columns[0].empty().write(directory)
        button_placeholder = columns[1].empty()

        # if st.session_state['FLASHDeconvButtons'][directory]:

        
        clicked = button_placeholder.button('Prepare Download', key=i)
        if clicked:
            button_placeholder.empty()
            with st.spinner():
                with open(join(dirpath, directory, 'output.zip'), 'rb') as f:
                    button_placeholder.download_button(
                        "Download ⬇️", f, 
                        file_name = f'{directory}.zip'
                    )

if __name__ == "__main__":
    content()
