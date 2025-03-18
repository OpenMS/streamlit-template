import streamlit as st

from src.common.common import page_setup, save_params, show_table
from src import simpleworkflow

# Page name "workflow" will show mzML file selector in sidebar
params = page_setup()

st.title("Simple Workflow")
st.markdown("Example for a simple workflow with quick execution times.")

# Define two widgets with values from paramter file
# To save them as parameters use the same key as in the json file

# We access the x-dimension via local variable
xdimension = st.number_input(
    label="x dimension",
    min_value=1,
    max_value=20,
    value=params["example-x-dimension"],
    step=1,
    key="example-x-dimension",
)

st.number_input(
    label="y dimension",
    min_value=1,
    max_value=20,
    value=params["example-y-dimension"],
    step=1,
    key="example-y-dimension",
)

# Get a dataframe with x and y dimensions via time consuming (sleep) cached function
# If the input has been given before, the function does not run again
# Input x from local variable, input y from session state via key
df = simpleworkflow.generate_random_table(
    xdimension, st.session_state["example-y-dimension"]
)

# Display dataframe via custom show_table function, which will render a download button as well
show_table(df, download_name="random-table")

# At the end of each page, always save parameters (including any changes via widgets with key)
save_params(params)
