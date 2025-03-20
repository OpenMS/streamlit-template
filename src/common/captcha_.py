from pathlib import Path
import streamlit as st
import streamlit.components.v1 as st_components
from streamlit.source_util import page_icon_and_name, calc_md5, get_pages, _on_pages_changed

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
    # Get all pages from the app's configuration
    current_pages = get_pages(main_script_path_str)

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
    _on_pages_changed.send()


def delete_page(main_script_path_str: str, page_name: str) -> None:
    """
    Delete a specific page from an app's configuration.

    Args:
        main_script_path_str (str): The name of the main page, typically the app's name.
        page_name (str): The name of the page to be deleted.

    Returns:
        None
    """
    # Get all pages
    current_pages = get_pages(main_script_path_str)

    # Iterate over all pages and delete the desired page if found
    for key, value in current_pages.items():
        if value["page_name"] == page_name:
            del current_pages[key]

    # Refresh the pages configuration
    _on_pages_changed.send()


def restore_all_pages(main_script_path_str: str) -> None:
    """
    restore all pages found in the "content" directory to an app's configuration.

    Args:
        main_script_path_str (str): The name of the main page, typically the app's name.

    Returns:
        None
    """
    # Get all pages
    pages = get_pages(main_script_path_str)

    # Obtain the path to the main script
    main_script_path = Path(main_script_path_str)

    # Define the directory where pages are stored
    pages_dir = main_script_path.parent / "content"

    # To store the pages for later, to add in ascending order
    pages_temp = []

    # Iterate over all .py files in the "content" directory
    for script_path in pages_dir.glob("*.py"):
        # append path with file name
        script_path_str = str(script_path.resolve())

        # Calculate the MD5 hash of the script path
        psh = calc_md5(script_path_str)

        # Obtain the page icon and name
        pi, pn = page_icon_and_name(script_path)

        # Extract the index from the page name
        index = int(os.path.basename(script_path.stem).split("_")[0])

        # Add the page data to the temporary list
        pages_temp.append(
            (
                index,
                {
                    "page_script_hash": psh,
                    "page_name": pn,
                    "icon": pi,
                    "script_path": script_path_str,
                },
            )
        )

    # Sort the pages_temp list by index in ascending order as defined in pages folder e-g 0_, 1_ etc
    pages_temp.sort(key=lambda x: x[0])

    # Add pages
    for index, page_data in pages_temp:
        # Add the new page configuration
        pages[page_data["page_script_hash"]] = {
            "page_script_hash": page_data["page_script_hash"],
            "page_name": page_data["page_name"],
            "icon": page_data["icon"],
            "script_path": page_data["script_path"],
        }

    # Refresh the page configuration
    _on_pages_changed.send()


def add_page(main_script_path_str: str, page_name: str) -> None:
    """
    Add a new page to an app's configuration.

    Args:
        main_script_path_str (str): The name of the main page, typically the app's name.
        page_name (str): The name of the page to be added.

    Returns:
        None
    """
    # Get all pages
    pages = get_pages(main_script_path_str)

    # Obtain the path to the main script
    main_script_path = Path(main_script_path_str)

    # Define the directory where pages are stored
    pages_dir = main_script_path.parent / "content"

    # Find the script path corresponding to the new page
    script_path = [f for f in pages_dir.glob("*.py") if f.name.find(page_name) != -1][0]
    script_path_str = str(script_path.resolve())

    # Calculate the MD5 hash of the script path
    psh = calc_md5(script_path_str)

    # Obtain the page icon and name
    pi, pn = page_icon_and_name(script_path)

    # Add the new page configuration
    pages[psh] = {
        "page_script_hash": psh,
        "page_name": pn,
        "icon": pi,
        "script_path": script_path_str,
    }

    # Refresh the page configuration
    _on_pages_changed.send()


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
