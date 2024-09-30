# Build your own app based on this template

## App layout

*Pages* can be navigated via the *sidebar*, which also contains the OpenMS logo, settings panel and a workspace indicator.

## Key concepts

- **Workspaces**
: Directories where all data is generated and uploaded can be stored as well as a workspace specific parameter file.
- **Run the app locally and online**
: Launching the app with online mode disabled in the settings.json lets the user create/remove workspaces. In the online the user gets a workspace with a specific ID.
- **Parameters**
: Parameters (defaults in `default-parameters.json`) store changing parameters for each workspace. Parameters are loaded via the page_setup function at the start of each page. To track a widget variable via parameters simply give them a key and add a matching entry in the default parameters file. Initialize a widget value from the params dictionary.

```python
params = page_setup()

st.number_input(label="x dimension", min_value=1, max_value=20,
value=params["example-y-dimension"], step=1, key="example-y-dimension")

save_params()
```

## Code structure
- The main file `app.py` defines page layout.
- **Pages** must be placed in the `content` directory.
- It is recommended to use a separate file for defining functions per page in the `src` directory.
- The `src/common.py` file contains a set of useful functions for common use (e.g. rendering a table with download button).

## Modify the template to build your own app

1. In `src/common.py`, update the name of your app and the repository name
    ```python
    APP_NAME = "OpenMS Streamlit App"
    REPOSITORY_NAME = "streamlit-template"
    ```
2. In `clean-up-workspaces.py`, update the name of the workspaces directory to `/workspaces-<your-repository-name>`
    ```python
    workspaces_directory = Path("/workspaces-streamlit-template")
    ```
3. Update `README.md` accordingly


**Dockerfile-related**
1. Choose one of the Dockerfiles depending on your use case:
    - `Dockerfile` builds OpenMS including TOPP tools
    - `Dockerfile_simple` uses pyOpenMS only
2. Update the Dockerfile:
    - with the `GITHUB_USER` owning the Streamlit app repository
    - with the `GITHUB_REPO` name of the Streamlit app repository
    - if your main page Python file is not called `app.py`, modify the following line
        ```dockerfile
        RUN echo "mamba run --no-capture-output -n streamlit-env streamlit run app.py" >> /app/entrypoint.sh
        ```
3. Update Python package dependency files:
    - `requirements.txt` if using `Dockerfile_simple`
    - `environment.yml` if using `Dockerfile`

## How to build a workflow

### Simple workflow using pyOpenMS

Take a look at the example pages `Simple Workflow` or `Workflow with mzML files` for examples (on the *sidebar*). Put Streamlit logic inside the pages and call the functions with workflow logic from from the `src` directory (for our examples `src/simple_workflow.py` and `src/mzmlfileworkflow.py`).

### Complex workflow using TOPP tools

This template app features a module in `src/workflow` that allows for complex and long workflows to be built very efficiently. Check out the `TOPP Workflow Framework` page for more information (on the *sidebar*).
