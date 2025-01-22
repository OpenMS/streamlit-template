"""
Main page for the OpenMS Template App.

This module sets up and displays the Streamlit app for the OpenMS Template App.
It includes:
- Setting the app title.
- Displaying a description.
- Providing a download button for the Windows version of the app.

Usage:
Run this script to launch the OpenMS Template App.

Note:
- If run in local mode, the CAPTCHA control is not applied.
- If not in local mode, CAPTCHA control is applied to verify the user.

Returns:
    None
"""

from pathlib import Path
import streamlit as st

from src.common.common import page_setup, v_space

page_setup(page="main")

st.markdown("# 👋 Quick Start")
st.markdown("## Template for OpenMS web apps using the **streamlit** framework")
c1, c2 = st.columns(2)
c1.markdown(
    """
## ⭐ Features
       
- Simple workflows with **pyOpenMS** 
- Complex workflows utilizing **OpenMS TOPP tools** with parallel execution.
- Workspaces for user data with unique shareable IDs
- Persistent parameters and input files within a workspace
- Captcha control
- Packaged executables for Windows
- Deploy multiple apps easily with [docker-compose](https://github.com/OpenMS/streamlit-deployment)
"""
)
v_space(1, c2)
c2.image("assets/pyopenms_transparent_background.png", width=300)
if Path("OpenMS-App.zip").exists():
    st.subheader(
        """
Download the latest version for Windows here by clicking the button below.
"""
    )
    with open("OpenMS-App.zip", "rb") as file:
        st.download_button(
            label="Download for Windows",
            data=file,
            file_name="OpenMS-App.zip",
            mime="archive/zip",
            type="primary",
        )
    st.markdown(
        """
Extract the zip file and run the installer (.msi) file to install the app. The app can then be launched using the corresponding desktop icon.
"""
    )

st.markdown("## 📖 Documentation")
st.markdown(
    f"""
This template app includes documentation for **users** including **installation** and introduction to template specific concepts such as **workspaces** and developers with detailed instructions on **how to create and deploy your own app** based on this template.
"""
)
st.page_link(
    "content/documentation.py",
    label="Read documentation here, select chapter in the content menu.",
    icon="➡️",
)

st.markdown(
    """##  Workspaces and Settings
The **sidebar** contains to boxes, one for **workspaces** (in local mode) and one for **settings**.

🖥️ **Workspaces** store user inputs, parameters and results for a specific session or analysis task.

In **online mode** where the app is hosted on a remote server the workspace has a unique identifier number embedded within the URL. To share your data analysis with collaboration partners simply share the URL.

In **local mode** where the app is run locally on a PC (e.g. via Windows executable) the user can create and delete separate workspaces for different projects.

⚙️ **Settings** contain global settings which are relevant for all pages, such as the image export format.
"""
)


st.markdown("## Example pages: workflows, visualization and more")
st.markdown(
    """
This app serves both as documentation and showcase what's possible with OpenMS web apps. 
            
In general there are two options for building workflows.
            
### 1. 🚀 **TOPP Workflow Framework**
            
Use this option if you want a standardized framework for building your workflow.

- **Pre-defined user interface** all in one streamlit page with all steps on different pages:
    - **File Upload**: upload, download and delete input files
    - **Configure**: Automatically display input widgets for all paramters in TOPP tools and custom Python scripts
    - **Run**: Start and stop workflow execution, includes continous log
    - **Results**: Interactive result dashboard
- **Write less code**: everything from file upload, input widget generation and execution of tools is handled via convenient functions
- **Fast and performant workflows**: Automatic parallel execution of TOPP tools ensures great speed, comparable with workflows written in bash
- **Ideal for longer workflows**: Close the app and come back to the still running or finish workflow the next day, by entering your workspace again.
"""
)
st.page_link(
    "content/documentation.py",
    label="Check out extensive documentation on the TOPP tool framework.",
    icon="➡️",
)
st.page_link(
    "content/topp_workflow_file_upload.py", label="Play around with the example workflow.", icon="➡️"
)
st.markdown(
    """
### 2. 🐍 **Flexible, custom workflow with pyOpenMS on multiple pages**
            
Use this option if you want full control over your workflow implementation and user interface.

Uses the integrated parameter handling with global parameters across pages, including uploaded files.
            
To get an idea check out the following pages from the example worklfow (file upload first!).
"""
)
st.page_link(
    "content/file_upload.py",
    label="Upload your own mzML files or use the provided example data set.",
    icon="➡️",
)
st.page_link(
    "content/raw_data_viewer.py",
    label="Visualize mzML file content in an interactive dashboard.",
    icon="➡️",
)
st.page_link(
    "content/run_example_workflow.py",
    label="Run a small example workflow with mzML files and check out results.",
    icon="➡️",
)

st.markdown(
    """
### Other Topics
            
Includes other example pages which are independent to showcase other functionalities.
"""
)
st.page_link(
    "content/simple_workflow.py",
    label="A very simple worklfow explaining the concepts of data caching in streamlit.",
    icon="➡️",
)
st.page_link(
    "content/run_subprocess.py",
    label="How to run any command line tool as subprocess from within the OpenMS web app.",
    icon="➡️",
)
