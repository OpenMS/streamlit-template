import streamlit as st
from src.common import defaultPageSetup

def readingInputFiles():
    st.subheader('File uploads')

    # input file form
    # with st.form
    return

def running_fd():
    return

def content():
    defaultPageSetup("Running FLASHDeconv")

    # handling input
    readingInputFiles()

    # setting parameter

    # running button
    running_fd()

    # log?



if __name__ == "__main__":
    # try:
    content()
    # except:
    #     st.warning(ERRORS["visualization"])