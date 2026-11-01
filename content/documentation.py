import streamlit as st
from src.common.common import page_setup
from src.common.installers import render_installer_buttons
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
    "Developers Guide: From Notebook to Web App",
    "Developers Guide: Deployment",
    "Developers Guide: Kubernetes Deployment",
]
page = cols[0].selectbox(
    "**Content**",
    pages,
    # Keyed so another page can land the reader on a chapter: the Quickstart card
    # seeds this key before switching here. Without it this always opens on the
    # first entry, and the only way to reach a chapter was to tell the reader to
    # go find it in the menu.
    key="doc_chapter",
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
    render_installer_buttons("Download the latest version of the desktop app:")
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

This guide explains how to package OpenMS apps for Windows. The embeddable Python route is the one CI uses to build the installer; PyInstaller is an older alternative.
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

if page == pages[6]:
    with open(Path("docs", "deployment.md"), "r", encoding="utf-8") as f:
        content = f.read()
    st.markdown(content)

#############################################################################################
# Kubernetes Deployment
#############################################################################################

if page == pages[7]:
    with open(Path("docs", "kubernetes-deployment.md"), "r", encoding="utf-8") as f:
        content = f.read()
    st.markdown(content)
#############################################################################################
# From Notebook to Web App
#############################################################################################

if page == pages[5]:
    with open(Path("docs", "notebook_to_webapp.md"), "r", encoding="utf-8") as f:
        content = f.read()
    st.markdown(content)
