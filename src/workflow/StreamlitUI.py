import streamlit as st
import pyopenms as poms
from pathlib import Path
import shutil
import subprocess
from typing import Any, Union, List, Literal, Callable
import json
import os
import sys
import importlib.util
import time
from io import BytesIO
import zipfile
from datetime import datetime


from src.common.common import (
    OS_PLATFORM,
    TK_AVAILABLE,
    tk_directory_dialog,
    tk_file_dialog,
)


class StreamlitUI:
    """
    Provides an interface for Streamlit applications to handle file uploads,
    input selection, and parameter management for analysis workflows. It includes
    methods for uploading files, selecting input files from available ones, and
    generating various input widgets dynamically based on the specified parameters.
    """

    # Methods for Streamlit UI components
    def __init__(self, workflow_dir, logger, executor, parameter_manager):
        self.workflow_dir = workflow_dir
        self.logger = logger
        self.executor = executor
        self.parameter_manager = parameter_manager
        self.params = self.parameter_manager.get_parameters_from_json()

    @st.fragment
    def upload_widget(
        self,
        key: str,
        file_types: Union[str, List[str]],
        name: str = "",
        fallback: Union[List, str] = None,
    ) -> None:
        """
        Handles file uploads through the Streamlit interface, supporting both direct
        uploads and local directory copying for specified file types. It allows for
        specifying fallback files to ensure essential files are available.

        Args:
            key (str): A unique identifier for the upload component.
            file_types (Union[str, List[str]]): Expected file type(s) for the uploaded files.
            name (str, optional): Display name for the upload component. Defaults to the key if not provided.
            fallback (Union[List, str], optional): Default files to use if no files are uploaded.
        """
        files_dir = Path(self.workflow_dir, "input-files", key)

        # create the files dir
        files_dir.mkdir(exist_ok=True, parents=True)

        if fallback is not None:
            # check if only fallback files are in files_dir, if yes, reset the directory before adding new files
            if [Path(f).name for f in Path(files_dir).iterdir()] == [
                Path(f).name for f in fallback
            ]:
                shutil.rmtree(files_dir)
                files_dir.mkdir()

        if not name:
            name = key.replace("-", " ")

        c1, c2 = st.columns(2)
        c1.markdown("**Upload file(s)**")

        if st.session_state.location == "local":
            c2_text, c2_checkbox = c2.columns([1.5, 1], gap="large")
            c2_text.markdown("**OR add files from local folder**")
            use_copy = c2_checkbox.checkbox(
                "Make a copy of files",
                key=f"{key}-copy_files",
                value=True,
                help="Create a copy of files in workspace.",
            )
        else:
            use_copy = True

        # Convert file_types to a list if it's a string
        if isinstance(file_types, str):
            file_types = [file_types]

        if use_copy:
            with c1.form(f"{key}-upload", clear_on_submit=True):
                # Streamlit file uploader accepts file types as a list or None
                file_type_for_uploader = file_types if file_types else None

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
                        # in case of online mode a single file is returned -> put in list
                        if not isinstance(files, list):
                            files = [files]
                        for f in files:
                            # Check if file type is in the list of accepted file types
                            if f.name not in [
                                f.name for f in files_dir.iterdir()
                            ] and any(f.name.endswith(ft) for ft in file_types):
                                with open(Path(files_dir, f.name), "wb") as fh:
                                    fh.write(f.getbuffer())
                        st.success("Successfully added uploaded files!")
                    else:
                        st.error("Nothing to add, please upload file.")
        else:
            # Create a temporary file to store the path to the local directories
            external_files = Path(files_dir, "external_files.txt")
            # Check if the file exists, if not create it
            if not external_files.exists():
                external_files.touch()
            c1.write("\n")
            with c1.container(border=True):
                dialog_button = st.button(
                    rf"$\textsf{{\Large 📁 Add }} \textsf{{ \Large \textbf{{{name}}} }}$",
                    type="primary",
                    use_container_width=True,
                    key="local_browse_single",
                    help="Browse for your local MS data files.",
                    disabled=not TK_AVAILABLE,
                )

                # Tk file dialog requires file types to be a list of tuples
                if isinstance(file_types, str):
                    tk_file_types = [(f"{file_types}", f"*.{file_types}")]
                elif isinstance(file_types, list):
                    tk_file_types = [(f"{ft}", f"*.{ft}") for ft in file_types]
                else:
                    raise ValueError("'file_types' must be either of type str or list")

                if dialog_button:
                    local_files = tk_file_dialog(
                        "Select your local MS data files",
                        tk_file_types,
                        st.session_state["previous_dir"],
                    )
                    if local_files:
                        my_bar = st.progress(0)
                        for i, f in enumerate(local_files):
                            with open(external_files, "a") as f_handle:
                                f_handle.write(f"{f}\n")
                        my_bar.empty()
                        st.success("Successfully added files!")

                        st.session_state["previous_dir"] = Path(local_files[0]).parent

        # Local file upload option: via directory path
        if st.session_state.location == "local":
            # c2_text, c2_checkbox = c2.columns([1.5, 1], gap="large")
            # c2_text.markdown("**OR add files from local folder**")
            # use_copy = c2_checkbox.checkbox("Make a copy of files", key=f"{key}-copy_files", value=True, help="Create a copy of files in workspace.")
            with c2.container(border=True):
                st_cols = st.columns([0.05, 0.55], gap="small")
                with st_cols[0]:
                    st.write("\n")
                    st.write("\n")
                    dialog_button = st.button(
                        "📁",
                        key=f"local_browse_{key}",
                        help="Browse for your local directory with MS data.",
                        disabled=not TK_AVAILABLE,
                    )
                    if dialog_button:
                        st.session_state["local_dir"] = tk_directory_dialog(
                            "Select directory with your MS data",
                            st.session_state["previous_dir"],
                        )
                        st.session_state["previous_dir"] = st.session_state["local_dir"]

                with st_cols[1]:
                    local_dir = st.text_input(
                        f"path to folder with **{name}** files",
                        key=f"path_to_folder_{key}",
                        value=st.session_state["local_dir"],
                    )

                if c2.button(
                    f"Add **{name}** files from local folder",
                    use_container_width=True,
                    key=f"add_files_from_local_{key}",
                    help="Add files from local directory.",
                ):
                    files = []
                    local_dir = Path(
                        local_dir
                    ).expanduser()  # Expand ~ to full home directory path

                    for ft in file_types:
                        # Search for both files and directories with the specified extension
                        for path in local_dir.iterdir():
                            if path.is_file() and path.name.endswith(f".{ft}"):
                                files.append(path)
                            elif path.is_dir() and path.name.endswith(f".{ft}"):
                                files.append(path)

                    if not files:
                        st.warning(
                            f"No files with type **{', '.join(file_types)}** found in specified folder."
                        )
                    else:
                        my_bar = st.progress(0)
                        for i, f in enumerate(files):
                            my_bar.progress((i + 1) / len(files))
                            if use_copy:
                                if os.path.isfile(f):
                                    shutil.copy(f, Path(files_dir, f.name))
                                elif os.path.isdir(f):
                                    shutil.copytree(
                                        f, Path(files_dir, f.name), dirs_exist_ok=True
                                    )
                            else:
                                # Write the path to the local directories to the file
                                with open(external_files, "a") as f_handle:
                                    f_handle.write(f"{f}\n")
                        my_bar.empty()
                        st.success("Successfully copied files!")

            if not TK_AVAILABLE:
                c2.warning(
                    "**Warning**: Failed to import tkinter, either it is not installed, or this is being called from a cloud context. "
                    "This function is not available in a Streamlit Cloud context. "
                    "You will have to manually enter the path to the folder with the MS files."
                )

            if not use_copy:
                c2.warning(
                    "**Warning**: You have deselected the `Make a copy of files` option. "
                    "This **_assumes you know what you are doing_**. "
                    "This means that the original files will be used instead. "
                )

        if fallback and not any([f for f in Path(files_dir).iterdir() if f.name != "external_files.txt"]):
            if isinstance(fallback, str):
                fallback = [fallback]
            for f in fallback:
                c1, _ = st.columns(2)
                if not Path(files_dir, f).exists():
                    shutil.copy(f, Path(files_dir, Path(f).name))
            current_files = [f.name for f in files_dir.iterdir() if f.name != "external_files.txt"]
            c1.warning("**No data yet. Using example data file(s).**")
        else:
            if files_dir.exists():
                current_files = [
                    f.name
                    for f in files_dir.iterdir()
                    if "external_files.txt" not in f.name
                ]

                # Check if local files are available
                external_files = Path(
                    self.workflow_dir, "input-files", key, "external_files.txt"
                )

                if external_files.exists():
                    with open(external_files, "r") as f:
                        external_files_list = f.read().splitlines()
                    # Only make files available that still exist
                    current_files += [
                        f"(local) {Path(f).name}"
                        for f in external_files_list
                        if os.path.exists(f)
                    ]
            else:
                current_files = []

        if files_dir.exists() and not any(files_dir.iterdir()):
            shutil.rmtree(files_dir)

        c1, _ = st.columns(2)
        if current_files:
            c1.info(f"Current **{name}** files:\n\n" + "\n\n".join(current_files))
            if c1.button(
                f"🗑️ Clear **{name}** files.",
                use_container_width=True,
                key=f"remove-files-{key}",
            ):
                shutil.rmtree(files_dir)
                if key in self.params:
                    del self.params[key]
                with open(
                    self.parameter_manager.params_file, "w", encoding="utf-8"
                ) as f:
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
        reactive: bool = False,
    ) -> None:
        """
        Presents a widget for selecting input files from those that have been uploaded.
        Allows for single or multiple selections.

        Args:
            key (str): A unique identifier related to the specific input files.
            name (str, optional): The display name for the selection widget. Defaults to the key if not provided.
            multiple (bool, optional): If True, allows multiple files to be selected.
            display_file_path (bool, optional): If True, displays the full file path in the selection widget.
            reactive (bool, optional): If True, widget changes trigger the parent
                section to re-render, enabling conditional UI based on this widget's
                value. Use for widgets that control visibility of other UI elements.
                Default is False (widget changes are isolated for performance).
        """
        if reactive:
            self._select_input_file_impl(key, name, multiple, display_file_path, reactive)
        else:
            self._select_input_file_fragmented(key, name, multiple, display_file_path, reactive)

    @st.fragment
    def _select_input_file_fragmented(self, key, name, multiple, display_file_path, reactive):
        self._select_input_file_impl(key, name, multiple, display_file_path, reactive)

    def _select_input_file_impl(self, key, name, multiple, display_file_path, reactive):
        """Internal implementation of select_input_file - contains all the widget logic."""
        if not name:
            name = f"**{key}**"
        path = Path(self.workflow_dir, "input-files", key)
        if not path.exists():
            st.warning(f"No **{name}** files!")
            return
        options = [str(f) for f in path.iterdir() if "external_files.txt" not in str(f)]

        # Check if local files are available
        external_files = Path(
            self.workflow_dir, "input-files", key, "external_files.txt"
        )

        if external_files.exists():
            with open(external_files, "r") as f:
                external_files_list = f.read().splitlines()
            # Only make files available that still exist
            options += [f for f in external_files_list if os.path.exists(f)]
        if (key in self.params.keys()) and isinstance(self.params[key], list):
            self.params[key] = [f for f in self.params[key] if f in options]

        widget_type = "multiselect" if multiple else "selectbox"
        self.input_widget(
            key,
            name=name,
            widget_type=widget_type,
            options=options,
            display_file_path=display_file_path,
            reactive=reactive,
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
        on_change: Callable = None,
        reactive: bool = False,
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
            reactive (bool, optional): If True, widget changes trigger the parent
                section to re-render, enabling conditional UI based on this widget's
                value. Use for widgets that control visibility of other UI elements.
                Default is False (widget changes are isolated for performance).
        """
        if reactive:
            # Render directly in parent context - changes trigger parent rerun
            self._input_widget_impl(
                key, default, name, help, widget_type, options,
                min_value, max_value, step_size, display_file_path, on_change
            )
        else:
            # Render in isolated fragment - changes don't affect parent
            self._input_widget_fragmented(
                key, default, name, help, widget_type, options,
                min_value, max_value, step_size, display_file_path, on_change
            )

    @st.fragment
    def _input_widget_fragmented(
        self, key, default, name, help, widget_type,
        options, min_value, max_value, step_size,
        display_file_path, on_change
    ):
        self._input_widget_impl(
            key, default, name, help, widget_type,
            options, min_value, max_value, step_size,
            display_file_path, on_change
        )

    def _input_widget_impl(
        self, key, default, name, help, widget_type,
        options, min_value, max_value, step_size,
        display_file_path, on_change
    ):
        """Internal implementation of input_widget - contains all the widget logic."""

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
            st.text_input(name, value=value, key=key, help=help, on_change=on_change)

        elif widget_type == "textarea":
            st.text_area(name, value=value, key=key, help=help, on_change=on_change)

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
                on_change=on_change,
            )

        elif widget_type == "checkbox":
            st.checkbox(name, value=value, key=key, help=help, on_change=on_change)

        elif widget_type == "selectbox":
            if options is not None:
                st.selectbox(
                    name,
                    options=options,
                    index=options.index(value) if value in options else 0,
                    key=key,
                    format_func=format_files,
                    help=help,
                    on_change=on_change,
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
                    on_change=on_change,
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
                    on_change=on_change,
                )
            else:
                st.warning(
                    f"Slider widget '{name}' requires min_value and max_value parameters"
                )

        elif widget_type == "password":
            st.text_input(name, value=value, type="password", key=key, help=help, on_change=on_change)

        elif widget_type == "auto":
            # Auto-determine widget type based on value
            if isinstance(value, bool):
                st.checkbox(name, value=value, key=key, help=help, on_change=on_change)
            elif isinstance(value, (int, float)):
                self._input_widget_impl(
                    key,
                    value,
                    name=name,
                    help=help,
                    widget_type="number",
                    options=None,
                    min_value=min_value,
                    max_value=max_value,
                    step_size=step_size,
                    display_file_path=False,
                    on_change=on_change,
                )
            elif (isinstance(value, str) or value == None) and options is not None:
                self._input_widget_impl(
                    key,
                    value,
                    name=name,
                    help=help,
                    widget_type="selectbox",
                    options=options,
                    min_value=None,
                    max_value=None,
                    step_size=1,
                    display_file_path=False,
                    on_change=on_change,
                )
            elif isinstance(value, list) and options is not None:
                self._input_widget_impl(
                    key,
                    value,
                    name=name,
                    help=help,
                    widget_type="multiselect",
                    options=options,
                    min_value=None,
                    max_value=None,
                    step_size=1,
                    display_file_path=False,
                    on_change=on_change,
                )
            elif isinstance(value, bool):
                self._input_widget_impl(
                    key, value, name=name, help=help, widget_type="checkbox",
                    options=None, min_value=None, max_value=None, step_size=1,
                    display_file_path=False, on_change=on_change
                )
            else:
                self._input_widget_impl(
                    key, value, name=name, help=help, widget_type="text",
                    options=None, min_value=None, max_value=None, step_size=1,
                    display_file_path=False, on_change=on_change
                )

        else:
            st.error(f"Unsupported widget type '{widget_type}'")

        self.parameter_manager.save_parameters()

    @st.fragment
    def input_TOPP(
        self,
        topp_tool_name: str,
        num_cols: int = 4,
        exclude_parameters: List[str] = [],
        include_parameters: List[str] = [],
        display_tool_name: bool = True,
        display_subsections: bool = True,
        display_subsection_tabs: bool = False,
        custom_defaults: dict = {},
    ) -> None:
        """
        Generates input widgets for TOPP tool parameters dynamically based on the tool's
        .ini file. Supports excluding specific parameters and adjusting the layout.
        File input and output parameters are excluded.

        Args:
            topp_tool_name (str): The name of the TOPP tool for which to generate inputs.
            num_cols (int, optional): Number of columns to use for the layout. Defaults to 3.
            exclude_parameters (List[str], optional): List of parameter names to exclude from the widget. Defaults to an empty list.
            include_parameters (List[str], optional): List of parameter names to include in the widget. Defaults to an empty list.
            display_tool_name (bool, optional): Whether to display the TOPP tool name. Defaults to True.
            display_subsections (bool, optional): Whether to split parameters into subsections based on the prefix. Defaults to True.
            display_subsection_tabs (bool, optional): Whether to display main subsections in separate tabs (if more than one main section). Defaults to False.
            custom_defaults (dict, optional): Dictionary of custom defaults to use. Defaults to an empty dict.
        """

        if not display_subsections:
            display_subsection_tabs = False
        if display_subsection_tabs:
            display_subsections = True

        # write defaults ini files
        ini_file_path = Path(self.parameter_manager.ini_dir, f"{topp_tool_name}.ini")
        ini_existed = ini_file_path.exists()
        if not self.parameter_manager.create_ini(topp_tool_name):
            st.error(f"TOPP tool **'{topp_tool_name}'** not found.")
            return
        if not ini_existed:
            # update custom defaults if necessary
            if custom_defaults:
                param = poms.Param()
                poms.ParamXMLFile().load(str(ini_file_path), param)
                for key, value in custom_defaults.items():
                    encoded_key = f"{topp_tool_name}:1:{key}".encode()
                    if encoded_key in param.keys():
                        param.setValue(encoded_key, value)
                poms.ParamXMLFile().store(str(ini_file_path), param)

        # read into Param object
        param = poms.Param()
        poms.ParamXMLFile().load(str(ini_file_path), param)

        def _matches_parameter(pattern: str, key: bytes) -> bool:
            """
            Match pattern against TOPP parameter key using suffix matching.

            Key format: b"ToolName:1:section:subsection:param_name"

            Returns True if pattern matches the end of the param path,
            bounded by ':' or start of path.
            """
            pattern = pattern.lstrip(":")  # Strip legacy leading colon
            key_str = key.decode()

            # Extract param path after "ToolName:1:"
            parts = key_str.split(":")
            param_path = ":".join(parts[2:]) if len(parts) > 2 else key_str

            # Check if pattern matches as a suffix, bounded by ':' or start
            return param_path == pattern or param_path.endswith(":" + pattern)

        # Always apply base exclusions (input/output files, standard excludes)
        excluded_keys = [
            "log",
            "debug",
            "threads",
            "no_progress",
            "force",
            "version",
            "test",
        ] + exclude_parameters

        valid_keys = [
            key
            for key in param.keys()
            if not (
                b"input file" in param.getTags(key)
                or b"output file" in param.getTags(key)
                or any([_matches_parameter(k, key) for k in excluded_keys])
            )
        ]

        # Track which keys are "included" (shown by default) vs "non-included" (advanced only)
        if include_parameters:
            included_keys = {
                key for key in valid_keys
                if any([_matches_parameter(k, key) for k in include_parameters])
            }
        else:
            included_keys = set(valid_keys)  # All are included when no filter specified
        params = []
        for key in valid_keys:
            entry = param.getEntry(key)
            p = {
                "name": entry.name.decode(),
                "key": key,
                "value": entry.value,
                "original_is_list": isinstance(entry.value, list),
                "valid_strings": [v.decode() for v in entry.valid_strings],
                "description": entry.description.decode(),
                "advanced": (b"advanced" in param.getTags(key)),
                "non_included": key not in included_keys,
                "section_description": param.getSectionDescription(
                    ":".join(key.decode().split(":")[:-1])
                ),
            }
            # Parameter sections and subsections as string (e.g. "section:subsection")
            if display_subsections:
                p["sections"] = ":".join(
                    p["key"].decode().split(":1:")[1].split(":")[:-1]
                )
            params.append(p)

        # for each parameter in params_decoded
        # if a parameter with custom default value exists, use that value
        # else check if the parameter is already in self.params, if yes take the value from self.params
        for p in params:
            name = p["key"].decode().split(":1:")[1]
            if topp_tool_name in self.params:
                if name in self.params[topp_tool_name]:
                    p["value"] = self.params[topp_tool_name][name]
                elif name in custom_defaults:
                    p["value"] = custom_defaults[name]
            elif name in custom_defaults:
                p["value"] = custom_defaults[name]
            # Ensure list parameters stay as lists after loading from JSON
            # (JSON may store single-item lists as strings)
            if p["original_is_list"] and isinstance(p["value"], str):
                p["value"] = p["value"].split("\n") if p["value"] else []

        # Split into subsections if required
        param_sections = {}
        section_descriptions = {}
        if display_subsections:
            for p in params:
                # Skip advanced/non-included parameters if toggle not enabled
                if not st.session_state["advanced"] and (p["advanced"] or p["non_included"]):
                    continue
                # Add section description to section_descriptions dictionary if it exists
                if p["section_description"]:
                    section_descriptions[p["sections"]] = p["section_description"]
                # Add parameter to appropriate section in param_sections dictionary
                if not p["sections"]:
                    p["sections"] = "General"
                if p["sections"] in param_sections:
                    param_sections[p["sections"]].append(p)
                else:
                    param_sections[p["sections"]] = [p]
        else:
            # Simply put all parameters in "all" section if no subsections required
            # Filter advanced/non-included parameters if toggle not enabled
            param_sections["all"] = [
                p for p in params
                if st.session_state["advanced"] or (not p["advanced"] and not p["non_included"])
            ]

        # Display tool name if required
        if display_tool_name:
            st.markdown(f"**{topp_tool_name}**")

        tab_names = [k for k in param_sections.keys() if ":" not in k]
        tabs = None
        if tab_names and display_subsection_tabs:
            tabs = st.tabs([k for k in param_sections.keys() if ":" not in k])

        # Show input widgets
        def show_subsection_header(section: str, display_subsections: bool):
            # Display section name and help text (section description) if required
            if section and display_subsections:
                parts = section.split(":")
                st.markdown(
                    ":".join(parts[:-1])
                    + (":" if len(parts) > 1 else "")
                    + f"**{parts[-1]}**",
                    help=(
                        section_descriptions[section]
                        if section in section_descriptions
                        else None
                    ),
                )

        def display_TOPP_params(params: dict, num_cols):
            """Displays individual TOPP parameters in given number of columns"""
            cols = st.columns(num_cols)
            i = 0
            for p in params:
                # get key and name
                key = f"{self.parameter_manager.topp_param_prefix}{p['key'].decode()}"
                name = p["name"]
                try:
                    # sometimes strings with newline, handle as list
                    if isinstance(p["value"], str) and "\n" in p["value"]:
                        p["value"] = p["value"].split("\n")
                    # bools
                    if isinstance(p["value"], bool):
                        cols[i].markdown("##")
                        cols[i].checkbox(
                            name,
                            value=(
                                (p["value"] == "true")
                                if type(p["value"]) == str
                                else p["value"]
                            ),
                            help=p["description"],
                            key=key,
                        )

                    # strings
                    elif isinstance(p["value"], str):
                        # string options
                        if p["valid_strings"]:
                            cols[i].selectbox(
                                name,
                                options=p["valid_strings"],
                                index=p["valid_strings"].index(p["value"]),
                                help=p["description"],
                                key=key,
                            )
                        else:
                            cols[i].text_input(
                                name, value=p["value"], help=p["description"], key=key
                            )

                    # ints
                    elif isinstance(p["value"], int):
                        cols[i].number_input(
                            name, value=int(p["value"]), help=p["description"], key=key
                        )

                    # floats
                    elif isinstance(p["value"], float):
                        cols[i].number_input(
                            name,
                            value=float(p["value"]),
                            step=1.0,
                            help=p["description"],
                            key=key,
                        )

                    # lists
                    elif isinstance(p["value"], list):
                        p["value"] = [
                            v.decode() if isinstance(v, bytes) else v
                            for v in p["value"]
                        ]

                        # Use multiselect when valid_strings are available for better UX
                        if len(p['valid_strings']) > 0:
                            # Filter current values to only include valid options
                            current_values = [v for v in p["value"] if v in p['valid_strings']]

                            # Use a display key for multiselect (stores list), sync to main key (stores string)
                            display_key = f"{key}_display"

                            def on_multiselect_change(dk=display_key, tk=key):
                                st.session_state[tk] = "\n".join(st.session_state[dk])

                            cols[i].multiselect(
                                name,
                                options=sorted(p['valid_strings']),
                                default=current_values,
                                help=p["description"],
                                key=display_key,
                                on_change=on_multiselect_change,
                            )

                            # Ensure main key has string value for ParameterManager
                            if key not in st.session_state:
                                st.session_state[key] = "\n".join(current_values)
                        else:
                            # Fall back to text_area for freeform list input
                            cols[i].text_area(
                                name,
                                value="\n".join([str(val) for val in p["value"]]),
                                help=p["description"] + " Separate entries using the \"Enter\" key.",
                                key=key,
                            )

                    # increment number of columns, create new cols object if end of line is reached
                    i += 1
                    if i == num_cols:
                        i = 0
                        cols = st.columns(num_cols)
                except Exception as e:
                    cols[i].error(f"Error in parameter **{p['name']}**.")
                    print('Error parsing "' + p["name"] + '": ' + str(e))


        for section, params in param_sections.items():
            if tabs is None:
                show_subsection_header(section, display_subsections)
                display_TOPP_params(params, num_cols)
            else:
                tab_name = section.split(":")[0]
                with tabs[tab_names.index(tab_name)]:
                    show_subsection_header(section, display_subsections)
                    display_TOPP_params(params, num_cols)
        
        self.parameter_manager.save_parameters()
            

    @st.fragment
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
        self.parameter_manager.save_parameters()

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

        c1, _ = st.columns(2)
        # Initialize Streamlit progress bar
        my_bar = c1.progress(0)

        with zipfile.ZipFile(bytes_io, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for i, file_path in enumerate(files):
                if (
                    file_path.is_file()
                ):  # Ensure we're only adding files, not directories
                    # Preserve directory structure relative to the original directory
                    zip_file.write(file_path, file_path.relative_to(directory.parent))
                    my_bar.progress((i + 1) / n_files)  # Update progress bar

        my_bar.empty()  # Clear progress bar after operation is complete
        bytes_io.seek(0)  # Reset buffer pointer to the beginning

        # Display a download button for the zip file in Streamlit
        c1.download_button(
            label="⬇️ Download Now",
            data=bytes_io,
            file_name="input-files.zip",
            mime="application/zip",
            use_container_width=True,
        )

    def preset_buttons(self, num_cols: int = 4) -> None:
        """
        Renders a grid of preset buttons for the current workflow.

        When a preset button is clicked, the preset parameters are applied to the
        session state and saved to params.json, then the page is reloaded.

        Args:
            num_cols: Number of columns for the button grid. Defaults to 4.
        """
        preset_names = self.parameter_manager.get_preset_names()
        if not preset_names:
            return

        st.markdown("---")
        st.markdown("**Parameter Presets**")
        st.caption("Click a preset to apply optimized parameters")

        # Create button grid
        cols = st.columns(num_cols)
        for i, preset_name in enumerate(preset_names):
            col_idx = i % num_cols
            description = self.parameter_manager.get_preset_description(preset_name)
            with cols[col_idx]:
                if st.button(
                    preset_name,
                    key=f"preset_{preset_name}",
                    help=description if description else None,
                    use_container_width=True,
                ):
                    if self.parameter_manager.apply_preset(preset_name):
                        st.toast(f"Applied preset: {preset_name}")
                        st.rerun()
                    else:
                        st.error(f"Failed to apply preset: {preset_name}")
            # Start new row if needed
            if col_idx == num_cols - 1 and i < len(preset_names) - 1:
                cols = st.columns(num_cols)

    def file_upload_section(self, custom_upload_function) -> None:
        custom_upload_function()
        c1, _ = st.columns(2)
        if c1.button("⬇️ Download files", use_container_width=True):
            self.zip_and_download_files(Path(self.workflow_dir, "input-files"))

    def parameter_section(self, custom_parameter_function) -> None:
        st.toggle("Show advanced parameters", value=False, key="advanced")

        # Display preset buttons if presets are available for this workflow
        self.preset_buttons()

        custom_parameter_function()

        # File Import / Export section       
        st.markdown("---")
        cols = st.columns(3)
        with cols[0]:
            if st.button(
                "⚠️ Load default parameters",
                help="Reset parameter section to default.",
                use_container_width=True,
            ):
                self.parameter_manager.reset_to_default_parameters()
                self.parameter_manager.clear_parameter_session_state()
                st.toast("Parameters reset to defaults")
                st.rerun()
        with cols[1]:
            if self.parameter_manager.params_file.exists():
                with open(self.parameter_manager.params_file, "rb") as f:
                    st.download_button(
                        "⬇️ Export parameters",
                        data=f,
                        file_name="parameters.json",
                        mime="text/json",
                        help="Export parameter, can be used to import to this workflow.",
                        use_container_width=True,
                    )
            text = self.export_parameters_markdown()
            st.download_button(
                "📑 Method summary",
                data=text,
                file_name="method-summary.md",
                mime="text/md",
                help="Download method summary for publications.",
                use_container_width=True,
            )

        with cols[2]:
            up = st.file_uploader(
                "⬆️ Import parameters",
                help="Import previously exported parameters.",
                key="param_import_uploader"
            )
            if up is not None:
                with open(self.parameter_manager.params_file, "w") as f:
                    f.write(up.read().decode("utf-8"))
                self.parameter_manager.clear_parameter_session_state()
                st.toast("Parameters imported")
                st.rerun()

    def execution_section(
        self,
        start_workflow_function,
        get_status_function=None,
        stop_workflow_function=None
    ) -> None:
        with st.expander("**Summary**"):
            st.markdown(self.export_parameters_markdown())

        c1, c2 = st.columns(2)
        # Select log level, this can be changed at run time or later without re-running the workflow
        log_level = c1.selectbox(
            "log details", ["minimal", "commands and run times", "all"], key="log_level"
        )

        # Real-time display options
        if "log_lines_count" not in st.session_state:
            st.session_state.log_lines_count = 100

        log_lines_count = c2.selectbox(
            "lines to show", [50, 100, 200, 500, "all"],
            index=1, key="log_lines_select"
        )
        if log_lines_count != "all":
            st.session_state.log_lines_count = log_lines_count

        # Get workflow status (supports both queue and local modes)
        status = {}
        if get_status_function:
            status = get_status_function()

        # Determine if workflow is running
        is_running = status.get("running", False)
        job_status = status.get("status", "idle")

        # Fallback to PID check for backward compatibility
        pid_exists = self.executor.pid_dir.exists() and list(self.executor.pid_dir.iterdir())
        if not is_running and pid_exists:
            is_running = True
            job_status = "running"

        log_path = Path(self.workflow_dir, "logs", log_level.replace(" ", "-") + ".log")
        log_exists = log_path.exists()

        # Show queue status if available (online mode)
        if status.get("job_id"):
            self._show_queue_status(status)

        # Control buttons
        if is_running:
            if c1.button("Stop Workflow", type="primary", use_container_width=True):
                if stop_workflow_function:
                    stop_workflow_function()
                else:
                    self.executor.stop()
                st.rerun()
        elif c1.button("Start Workflow", type="primary", use_container_width=True):
            start_workflow_function()
            with st.spinner("**Workflow starting...**"):
                time.sleep(1)
                st.rerun()

        # Display logs and status
        if is_running:
            # Real-time display during execution
            spinner_text = "**Workflow running...**"
            if job_status == "queued":
                pos = status.get("queue_position", "?")
                spinner_text = f"**Waiting in queue (position {pos})...**"

            with st.spinner(spinner_text):
                if log_exists:
                    with open(log_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    if log_lines_count == "all":
                        display_lines = lines
                    else:
                        display_lines = lines[-st.session_state.log_lines_count:]
                    st.code(
                        "".join(display_lines),
                        language="neon",
                        line_numbers=False,
                    )
                # Faster polling for real-time updates
                time.sleep(1)
                st.rerun()

        elif log_exists:
            # Static display after completion
            st.markdown(
                f"**Workflow log file: {datetime.fromtimestamp(log_path.stat().st_ctime).strftime('%Y-%m-%d %H:%M')} CET**"
            )
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            content = "".join(lines)
            # Check if workflow finished successfully
            if "WORKFLOW FINISHED" in content:
                st.success("**Workflow completed successfully.**")
            else:
                st.error("**Errors occurred, check log file.**")
            # Apply line limit to static display
            if log_lines_count == "all":
                display_lines = lines
            else:
                display_lines = lines[-st.session_state.log_lines_count:]
            st.code("".join(display_lines), language="neon", line_numbers=False)

    def _show_queue_status(self, status: dict) -> None:
        """Display queue job status for online mode"""
        job_status = status.get("status", "unknown")

        # Status icons
        status_display = {
            "queued": ("Queued", "info"),
            "started": ("Running", "info"),
            "finished": ("Completed", "success"),
            "failed": ("Failed", "error"),
            "canceled": ("Cancelled", "warning"),
        }

        label, msg_type = status_display.get(job_status, ("Unknown", "info"))

        # Queue-specific information
        if job_status == "queued":
            queue_position = status.get("queue_position", "?")
            queue_length = status.get("queue_length", "?")
            st.info(f"**Status: {label}** - Your workflow is #{queue_position} in the queue ({queue_length} total jobs)")

        elif job_status == "started":
            current_step = status.get("current_step", "Processing...")
            st.info(f"**Status: {label}** - {current_step}")

        elif job_status == "finished":
            # Check if the job result indicates success or failure
            job_result = status.get("result")
            if job_result and isinstance(job_result, dict) and job_result.get("success") is False:
                st.error(f"**Status: Completed with errors**")
                error_msg = job_result.get("error", "Unknown error")
                if error_msg:
                    with st.expander("Error Details", expanded=True):
                        st.code(error_msg)
            else:
                st.success(f"**Status: {label}**")

        elif job_status == "failed":
            st.error(f"**Status: {label}**")
            job_error = status.get("error")
            if job_error:
                with st.expander("Error Details", expanded=True):
                    st.code(job_error)

        # Expandable job details
        with st.expander("Job Details", expanded=False):
            st.code(f"""Job ID: {status.get('job_id', 'N/A')}
Submitted: {status.get('enqueued_at', 'N/A')}
Started: {status.get('started_at', 'N/A')}""")



    def results_section(self, custom_results_function) -> None:
        custom_results_function()

    def non_default_params_summary(self):
        # Display a summary of non-default TOPP parameters and all others (custom and python scripts)

        def remove_full_paths(d: dict) -> dict:
            # Create a copy to avoid modifying the original dictionary
            cleaned_dict = {}

            for key, value in d.items():
                if isinstance(value, dict):
                    # Recursively clean nested dictionaries
                    nested_cleaned = remove_full_paths(value)
                    if nested_cleaned:  # Only add non-empty dictionaries
                        cleaned_dict[key] = nested_cleaned
                elif isinstance(value, list):
                    # Filter out existing paths from the list
                    filtered_list = [
                        item if not Path(str(item)).exists() else Path(str(item)).name
                        for item in value
                    ]
                    if filtered_list:  # Only add non-empty lists
                        cleaned_dict[key] = ", ".join(filtered_list)
                elif not Path(str(value)).exists():
                    # Add entries that are not existing paths
                    cleaned_dict[key] = value

            return cleaned_dict

        # Don't want file paths to be shown in summary for export
        params = remove_full_paths(self.params)

        summary_text = ""
        python = {}
        topp = {}
        general = {}

        for k, v in params.items():
            # skip if v is a file path
            if isinstance(v, dict):
                topp[k] = v
            elif ".py" in k:
                script = k.split(".py")[0] + ".py"
                if script not in python:
                    python[script] = {}
                python[script][k.split(".py")[1][1:]] = v
            else:
                general[k] = v

        markdown = []

        def dict_to_markdown(d: dict):
            for key, value in d.items():
                if isinstance(value, dict):
                    # Add a header for nested dictionaries
                    markdown.append(f"> **{key}**\n")
                    dict_to_markdown(value)
                else:
                    # Add key-value pairs as list items
                    markdown.append(f">> {key}: **{value}**\n")

        if len(general) > 0:
            markdown.append("**General**")
            dict_to_markdown(general)
        if len(topp) > 0:
            markdown.append("**OpenMS TOPP Tools**\n")
            dict_to_markdown(topp)
        if len(python) > 0:
            markdown.append("**Python Scripts**")
            dict_to_markdown(python)
        return "\n".join(markdown)

    def export_parameters_markdown(self):
        markdown = []

        url = f"https://github.com/{st.session_state.settings['github-user']}/{st.session_state.settings['repository-name']}"
        tools = [p.stem for p in Path(self.parameter_manager.ini_dir).iterdir()]
        if len(tools) > 1:
            tools = ", ".join(tools[:-1]) + " and " + tools[-1]

        result = subprocess.run(
            "FileFilter --help", shell=True, text=True, capture_output=True
        )
        version = ""
        if result.returncode == 0:
            version = result.stderr.split("Version: ")[1].split("-")[0]

        markdown.append(
            f"""Data was processed using **{st.session_state.settings['app-name']}** ([{url}]({url})), a web application based on the OpenMS WebApps framework [1].
OpenMS ([https://www.openms.de](https://www.openms.de)) is a free and open-source software for LC-MS data analysis [2].
The workflow includes the **OpenMS {version}** TOPP tools {tools} as well as Python scripts. Non-default parameters are listed in the supplementary section below.

[1] Müller, Tom David, et al. "OpenMS WebApps: Building User-Friendly Solutions for MS Analysis." (2025) [https://doi.org/10.1021/acs.jproteome.4c00872](https://doi.org/10.1021/acs.jproteome.4c00872).
\\
[2] Pfeuffer, Julianus, et al. "OpenMS 3 enables reproducible analysis of large-scale mass spectrometry data." (2024) [https://doi.org/10.1038/s41592-024-02197-7](https://doi.org/10.1038/s41592-024-02197-7).
"""
        )
        markdown.append(self.non_default_params_summary())
        return "\n".join(markdown)
