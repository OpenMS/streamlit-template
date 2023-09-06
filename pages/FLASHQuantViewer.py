import streamlit as st
from src.common import defaultPageSetup


def content():
    defaultPageSetup()
    st.title('FLASHQuant')
    st.write(st.session_state['changed_tool_name'])


if __name__ == "__main__":
    content()
