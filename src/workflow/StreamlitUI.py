import streamlit as st
import pyopenms as poms
from pathlib import Path
import shutil
import subprocess
from typing import Any, Union, List
import json
import sys
import importlib.util
import time
from io import BytesIO
import zipfile

class StreamlitUI:
    """
    Provides an interface for Streamlit applications to handle file uploads,
    input selection, and parameter management for analysis workflows. It includes
    methods for uploading files, selecting input files from available ones, and
    generating various input widgets dynamically based on the specified parameters.
    """

    # Methods for Streamlit UI components
    def __init__(self, workflow_dir, logger, executor, paramter_manager):
        self.workflow_dir = workflow_dir
        self.logger = logger
        self.executor = executor
        self.parameter_manager = paramter_manager
        self.params = self.parameter_manager.get_parameters_from_json()

    def upload_widget(
        self,
        key: str,
        file_type: str,
        name: str = "",
        fallback: Union[List, str] = None,
    ) -> None:
        """
        Handles file uploads through the Streamlit interface, supporting both direct
        uploads and local directory copying for specified file types. It allows for
        specifying fallback files to ensure essential files are available.

        Args:
            key (str): A unique identifier for the upload component.
            file_type (str): Expected file type for the uploaded files.
            name (str, optional): Display name for the upload component. Defaults to the key if not provided.
            fallback (Union[List, str], optional): Default files to use if no files are uploaded.
        """
        # streamlit uploader can't handle file types with upper and lower case letters
        files_dir = Path(self.workflow_dir, "input-files", key)

        if not name:
            name = key.replace("-", " ")

        c1, c2 = st.columns(2)
        c1.markdown("**Upload file(s)**")
        with c1.form(f"{key}-upload", clear_on_submit=True):
            if any(c.isupper() for c in file_type) and (c.islower() for c in file_type):
                file_type_for_uploader = None
            else:
                file_type_for_uploader = [file_type]
            files = st.file_uploader(
                f"{name}",
                accept_multiple_files=(st.session_state.location == "local"),
                type=file_type_for_uploader,
                label_visibility="collapsed",
            )
            if st.form_submit_button(
                f"Add **{name}**", use_container_width=True, type="primary"
            ):
                if files:
                    files_dir.mkdir(parents=True, exist_ok=True)
                    # in case of online mode a single file is returned -> put in list
                    if not isinstance(files, list):
                        files = [files]
                    for f in files:
                        if f.name not in [
                            f.name for f in files_dir.iterdir()
                        ] and f.name.endswith(file_type):
                            with open(Path(files_dir, f.name), "wb") as fh:
                                fh.write(f.getbuffer())
                    st.success("Successfully added uploaded files!")
                else:
                    st.error("Nothing to add, please upload file.")

        # Local file upload option: via directory path
        if st.session_state.location == "local":
            c2.markdown("**OR copy files from local folder**")
            with c2.form(f"{key}-local-file-upload"):
                local_dir = st.text_input(f"path to folder with **{name}** files")
                if st.form_submit_button(
                    f"Copy **{name}** files from local folder", use_container_width=True
                ):
                    # raw string for file paths
                    if not any(Path(local_dir).glob(f"*.{file_type}")):
                        st.warning(
                            f"No files with type **{file_type}** found in specified folder."
                        )
                    else:
                        files_dir.mkdir(parents=True, exist_ok=True)
                        # Copy all mzML files to workspace mzML directory, add to selected files
                        files = list(Path(local_dir).glob("*.mzML"))
                        my_bar = st.progress(0)
                        for i, f in enumerate(files):
                            my_bar.progress((i + 1) / len(files))
                            shutil.copy(f, Path(files_dir, f.name))
                        my_bar.empty()
                        st.success("Successfully copied files!")

        if fallback:
            files_dir.mkdir(parents=True, exist_ok=True)
            if isinstance(fallback, str):
                fallback = [fallback]
            for f in fallback:
                if not Path(files_dir, f).exists():
                    shutil.copy(f, Path(files_dir, Path(f).name))
                    st.info(f"Adding default file: **{f}**")
            current_files = [
                f.name
                for f in files_dir.iterdir()
                if f.name not in [Path(f).name for f in fallback]
            ]
        else:
            if files_dir.exists():
                current_files = [f.name for f in files_dir.iterdir()]
            else:
                current_files = []

        if files_dir.exists() and not any(files_dir.iterdir()):
            shutil.rmtree(files_dir)

        c1, c2 = st.columns(2)
        if current_files:
            c1.info(f"Current **{name}** files:\n\n" + "\n\n".join(current_files))
            if c2.button(
                f"🗑️ Remove all **{name}** files.",
                use_container_width=True,
                key=f"remove-files-{key}",
            ):
                shutil.rmtree(files_dir)
                del self.params[key]
                with open(self.parameter_manager.params_file, "w", encoding="utf-8") as f:
                    json.dump(self.params, f, indent=4)
                st.rerun()
        elif not fallback:
            st.warning(f"No **{name}** files!")

    def select_input_file(
        self,
        key: str,
        name: str = "",
        multiple: bool = False,
        display_file_path: bool = False,
    ) -> None:
        """
        Presents a widget for selecting input files from those that have been uploaded.
        Allows for single or multiple selections.

        Args:
            key (str): A unique identifier related to the specific input files.
            name (str, optional): The display name for the selection widget. Defaults to the key if not provided.
            multiple (bool, optional): If True, allows multiple files to be selected.
            display_file_path (bool, optional): If True, displays the full file path in the selection widget.
        """
        if not name:
            name = f"**{key}**"
        path = Path(self.workflow_dir, "input-files", key)
        if not path.exists():
            st.warning(f"No **{name}** files!")
            return
        options = [str(f) for f in path.iterdir()]
        if key in self.params.keys():
            self.params[key] = [f for f in self.params[key] if f in options]

        widget_type = "multiselect" if multiple else "selectbox"
        self.input_widget(
            key,
            name=name,
            widget_type=widget_type,
            options=options,
            display_file_path=display_file_path,
        )

    def input_widget(
        self,
        key: str,
        default: Any = None,
        name: str = "input widget",
        help: str = None,
        widget_type: str = "auto",  # text, textarea, number, selectbox, slider, checkbox, multiselect
        options: List[str] = None,
        min_value: Union[int, float] = None,
        max_value: Union[int, float] = None,
        step_size: Union[int, float] = 1,
        display_file_path: bool = False,
    ) -> None:
        """
        Creates and displays a Streamlit widget for user input based on specified
        parameters. Supports a variety of widget types including text input, number
        input, select boxes, and more. Default values will be read in from parameters
        if they exist. The key is modified to be recognized by the ParameterManager class
        as a custom parameter (distinct from TOPP tool parameters).

        Args:
            key (str): Unique identifier for the widget.
            default (Any, optional): Default value for the widget.
            name (str, optional): Display name of the widget.
            help (str, optional): Help text to display alongside the widget.
            widget_type (str, optional): Type of widget to create ('text', 'textarea',
                                         'number', 'selectbox', 'slider', 'checkbox',
                                         'multiselect', 'password', or 'auto').
            options (List[str], optional): Options for select/multiselect widgets.
            min_value (Union[int, float], optional): Minimum value for number/slider widgets.
            max_value (Union[int, float], optional): Maximum value for number/slider widgets.
            step_size (Union[int, float], optional): Step size for number/slider widgets.
            display_file_path (bool, optional): Whether to display the full file path for file options.
        """

        def format_files(input: Any) -> List[str]:
            if not display_file_path and Path(input).exists():
                return Path(input).name
            else:
                return input

        if key in self.params.keys():
            value = self.params[key]
        else:
            value = default
            # catch case where options are given but default is None
            if options is not None and value is None:
                if widget_type == "multiselect":
                    value = []
                elif widget_type == "selectbox":
                    value = options[0]

        key = f"{self.parameter_manager.param_prefix}{key}"

        if widget_type == "text":
            st.text_input(name, value=value, key=key, help=help)

        elif widget_type == "textarea":
            st.text_area(name, value=value, key=key, help=help)

        elif widget_type == "number":
            number_type = float if isinstance(value, float) else int
            step_size = number_type(step_size)
            if min_value is not None:
                min_value = number_type(min_value)
            if max_value is not None:
                max_value = number_type(max_value)
            help = str(help)
            st.number_input(
                name,
                min_value=min_value,
                max_value=max_value,
                value=value,
                step=step_size,
                format=None,
                key=key,
                help=help,
            )

        elif widget_type == "checkbox":
            st.checkbox(name, value=value, key=key, help=help)

        elif widget_type == "selectbox":
            if options is not None:
                st.selectbox(
                    name,
                    options=options,
                    index=options.index(value) if value in options else 0,
                    key=key,
                    format_func=format_files,
                    help=help,
                )
            else:
                st.warning(f"Select widget '{name}' requires options parameter")

        elif widget_type == "multiselect":
            if options is not None:
                st.multiselect(
                    name,
                    options=options,
                    default=value,
                    key=key,
                    format_func=format_files,
                    help=help,
                )
            else:
                st.warning(f"Select widget '{name}' requires options parameter")

        elif widget_type == "slider":
            if min_value is not None and max_value is not None:
                slider_type = float if isinstance(value, float) else int
                step_size = slider_type(step_size)
                if min_value is not None:
                    min_value = slider_type(min_value)
                if max_value is not None:
                    max_value = slider_type(max_value)
                st.slider(
                    name,
                    min_value=min_value,
                    max_value=max_value,
                    value=value,
                    step=step_size,
                    key=key,
                    format=None,
                    help=help,
                )
            else:
                st.warning(
                    f"Slider widget '{name}' requires min_value and max_value parameters"
                )

        elif widget_type == "password":
            st.text_input(name, value=value, type="password", key=key, help=help)

        elif widget_type == "auto":
            # Auto-determine widget type based on value
            if isinstance(value, bool):
                st.checkbox(name, value=value, key=key, help=help)
            elif isinstance(value, (int, float)):
                self.input_widget(
                    key,
                    value,
                    widget_type="number",
                    name=name,
                    min_value=min_value,
                    max_value=max_value,
                    step_size=step_size,
                    help=help,
                )
            elif (isinstance(value, str) or value == None) and options is not None:
                self.input_widget(
                    key,
                    value,
                    widget_type="selectbox",
                    name=name,
                    options=options,
                    help=help,
                )
            elif isinstance(value, list) and options is not None:
                self.input_widget(
                    key,
                    value,
                    widget_type="multiselect",
                    name=name,
                    options=options,
                    help=help,
                )
            elif isinstance(value, bool):
                self.input_widget(key, value, widget_type="checkbox", name=name, help=help)
            else:
                self.input_widget(key, value, widget_type="text", name=name, help=help)

        else:
            st.error(f"Unsupported widget type '{widget_type}'")

    def input_TOPP(
        self,
        topp_tool_name: str,
        num_cols: int = 3,
        exclude_parameters: List[str] = [],
    ) -> None:
        """
        Generates input widgets for TOPP tool parameters dynamically based on the tool's
        .ini file. Supports excluding specific parameters and adjusting the layout.
        File input and output parameters are excluded.

        Args:
            topp_tool_name (str): The name of the TOPP tool for which to generate inputs.
            num_cols (int, optional): Number of columns to use for the layout. Defaults to 3.
            exclude_parameters (List[str], optional): List of parameter names to exclude from the widget.
        """
        # write defaults ini files
        ini_file_path = Path(self.parameter_manager.ini_dir, f"{topp_tool_name}.ini")
        if not ini_file_path.exists():
            subprocess.call([topp_tool_name, "-write_ini", str(ini_file_path)])
        # read into Param object
        param = poms.Param()
        poms.ParamXMLFile().load(str(ini_file_path), param)

        excluded_keys = [
            "log",
            "debug",
            "threads",
            "no_progress",
            "force",
            "version",
            "test",
        ] + exclude_parameters

        param_dicts = []
        for key in param.keys():
            # Determine if the parameter should be included based on the conditions
            if (
                b"input file" in param.getTags(key)
                or b"output file" in param.getTags(key)
            ) or (key.decode().split(":")[-1] in excluded_keys):
                continue
            entry = param.getEntry(key)
            param_dict = {
                "name": entry.name.decode(),
                "key": key,
                "value": entry.value,
                "valid_strings": [v.decode() for v in entry.valid_strings],
                "description": entry.description.decode(),
                "advanced": (b"advanced" in param.getTags(key)),
            }
            param_dicts.append(param_dict)

        # Update parameter values from the JSON parameters file
        json_params = self.params
        if topp_tool_name in json_params:
            for p in param_dicts:
                name = p["key"].decode().split(":1:")[1]
                if name in json_params[topp_tool_name]:
                    p["value"] = json_params[topp_tool_name][name]

        # input widgets in n number of columns
        cols = st.columns(num_cols)
        i = 0

        # show input widgets
        for p in param_dicts:

            # skip avdanced parameters if not selected
            if not st.session_state["advanced"] and p["advanced"]:
                continue

            key = f"{self.parameter_manager.topp_param_prefix}{p['key'].decode()}"

            try:
                # bools
                if p["value"] == "true" or p["value"] == "false":
                    cols[i].markdown("##")
                    cols[i].checkbox(
                        p["name"],
                        value=(p["value"] == "true"),
                        help=p["description"],
                        key=key,
                    )

                # string options
                elif isinstance(p["value"], str) and p["valid_strings"]:
                    cols[i].selectbox(
                        p["name"],
                        options=p["valid_strings"],
                        index=p["valid_strings"].index(p["value"]),
                        help=p["description"],
                        key=key,
                    )

                # strings
                elif isinstance(p["value"], str):
                    cols[i].text_input(
                        p["name"], value=p["value"], help=p["description"], key=key
                    )

                # ints
                elif isinstance(p["value"], int):
                    cols[i].number_input(
                        p["name"], value=int(p["value"]), help=p["description"], key=key
                    )

                # floats
                elif isinstance(p["value"], float):
                    cols[i].number_input(
                        p["name"],
                        value=float(p["value"]),
                        step=1.0,
                        help=p["description"],
                        key=key,
                    )

                # lists
                elif isinstance(p["value"], list):
                    p["value"] = [
                        v.decode() if isinstance(v, bytes) else v for v in p["value"]
                    ]
                    cols[i].text_area(
                        p["name"],
                        value="\n".join(p["value"]),
                        help=p["description"],
                        key=key,
                    )

                # increment number of columns, create new cols object if end of line is reached
                i += 1
                if i == num_cols:
                    i = 0
                    cols = st.columns(num_cols)
            except:
                cols[i].error(f"Error in parameter **{p['name']}**.")

    def input_python(
        self,
        script_file: str,
        num_cols: int = 3,
    ) -> None:
        """
    Dynamically generates and displays input widgets based on the DEFAULTS 
    dictionary defined in a specified Python script file.

    For each entry in the DEFAULTS dictionary, an input widget is displayed, 
    allowing the user to specify values for the parameters defined in the 
    script. The widgets are arranged in a grid with a specified number of 
    columns. Parameters can be marked as hidden or advanced within the DEFAULTS 
    dictionary; hidden parameters are not displayed, and advanced parameters 
    are displayed only if the user has selected to view advanced options.

    Args:
    script_file (str): The file name or path to the Python script containing 
                       the DEFAULTS dictionary. If the path is omitted, the method searches in 
                       src/python-tools/'.
    num_cols (int, optional): The number of columns to use for displaying input widgets. Defaults to 3.
    """

        # Check if script file exists (can be specified without path and extension)
        # default location: src/python-tools/script_file
        if not script_file.endswith(".py"):
            script_file += ".py"
        path = Path(script_file)
        if not path.exists():
            path = Path("src", "python-tools", script_file)
            if not path.exists():
                st.error("Script file not found.")
        # load DEFAULTS from file
        if path.parent not in sys.path:
            sys.path.append(str(path.parent))
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        defaults = getattr(module, "DEFAULTS", None)
        if defaults is None:
            st.error("No DEFAULTS found in script file.")
            return
        elif isinstance(defaults, list):
            # display input widget for every entry in defaults
            # input widgets in n number of columns
            cols = st.columns(num_cols)
            i = 0
            for entry in defaults:
                key = f"{path.name}:{entry['key']}" if "key" in entry else None
                if key is None:
                    st.error("Key not specified for parameter.")
                    continue
                value = entry["value"] if "value" in entry else None
                if value is None:
                    st.error("Value not specified for parameter.")
                    continue
                hide = entry["hide"] if "hide" in entry else False
                # no need to display input and output files widget or hidden parameters
                if hide:
                    continue
                advanced = entry["advanced"] if "advanced" in entry else False
                # skip avdanced parameters if not selected
                if not st.session_state["advanced"] and advanced:
                    continue
                name = entry["name"] if "name" in entry else key
                help = entry["help"] if "help" in entry else ""
                min_value = entry["min"] if "min" in entry else None
                max_value = entry["max"] if "max" in entry else None
                step_size = entry["step_size"] if "step_size" in entry else 1
                widget_type = entry["widget_type"] if "widget_type" in entry else "auto"
                options = entry["options"] if "options" in entry else None

                with cols[i]:
                    if isinstance(value, bool):
                        st.markdown("#")
                    self.input_widget(
                        key=key,
                        default=value,
                        name=name,
                        help=help,
                        widget_type=widget_type,
                        options=options,
                        min_value=min_value,
                        max_value=max_value,
                        step_size=step_size,
                    )
                # increment number of columns, create new cols object if end of line is reached
                i += 1
                if i == num_cols:
                    i = 0
                    cols = st.columns(num_cols)

    def zip_and_download_files(self, directory: str):
        """
        Creates a zip archive of all files within a specified directory,
        including files in subdirectories, and offers it as a download
        button in a Streamlit application.

        Args:
            directory (str): The directory whose files are to be zipped.
        """
       # Ensure directory is a Path object and check if directory is empty
        directory = Path(directory)
        if not any(directory.iterdir()):
            st.error("No files to compress.")
            return

        bytes_io = BytesIO()
        files = list(directory.rglob("*"))  # Use list comprehension to find all files

        # Check if there are any files to zip
        if not files:
            st.error("Directory is empty or contains no files.")
            return

        n_files = len(files)

        # Initialize Streamlit progress bar
        my_bar = st.progress(0)

        with zipfile.ZipFile(bytes_io, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for i, file_path in enumerate(files):
                if file_path.is_file():  # Ensure we're only adding files, not directories
                    # Preserve directory structure relative to the original directory
                    zip_file.write(file_path, file_path.relative_to(directory.parent))
                    my_bar.progress((i + 1) / n_files)  # Update progress bar

        my_bar.empty()  # Clear progress bar after operation is complete
        bytes_io.seek(0)  # Reset buffer pointer to the beginning

        # Display a download button for the zip file in Streamlit
        st.columns(2)[1].download_button(
            label="⬇️ Download Now",
            data=bytes_io,
            file_name="input-files.zip",
            mime="application/zip",
            use_container_width=True
        )
        
        
    def file_upload_section(self, custom_upload_function) -> None:
        custom_upload_function()
        if st.button("⬇️ Download all uploaded files", use_container_width=True):
            self.ui.zip_and_download_files(Path(self.workflow_dir, "input-files"))

    def parameter_section(self, custom_paramter_function) -> None:
        st.toggle("Show advanced parameters", value=False, key="advanced")

        form = st.form(
            key=f"{self.workflow_dir.stem}-input-form",
            clear_on_submit=True,
        )

        with form:
            cols = st.columns(2)

            cols[0].form_submit_button(
                label="Save parameters",
                on_click=self.parameter_manager.save_parameters,
                type="primary",
                use_container_width=True,
            )

            if cols[1].form_submit_button(
                label="Load default parameters", use_container_width=True
            ):
                self.parameter_manager.reset_to_default_parameters()

            custom_paramter_function()
        # Save parameters
        self.parameter_manager.save_parameters()

    def execution_section(self, start_workflow_function) -> None:
        if self.executor.pid_dir.exists():
            if st.button("Stop Workflow", type="primary", use_container_width=True):
                self.executor.stop()
                st.rerun()
        else:
            st.button(
                "Start Workflow",
                type="primary",
                use_container_width=True,
                on_click=start_workflow_function,
            )

        if self.logger.log_file.exists():
            if self.executor.pid_dir.exists():
                with st.spinner("**Workflow running...**"):
                    with open(self.logger.log_file, "r", encoding="utf-8") as f:
                        st.code(f.read(), language="neon", line_numbers=True)
                    time.sleep(2)
                st.rerun()
            else:
                st.markdown("**Workflow log file**")
                with open(self.logger.log_file, "r", encoding="utf-8") as f:
                    st.code(f.read(), language="neon", line_numbers=True)

    def results_section(self, custom_results_function) -> None:
        custom_results_function()
