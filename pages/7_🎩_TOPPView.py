import streamlit as st

from src.common import page_setup, save_params
from src.captcha_ import captcha_control


params = page_setup()

# If run in hosted mode, show captcha as long as it has not been solved
if "controllo" not in st.session_state or params["controllo"] is False:
    # Apply captcha by calling the captcha_control function
    captcha_control()

st.title("TOPPView")

# here's where the magic happens

save_params(params)
