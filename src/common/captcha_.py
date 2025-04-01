from pathlib import Path
import streamlit as st
import streamlit.components.v1 as st_components
from streamlit.util import calc_md5
import streamlit.runtime.scriptrunner as scriptrunner

from captcha.image import ImageCaptcha

import random
import string
import os


def delete_all_pages(main_script_path_str: str) -> None:
    """
    Delete all pages except the main page from an app's configuration.

    Args:
        main_script_path_str (str): The name of the main page, typically the app's name.

    Returns:
        None
    """
    # Get all pages from the app's configuration using st.session_state
    if "_pages" not in st.session_state:
        st.session_state._pages = {}
    current_pages = st.session_state._pages

    # Create a list to store keys pages to delete
    keys_to_delete = []

    # Iterate over all pages and add keys to delete list if the desired page is found
    for key, value in current_pages.items():
        if value["page_name"] != main_script_path_str:
            keys_to_delete.append(key)

    # Delete the keys from current pages
    for key in keys_to_delete:
        del current_pages[key]

    # Refresh the pages configuration
    scriptrunner.get_script_run_ctx().pages_manager.refresh()


def delete_page(main_script_path_str: str, page_name: str) -> None:
    """
    Delete a specific page from an app's configuration.

    Args:
        main_script_path_str (str): The name of the main page, typically the app's name.
        page_name (str): The name of the page to be deleted.

    Returns:
        None
    """
    # Get all pages from the app's configuration using st.session_state
    if "_pages" not in st.session_state:
        st.session_state._pages = {}
    current_pages = st.session_state._pages

    # Create a list to store keys pages to delete
    keys_to_delete = []

    # Iterate over all pages and add keys to delete list if the desired page is found
    for key, value in current_pages.items():
        if value["page_name"] == page_name:
            keys_to_delete.append(key)

    # Delete the keys from current pages
    for key in keys_to_delete:
        del current_pages[key]

    # Refresh the pages configuration
    scriptrunner.get_script_run_ctx().pages_manager.refresh()


def add_page(main_script_path_str: str, page_name: str, script_path_str: str) -> None:
    """
    Add a new page to an app's configuration.

    Args:
        main_script_path_str (str): The name of the main page, typically the app's name.
        page_name (str): The name of the page to be added.
        script_path_str (str): The path to the script file for the new page.

    Returns:
        None
    """
    # Get all pages from the app's configuration using st.session_state
    if "_pages" not in st.session_state:
        st.session_state._pages = {}
    pages = st.session_state._pages

    # Calculate the page script hash
    psh = calc_md5(script_path_str)

    # Add the new page to the pages dictionary
    pages[psh] = {
        "page_name": page_name,
        "script_path": script_path_str,
        "icon": "",
    }

    # Refresh the pages configuration
    scriptrunner.get_script_run_ctx().pages_manager.refresh()


def update_page(main_script_path_str: str, page_name: str, script_path_str: str) -> None:
    """
    Update an existing page in an app's configuration.

    Args:
        main_script_path_str (str): The name of the main page, typically the app's name.
        page_name (str): The name of the page to be updated.
        script_path_str (str): The path to the script file for the updated page.

    Returns:
        None
    """
    # Get all pages from the app's configuration using st.session_state
    if "_pages" not in st.session_state:
        st.session_state._pages = {}
    pages = st.session_state._pages

    # Calculate the page script hash
    psh = calc_md5(script_path_str)

    # Update the page in the pages dictionary
    pages[psh] = {
        "page_name": page_name,
        "script_path": script_path_str,
        "icon": "",
    }

    # Refresh the pages configuration
    scriptrunner.get_script_run_ctx().pages_manager.refresh()


length_captcha = 5
width = 400
height = 180


# define the function for the captcha control
def captcha_control():
    """
    Control and verification of a CAPTCHA to ensure the user is not a robot.

    This function implements CAPTCHA control to verify that the user is not a robot.
    It displays a CAPTCHA image and prompts the user to enter the corresponding text.
    If the entered text matches the CAPTCHA, the control is set to True; otherwise, it remains False.

    If the CAPTCHA is incorrect, it is regenerated and the control state is set to False.
    This function also handles user interactions and reruns the Streamlit app accordingly.

    The CAPTCHA text is generated as a session state and should not change during refreshes.

    Returns:
        None
    """
    # control if the captcha is correct
    if "controllo" not in st.session_state or st.session_state["controllo"] == False:
        
        # Check if consent for tracking was given
        ga = st.session_state.settings['analytics']['google-analytics']['enabled']
        pp = st.session_state.settings['analytics']['piwik-pro']['enabled']
        if (ga or pp) and (st.session_state.tracking_consent is None):
            consent_component = st_components.declare_component("gdpr_consent", path=Path("gdpr_consent"))
            with st.spinner():
                # Ask for consent
                st.session_state.tracking_consent = consent_component(
                    google_analytics=ga, piwik_pro=pp
                )
                if st.session_state.tracking_consent is None:
                    # No response by user yet
                    st.stop()
                else:
                    # Consent choice was made
                    st.rerun()

        st.title("Make sure you are not a robot🤖")

        # define the session state for control if the captcha is correct
        st.session_state["controllo"] = False

        # define the session state for the captcha text because it doesn't change during refreshes
        if "Captcha" not in st.session_state:
            st.session_state["Captcha"] = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=length_captcha)
            ).replace("0", "A").replace("O", "B")

        col1, _ = st.columns(2)
        with col1.form("captcha-form"):
            # setup the captcha widget
            st.info(
                "Please enter the captcha as text. Note: If your captcha is not accepted, you might need to disable your ad blocker."
            )
            image = ImageCaptcha(width=width, height=height)
            data = image.generate(st.session_state["Captcha"])
            st.image(data)
            c1, c2 = st.columns([70, 30])
            capta2_text = st.empty()
            capta2_text = c1.text_input("Enter captcha text", max_chars=5)
            c2.markdown("##")
            if c2.form_submit_button("Verify the code", type="primary"):
                capta2_text = capta2_text.replace(" ", "")
                # if the captcha is correct, the controllo session state is set to True
                if st.session_state["Captcha"].lower() == capta2_text.lower().strip():
                    del st.session_state["Captcha"]
                    col1.empty()
                    st.session_state["controllo"] = True
                    st.rerun()
                else:
                    # if the captcha is wrong, the controllo session state is set to False and the captcha is regenerated
                    st.error("🚨 Captch is wrong")
                    del st.session_state["Captcha"]
                    del st.session_state["controllo"]
                    st.rerun()
            else:
                # wait for the button click
                st.stop()
