import streamlit as st 
import requests

from src.common import page_setup

page_setup()

url = "https://raw.githubusercontent.com/OpenMS/streamlit-deployment/main/README.md"

response = requests.get(url)

if response.status_code == 200:
    st.markdown(response.text)  # or process the content as needed
else:
    st.warning("Failed to get README from streamlit-deployment repository.")