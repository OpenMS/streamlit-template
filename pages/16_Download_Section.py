import streamlit as st

from os.path import join, exists, isfile, basename
from os import listdir

from src.common import page_setup
from io import StringIO, BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

# Define output folder here; all subfolders will be handled as downloadable
# directories
output_folder = 'your_folder_goes_here'

def content():
    page_setup()

    # Generate full path
    dirpath = join(st.session_state["workspace"], output_folder)
    
    # Detect downloadable content
    if exists(dirpath):
        directories = sorted(
            [entry for entry in listdir(dirpath) if not isfile(entry)]
        )
    else:
        directories = []

    # Show error if no content is available for download
    if len(directories) == 0:
        st.error('No results to show yet. Please run a workflow first!')
        return
    
    # Table Header
    columns = st.columns((0.4, 0.6))
    columns[0].write('**Run**')
    columns[1].write('**Download**')

    # Table Body
    for i, directory in enumerate(directories):
        st.divider()
        columns = st.columns((0.4, 0.6))
        columns[0].empty().write(directory)
        
        with columns[1]:
            button_placeholder = st.empty()
            
            # Show placeholder button before download is prepared
            clicked = button_placeholder.button('Prepare Download', key=i)
            if clicked:
                button_placeholder.empty()
                with st.spinner():
                    # Create ZIP file
                    out_zip = join(dirpath, directory, 'output.zip')
                    if not exists(out_zip):
                        with ZipFile(out_zip, 'w', ZIP_DEFLATED) as zip_file:
                            for output in listdir(join(dirpath, directory)):
                                try:
                                    with open(join(dirpath, directory, output), 'r') as f:
                                        zip_file.writestr(basename(output), f.read())
                                except:
                                    continue
                    # Show download button after ZIP file was created
                    with open(out_zip, 'rb') as f:
                        button_placeholder.download_button(
                            "Download ⬇️", f, 
                            file_name = f'{directory}.zip'
                        )

if __name__ == "__main__":
    content()
