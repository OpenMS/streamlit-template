import streamlit as st

from src.common import *

params = page_setup(page="main")


st.markdown(
    """# Template App

A template for an OpenMS streamlit app."""
)

save_params(params)
