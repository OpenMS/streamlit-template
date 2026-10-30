import streamlit as st

from pathlib import Path
import shutil

from src.common.common import page_setup, export_files, export_folder_input
from zipfile import ZipFile, ZIP_DEFLATED

page_setup()

# A local install exports each run to a folder on disk instead of downloading it.
local = st.session_state.location == "local"
st.title("Export Results" if local else "Download Results")
if local:
    export_dir = export_folder_input("results-export")

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
    columns[1].write('**Export**' if local else '**Download**')
    columns[2].write('**Delete Result Set**')

    # Table Body
    for i, directory in enumerate(directories):
        st.divider()
        columns = st.columns(3)
        columns[0].empty().write(directory.name)
        
        with columns[1]:
            if local:
                # One click copies the run's files to <export folder>/<run>.
                if st.button('📤 Export', key=i, use_container_width=True):
                    export_files(
                        [
                            (f, f.relative_to(directory))
                            for f in sorted(directory.rglob('*'))
                            if f.is_file() and f.name != 'output.zip'
                        ],
                        Path(export_dir, directory.name),
                    )
                clicked = False
            else:
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