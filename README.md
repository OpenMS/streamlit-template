# OpenMS streamlit template [![Open Template!](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://openms-template.streamlit.app/)

This is a template app for pyOpenMS workflows in a web application.

## Template specific concepts

- **Workspaces:** Directories where all data generated and uploaded can be stored as well as a workspace specific parameter file.
Running the app locally will put the workspaces outside of the repository directory. Running online (e.g. streamlit cloud) the workspaces will be inside the repository directory.
- **Run the app local and online (default):** Launching the app with the local argument let's the user create/remove workspaces. The online version is for hosting where the user gets a workspace with a specific ID.

run locally:

`streamlit run app.py local`

- **Parameters:** Streamlit offers statefulness via the st.session_state object. However, we want to define default parameters (in `assets/default-params.json`) and store changing parameters for each workspace. Parameters are loaded via the mandatory page_setup function at the start of each page. To track a widget variable via parameters simply give them a key and add a matching entry in the default parameters file. Initialize a widget value from the params dictionary. You can access the value in two was as shown in the workflow example. Re-run the app when changing default parameters.

```python
params = page_setup()

st.number_input(label="x dimension", min_value=1, max_value=20,
value=params["example-y-dimension"], step=1, key="example-y-dimension")

save_params()
```


## Code structure

- **Pages** must be placed in the `pages` directory.
- It is recommended to use a separate file for defining functions per page in the `src` directory.
- The `src/common.py` file contains a set of useful functions for common use (e.g. rendering a table with download button).

## Layout of the template app

The main page contains explanatory text on how to use the app.

The sidebar always contains the OpenMS logo, settings panel and a workspace indicator. The main page contains a workspace selector as well.
Workflow pages contain a selector for all available mzML files, which have been uploaded.

### Pages:

- **File Upload:** Upload files (online one at a time, local multiple), load example data or copy mzML files from directory (local only). Also show all files in the workspace and options to remove them.
- **View Raw Data:** An example page to check out mzML files in detail.
- **Workflow:** Example for a workflow page which has two inputs and a time consuming cached function. The following example code shows a minimal setup for a page and two options how to access widget values for function calls.

```python
import streamlit as st

from src.common import *
from src.workflow import *

# Page name "workflow" will show mzML file selector in sidebar
params = page_setup(page="workflow")

st.title("Workflow")

# Define two widgets with values from parameter file
# To save them as parameters use the same key as in the json file

# We access the x-dimension via local variable
xdimension = st.number_input(
    label="x dimension", min_value=1, max_value=20, value=params["example-x-dimension"], step=1, key="example-x-dimension")

st.number_input(label="x dimension", min_value=1, max_value=20,
                value=params["example-y-dimension"], step=1, key="example-y-dimension")

# Get a dataframe with x and y dimensions via time consuming (sleep) cached function
# If the input has been given before, the function does not run again
# Input x from local variable, input y from session state via key
df = generate_random_table(xdimension, st.session_state["example-y-dimension"])

# Display dataframe via custom show_table function, which
show_table(df, download_name="random-table")

# At the end of each page, always save parameters (including any changes via widgets with key)
save_params(params)
```
