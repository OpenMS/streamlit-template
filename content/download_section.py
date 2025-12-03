import streamlit as st

from pathlib import Path
import shutil

from src.common.common import page_setup
from zipfile import ZipFile, ZIP_DEFLATED

page_setup()

# Define output folder here; all subfolders will be handled as downloadable
# directories
output_folder = 'mzML-workflow-results'


# Generate full path
dirpath = Path(st.session_state["workspace"], output_folder)

# Detect downloadable content
if dirpath.exists():
    directories = sorted(
        [entry for entry in dirpath.iterdir() if not entry.is_file()]
    )
else:
    directories = []

# Show error if no content is available for download
if len(directories) == 0:
    st.error('No results to show yet. Please run a workflow first!')
else:
    # Table Header
    columns = st.columns(3)
    columns[0].write('**Run**')
    columns[1].write('**Download**')
    columns[2].write('**Delete Result Set**')

    # Table Body
    for i, directory in enumerate(directories):
        st.divider()
        columns = st.columns(3)
        columns[0].empty().write(directory.name)
        
        with columns[1]:
            button_placeholder = st.empty()
            
            # Show placeholder button before download is prepared
            clicked = button_placeholder.button('Prepare Download', key=i, use_container_width=True)
            if clicked:
                button_placeholder.empty()
                with st.spinner():
                    # Create ZIP file
                    out_zip = Path(directory, 'output.zip')
                    if not out_zip.exists():
                        with ZipFile(out_zip, 'w', ZIP_DEFLATED) as zip_file:
                            for output in Path(directory).iterdir():
                                if output.name == 'output.zip':
                                    continue
                                try:
                                    with open(output, 'r') as f:
                                        zip_file.writestr(output.name, f.read())
                                except:
                                    continue
                    # Show download button after ZIP file was created
                    with open(out_zip, 'rb') as f:
                        button_placeholder.download_button(
                            "Download ⬇️", f, 
                            file_name = f'{directory.name}.zip',
                            use_container_width=True
                        )

        with columns[2]:
            if st.button(f"🗑️ {directory.name}", use_container_width=True):
                shutil.rmtree(directory)
                st.rerun()