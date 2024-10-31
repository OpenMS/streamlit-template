import streamlit as st
from src.common.common import page_setup
from pathlib import Path
from docs.toppframework import content as topp_framework_content

page_setup()


st.title("Documentation")

cols = st.columns(2)

pages = [
    "User Guide",
    "Installation",
    "Developers Guide: How to build app based on this template",
    "Developers Guide: TOPP Workflow Framework",
    "Developer Guide: Windows Executables",
    "Developers Guide: Deployment",
]
page = cols[0].selectbox(
    "**Content**",
    pages,
)

#############################################################################################
# User Guide
#############################################################################################

if page == pages[0]:
    with open(Path("docs", "user_guide.md"), "r", encoding="utf-8") as f:
        content = f.read()
    st.markdown(content) 

#############################################################################################
# Installation
#############################################################################################

if page == pages[1]:
    if Path("OpenMS-App.zip").exists():
        st.markdown(
            """
Download the latest version for **Windows** here clicking the button below.
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
    with open(Path("docs", "installation.md"), "r", encoding="utf-8") as f:
        content = f.read()
    st.markdown(content) 

#############################################################################################
# Developer Overview, how to build app based on Template
#############################################################################################

if page == pages[2]:
    with open(Path("docs", "build_app.md"), "r", encoding="utf-8") as f:
        content = f.read()
    st.markdown(content) 

#############################################################################################
# TOPP Workflow Framework
#############################################################################################

if page == pages[3]:
    topp_framework_content()

#############################################################################################
# Windows Executables
#############################################################################################

if page == pages[4]:
    st.markdown(
        """
## 💻  How to package everything for Windows executables

This guide explains how to package OpenMS apps into Windows executables using two different methods:
"""
    )

    tabs = ["**embeddable Python**", "**PyInstaller**"]
    tabs = st.tabs(tabs)

    # window executable with embeddable python
    with tabs[0]:
        with open(Path("docs", "win_exe_with_embed_py.md"), "r", encoding="utf-8") as f:
            content = f.read()
        st.markdown(content) 

    # window executable with pyinstaller
    with tabs[1]:
        with open(Path("docs", "win_exe_with_pyinstaller.md"), "r", encoding="utf-8") as f:
            content = f.read()
        st.markdown(content) 

#############################################################################################
# Deployment
#############################################################################################

if page == pages[5]:
    with open(Path("docs", "deployment.md"), "r", encoding="utf-8") as f:
        content = f.read()
    st.markdown(content) 