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

from src.common import page_setup

page_setup(page="main")

st.title("OpenMS Streamlit Template App")
st.markdown("""
This repository contains a template app for OpenMS workflows in a web application using the **streamlit** framework.
            
It serves as a foundation for apps ranging from simple workflows with **pyOpenMS** to complex workflows utilizing **OpenMS TOPP tools** with parallel execution.

It includes solutions for handling user data and parameters in workspaces as well as deployment with docker-compose.
""")
st.subheader("Features")
st.markdown("""
- Workspaces for user data with unique shareable IDs
- Persistent parameters and input files within a workspace
- Captcha control
- Packaged executables for Windows
- framework for workflows with OpenMS TOPP tools
- Deployment [with docker-compose](https://github.com/OpenMS/streamlit-deployment)
""")
st.subheader("Quick Start")
if Path("OpenMS-App.zip").exists():
    st.markdown("""
Download the latest version for Windows here by clicking the button below.
""")
    with open("OpenMS-App.zip", "rb") as file:
        st.download_button(
            label="Download for Windows",
            data=file,
            file_name="OpenMS-App.zip",
            mime="archive/zip",
            type="primary",
        )
    st.markdown("""
Extract the zip file and run the executable (.exe) file to launch the app. Since every dependency is compressed and packacked the app will take a while to launch (up to one minute).
""")
st.markdown("""
Check out the documentation for **users** and **developers** is included as pages indicated by the 📖 icon

Try the example pages **📁 mzML file upload**, **👀 visualization** and **example workflows**.
""")