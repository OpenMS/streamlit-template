import streamlit as st
from src.common import *

# initializing the page
page_setup()
sidebar(page="") # "page=main" to add online workspace

# main content
st.title("FLASHViewer")

st.markdown("""
#### FLASHViewer visualizes outputs from [FLASHDeconv](https://www.cell.com/cell-systems/fulltext/S2405-4712(20)30030-2).

Detailed information and the latest version of FLASHDeconv can be downloaded from the [OpenMS webpage](https://openms.de/application/flashdeconv/).
"""
)

st.info("""
**💡 How to run FLASHViewer**
1. Go to the **📁 File Upload** page through the sidebar and upload FLASHDeconv output files (\*_annotated.mzML & \*_deconv.mzML)
2. Click the **👀 Viewer** page on the sidebar to view the deconvolved results in detail.
""")