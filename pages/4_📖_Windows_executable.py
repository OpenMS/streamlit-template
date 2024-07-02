import streamlit as st
import requests

import streamlit as st

# Define CSS styles
css = '''
<style>
    /* Add space between tabs */
    .stTabs [data-baseweb="tab-list"] button {
        margin-right: 20px;
        border-radius: 5px;
        transition: background-color 0.3s ease, color 0.3s ease; /* Add smooth transition */
    }
    /* Style active tab */
    .stTabs [data-baseweb="tab-list"] button:focus {
        background-color: #f0f0f0; /* Change background color of active tab */
        color: #333333; /* Change text color of active tab */
        border-width: 3px; /* Increase thickness of blue line */
    }
    /* Style tab text */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 2rem;
        font-weight: bold;
    }
    /* Add hover effect */
    .stTabs [data-baseweb="tab-list"] button:hover {
        background-color: #f8f8f8; /* Change background color on hover */
    }
</style>
'''


st.markdown(css, unsafe_allow_html=True)

st.markdown("""
# 💻  How to package everything for Windows executables

This guide explains how to package OpenMS apps into Windows executables using two different methods:
""")

def fetch_markdown_content(url):
    response = requests.get(url)
    if response.status_code == 200:
        # Remove the first line from the content
        content_lines = response.text.split("\n")
        markdown_content = "\n".join(content_lines[1:])
        return markdown_content
    else:
        return None

tabs = ["embeddable Python", "PyInstaller"]
tabs = st.tabs(tabs)

# window executable with embeddable python
with tabs[0]: 
    markdown_url = "https://raw.githubusercontent.com/OpenMS/streamlit-template/main/win_exe_with_embed_py.md"

    markdown_content = fetch_markdown_content(markdown_url)

    if markdown_content:
        st.markdown(markdown_content, unsafe_allow_html=True)
    else:
        st.error("Failed to fetch Markdown content from the specified URL.", markdown_url)

# window executable with pyinstaller
with tabs[1]: 
    # URL of the Markdown document
    markdown_url = "https://raw.githubusercontent.com/OpenMS/streamlit-template/main/win_exe_with_pyinstaller.md"

    markdown_content = fetch_markdown_content(markdown_url)

    if markdown_content:
        st.markdown(markdown_content, unsafe_allow_html=True)
    else:
        st.error("Failed to fetch Markdown content from the specified URL. ", markdown_url)


