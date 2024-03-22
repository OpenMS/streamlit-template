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

import sys

from pathlib import Path
import streamlit as st

from src.captcha_ import captcha_control
from src.common import page_setup, save_params

params = page_setup(page="main")


def main():
    """
    Display main page content.
    """
    st.title("Template App")
    st.markdown("## A template for an OpenMS streamlit app.")
    if Path("OpenMS-App.zip").exists():
        st.markdown("## Installation")
        with open("OpenMS-App.zip", "rb") as file:
            st.download_button(
                label="Download for Windows",
                data=file,
                file_name="OpenMS-App.zip",
                mime="archive/zip",
                type="primary",
            )
    save_params(params)


# Check if the script is run in local mode (e.g., "streamlit run app.py local")
if "local" in sys.argv:
    # In local mode, run the main function without applying captcha
    main()

# If not in local mode, assume it's hosted/online mode
else:
    # WORK LIKE MULTIPAGE APP
    if "controllo" not in st.session_state or st.session_state["controllo"] is False:
        # Apply captcha control to verify the user
        captcha_control()

    else:
        # Run the main function
        main()
