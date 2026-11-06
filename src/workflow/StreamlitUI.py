import streamlit as st
import pyopenms as poms
from pathlib import Path
import shutil
import filecmp
import subprocess
from typing import Any, Callable, Dict, List, Literal, Union
import json
import math
import os
import sys
import importlib.util
import time
from io import BytesIO
import pandas as pd
import zipfile
from datetime import datetime


from src.common.common import (
    OS_PLATFORM,
    TK_AVAILABLE,
    export_files,
    export_folder_input,
    tk_directory_dialog,
    tk_file_dialog,
)
from src.workflow._log_status import classify_log_outcome
from src.workflow.progress import (
    DONE,
    FAILED,
    RUNNING,
    current_step,
    failures,
    file_counts,
    format_duration,
    read_progress,
    sample_counts,
    tool_progress,
)
from src.workflow.InputFolders import (
    design_rows,
    folder_counts,
    load_folders,
    natural_key,
    rename_folder,
    save_folders,
    suggest_groups,
)
from src.workflow.ExperimentalDesign import (
    align_design,
    check_design,
    design_path,
    load_design,
    read_design,
    save_design,
    to_openms_design,
)
from src.workflow.vendor_files import extract_bruker_zip, has_type
from src.workflow.settings_io import (
    THREADS_USER_MARKER,
    local_thread_default,
    local_threads_pinned,
    usable_cpu_count,
)
from src.data_import import ui as data_import_ui
from src.workflow.ParameterManager import (
    InvalidParameterFileError,
    ParameterManager,
    TransientParameterFileError,
)
from src.workflow.parameter_names import display_name as _display_name


def _txt(value) -> str:
    """Text from pyOpenMS: bytes up to pyOpenMS 3.5, str from 3.6 (nanobind)."""
    return value.decode() if isinstance(value, bytes) else str(value)


def _tags(param, key) -> list[str]:
    """A parameter's tags as str, whichever pyOpenMS gave them."""
    return [_txt(t) for t in param.getTags(key)]


def _valid_strings(entry) -> list[str]:
    """A parameter's allowed strings. pyOpenMS 3.6 raises TypeError when asked
    for those of a boolean parameter, which is a checkbox and has none."""
    if isinstance(entry.value, bool):
        return []
    return [_txt(v) for v in entry.valid_strings]


def _matches_topp_parameter(pattern: str, key) -> bool:
    """
    Match an include/exclude pattern against a TOPP parameter key.

    Key format: "ToolName:1:section:subsection:param_name" (bytes before
    pyOpenMS 3.6)

    A pattern matches the end of the parameter path, bounded by ':' or the
    start of the path ("tol" matches "FD:tol"). A pattern ending in ':' names
    a whole section from the top of the path instead ("fd:" matches every
    parameter under "fd:", but not "FD:" or "algorithm:fd:").
    """
    pattern = pattern.lstrip(":")  # Strip legacy leading colon
    key_str = _txt(key)

    # Extract param path after "ToolName:1:"
    parts = key_str.split(":")
    param_path = ":".join(parts[2:]) if len(parts) > 2 else key_str

    if pattern.endswith(":"):
        return param_path.startswith(pattern)

    # Check if pattern matches as a suffix, bounded by ':' or start
    return param_path == pattern or param_path.endswith(":" + pattern)


def _mounted_data_root() -> Union[Path, None]:
    """Return the validated mount root from the ``local_data_dir`` setting.

    The browser renders only when ``local_data_dir`` is an actual mount
    point inside the container — i.e. the operator passed ``-v`` /
    ``--bind`` / ``volumeMount`` to attach host data. Existence alone is
    no longer sufficient because the image now pre-creates the path so
    apptainer/singularity binds have a real attach target; without
    ``os.path.ismount`` the browser would render an empty tree for every
    user who didn't mount anything.
    """
    settings = st.session_state.get("settings") or {}
    raw = (settings.get("local_data_dir") or "").strip()
    if not raw:
        return None
    try:
        p = Path(raw).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not p.is_dir():
        return None
    if not os.path.ismount(p):
        return None
    return p


def _plain(value):
    """A parameter value as params.json stores it (lists as newline-joined text)."""
    if isinstance(value, list):
        return "\n".join(v.decode() if isinstance(v, bytes) else str(v) for v in value)
    return value


def _as_str_list(value) -> list[str]:
    """A list parameter's value as a list of str: bytes items decoded, and
    newline-separated text (as params.json stores lists) split into items,
    empty ones included, as CommandExecutor.run_topp() passes them."""
    if isinstance(value, (list, tuple)):
        return [v.decode() if isinstance(v, bytes) else str(v) for v in value]
    if isinstance(value, bytes):
        value = value.decode()
    if value is None or value == "":
        return []
    return str(value).split("\n")


def _short(value) -> str:
    """A parameter value for a caption or tooltip."""
    if isinstance(value, list):
        text = ", ".join(str(v) for v in value) or "empty"
    elif value == "":
        text = "empty"
    else:
        text = str(value)
    return text if len(text) <= 40 else text[:37] + "..."


def editor_table(state, editor_key: str, table, fits=None):
    """The table to hand ``st.data_editor(key=editor_key)`` in this run.

    A data editor keeps its edits as changes to the table it was first drawn
    with, and Streamlit identifies it by that table as well as its key. An app
    that saves each edit and draws the editor from the saved data would hand
    it a new table after every edit: Streamlit then draws a new editor and the
    edit made in that run is lost (every second value typed and confirmed with
    Tab or Enter vanished). So the first table is kept in ``state`` and used
    again while the editor stays on the page. ``table`` (a value, or a
    function returning one) is taken again when the editor was not drawn in
    the previous run (first visit, back from another page), so a change saved
    meanwhile shows, or when ``fits(kept_table)`` is false (other rows).
    Pass a new ``editor_key`` to start from ``table`` again (e.g. after an
    import replaced the data).
    """
    kept_key = f"_{editor_key}-table"
    kept = state.get(kept_key)
    if kept is None or editor_key not in state or (fits is not None and not fits(kept)):
        kept = table() if callable(table) else table
        state[kept_key] = kept
    return kept


def latest_results_key(workflow_dir) -> str:
    """Session-state flag the Run page's results button sets for the results page."""
    return f"{Path(workflow_dir).name}-show-latest-results"


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
        # upload key -> name, file types, folder and example files of each
        # upload_widget() on the page, for "Import from a link"
        self.upload_targets = {}
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
        fallback: Union[List, str, Dict[str, str]] = None,
        suggest_folders: bool = False,
        list_files: bool = True,
    ) -> None:
        """
        Handles file uploads through the Streamlit interface, supporting both direct
        uploads and local directory copying for specified file types. It allows for
        specifying fallback files to ensure essential files are available.

        Args:
            key (str): A unique identifier for the upload component.
            file_types (Union[str, List[str]]): Expected file type(s) for the uploaded files.
                ``"d"`` accepts Bruker .d folders: from a local folder, or online as
                a zip archive. Convert vendor files before use with
                ``CommandExecutor.convert_to_mzml()``.
            name (str, optional): Display name for the upload component. Defaults to the key if not provided.
            fallback (Union[List, str, Dict[str, str]], optional): Default files
                to use if no files are uploaded. A dict maps each file to the
                folder it is put in when it is copied, so the examples arrive
                sorted.
            suggest_folders (bool, optional): Offer to sort the files into folders
                by the groups their names suggest (``ctrl_R1``, ``ctrl_R2``,
                ``treated_R1`` ...). Folders are labels kept in
                ``input-folders.json``; ``experimental_design()`` takes them
                as conditions.
            list_files (bool, optional): Show the current files below the
                upload. ``select_input_file(upload=...)`` lists them itself.
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

        # Convert file_types to a list if it's a string
        if isinstance(file_types, str):
            file_types = [file_types]

        # Where "Import from a link" can put files, see file_upload_section()
        self.upload_targets[key] = {
            "name": name,
            "file_types": list(file_types),
            "dir": str(files_dir),
            "fallback": [str(Path(f).resolve()) for f in ([fallback] if isinstance(fallback, str) else fallback or [])],
        }

        c1, c2 = st.columns(2)

        mount_root = _mounted_data_root() if st.session_state.location == "online" else None

        if st.session_state.location == "local":
            # A local install reads files straight from disk, so the browser
            # upload widget (which streams every byte through the browser) is
            # not offered. Files are picked from disk and copied or referenced.
            c1.markdown("**Add file(s) from your computer**")
            c2_text, c2_checkbox = c2.columns([1.5, 1], gap="large")
            c2_text.markdown("**OR add files from local folder**")
            use_copy = c2_checkbox.checkbox(
                "Make a copy of files",
                key=f"{key}-copy_files",
                value=True,
                help="Create a copy of files in workspace.",
            )
        else:
            c1.markdown("**Upload file(s)**")
            use_copy = True

        if st.session_state.location != "local":
            with c1.form(f"{key}-upload", clear_on_submit=True):
                # Streamlit file uploader accepts file types as a list or None.
                # A .d folder cannot be uploaded from a browser, only a zip of it.
                file_type_for_uploader = (
                    file_types + ["zip"] if "d" in file_types else file_types
                ) if file_types else None

                files = st.file_uploader(
                    f"{name}",
                    accept_multiple_files=False,
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
                        failed = False
                        for f in files:
                            if "d" in file_types and f.name.lower().endswith(".zip"):
                                try:
                                    added = extract_bruker_zip(f, files_dir)
                                except zipfile.BadZipFile:
                                    added = []
                                if not added:
                                    st.error(f"**{f.name}** holds no Bruker .d folder.")
                                    failed = True
                            # Check if file type is in the list of accepted file types
                            elif f.name not in [
                                f.name for f in files_dir.iterdir()
                            ] and has_type(f.name, file_types):
                                with open(Path(files_dir, f.name), "wb") as fh:
                                    fh.write(f.getbuffer())
                        if not failed:
                            st.success("Successfully added uploaded files!")
                    else:
                        st.error("Nothing to add, please upload file.")
        else:
            external_files = Path(files_dir, "external_files.txt")
            c1.write("\n")
            with c1.container(border=True):
                dialog_button = st.button(
                    rf"$\textsf{{\Large 📁 Add }} \textsf{{ \Large \textbf{{{name}}} }}$",
                    type="primary",
                    use_container_width=True,
                    key=f"local_browse_single_{key}",
                    help="Browse for your local MS data files.",
                    disabled=not TK_AVAILABLE,
                )

                # Tk file dialog requires file types to be a list of tuples.
                # Both cases: Thermo writes .raw as well as .RAW.
                tk_file_types = [
                    (f"{ft}", f"*.{ft} *.{ft.upper()}") for ft in file_types
                ]
                if "d" in file_types:
                    st.caption(
                        "Bruker **.d** folders can't be picked here: add the "
                        "folder that contains them on the right."
                    )

                if dialog_button:
                    local_files = tk_file_dialog(
                        "Select your local MS data files",
                        tk_file_types,
                        st.session_state["previous_dir"],
                    )
                    if local_files:
                        my_bar = st.progress(0)
                        for i, f in enumerate(local_files):
                            my_bar.progress((i + 1) / len(local_files))
                            if use_copy:
                                if os.path.isdir(f):
                                    shutil.copytree(
                                        f,
                                        Path(files_dir, Path(f).name),
                                        dirs_exist_ok=True,
                                    )
                                else:
                                    shutil.copy(f, Path(files_dir, Path(f).name))
                            else:
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
                            if has_type(path, [ft]):
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

        if mount_root is not None:
            with c2:
                self._mounted_drive_browser(key, name, file_types, files_dir, mount_root)

        external_files_path = Path(files_dir, "external_files.txt")
        has_real_files = any(
            p.name != "external_files.txt" for p in files_dir.iterdir()
        )
        has_external_picks = external_files_path.exists() and any(
            line.strip() and os.path.exists(line.strip())
            for line in external_files_path.read_text().splitlines()
        )
        if fallback and not has_real_files and not has_external_picks:
            if isinstance(fallback, str):
                fallback = [fallback]
            for f in fallback:
                c1, _ = st.columns(2)
                if not Path(files_dir, f).exists():
                    shutil.copy(f, Path(files_dir, Path(f).name))
            self._fallback_folders(key, fallback)
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

        if not list_files:
            return
        c1, _ = st.columns(2)
        if current_files:
            self._input_folders(key, name, current_files, suggest_folders)
            c1, _ = st.columns(2)
            if c1.button(
                f"🗑️ Clear **{name}** files.",
                use_container_width=True,
                key=f"remove-files-{key}",
            ):
                shutil.rmtree(files_dir)
                save_folders(self.workflow_dir, key, {})
                if key in self.params:
                    del self.params[key]
                with open(
                    self.parameter_manager.params_file, "w", encoding="utf-8"
                ) as f:
                    json.dump(self.params, f, indent=4)
                st.rerun()
        elif not fallback:
            st.warning(f"No **{name}** files!")

    def _input_folders(
        self, key: str, name: str, current_files: List[str], suggest: bool,
        select: dict = None,
    ) -> None:
        """The current files of upload ``key``, browsed and organized by folder.

        A folder is a label (``InputFolders``); the files do not move. With
        ``suggest``, groups read from the file names are offered as folders.
        With ``select`` (``widget``: the selection's session key, ``paths``:
        file name -> path, ``multiple``) the table also selects files.
        """
        # "(local) name" marks a referenced file; folders are kept by file name
        names = sorted(
            {f.removeprefix("(local) ") for f in current_files}, key=natural_key
        )
        local = {f.removeprefix("(local) ") for f in current_files if f.startswith("(local) ")}
        folders = {
            f: d for f, d in load_folders(self.workflow_dir, key).items() if f in names
        }
        counts = folder_counts(folders, names)
        unfiled = [n for n in names if n not in folders]
        version_key = f"_folders-{Path(self.workflow_dir).name}-{key}"
        st.session_state.setdefault(version_key, 0)

        def changed():
            st.session_state[version_key] += 1
            try:  # upload_widget() is a fragment; a full app run cannot rerun it alone
                st.rerun(scope="fragment")
            except st.errors.StreamlitAPIException:
                st.rerun()

        if select is None:
            st.markdown(f"**Current {name} files** ({len(names)})")
        if suggest and unfiled:
            proposal = {
                s.file: s.group for s in suggest_groups(names) if s.file in unfiled
            }
            if proposal:
                groups = folder_counts(proposal, list(proposal))
                text = ", ".join(f"**{g}** ({n})" for g, n in groups.items())
                c1, c2 = st.columns([3, 1], vertical_alignment="center")
                c1.info(
                    f"The file names suggest {len(groups)} groups: {text}.",
                    icon="💡",
                )
                if c2.button(
                    "Sort into these folders",
                    key=f"{version_key}-suggest",
                    use_container_width=True,
                    help="Put each file in the folder of its group. "
                    "Files already in a folder stay where they are.",
                ):
                    save_folders(self.workflow_dir, key, {**folders, **proposal})
                    changed()

        all_label = f"All files ({len(names)})"
        views = {all_label: None}
        views.update({f"📁 {d} ({n})": d for d, n in counts.items()})
        if counts and unfiled:
            views[f"Not in a folder ({len(unfiled)})"] = ""
        view_key = f"{version_key}-view"
        # A renamed folder changes its label: fall back to all files
        if st.session_state.get(view_key) not in views:
            st.session_state[view_key] = all_label
        if len(views) > 1:
            label = st.pills(
                "Folder",
                list(views),
                key=view_key,
                label_visibility="collapsed",
            )
            view = views.get(label) if label else None
        else:
            view = None
        shown = [
            n for n in names
            if view is None or folders.get(n, "") == view
        ]
        selected = set()
        if select is not None:
            value = st.session_state.get(
                f"_pending-{select['widget']}", st.session_state.get(select["widget"])
            ) or []
            value = [value] if isinstance(value, str) else value
            selected = {Path(v).name for v in value}
        table = pd.DataFrame({
            "file": [f"{n} (referenced)" if n in local else n for n in shown],
            "folder": [folders.get(n, "") for n in shown],
        })
        if select is not None:
            table.insert(0, "use", [n in selected for n in shown])
            if select["multiple"]:
                c1, c2, _ = st.columns([1, 1, 2])
                if c1.button(
                    "Select all shown", key=f"{version_key}-all", use_container_width=True
                ):
                    self._set_selection(select, sorted(selected | set(shown), key=natural_key))
                    changed()
                if c2.button(
                    "Clear selection", key=f"{version_key}-none", use_container_width=True
                ):
                    self._set_selection(select, sorted(selected - set(shown), key=natural_key))
                    changed()
        edited = st.data_editor(
            table,
            key=f"{version_key}-{st.session_state[version_key]}-{view}",
            hide_index=True,
            num_rows="fixed",
            disabled=["file"],
            use_container_width=True,
            column_config={
                "use": st.column_config.CheckboxColumn(
                    "Use", help="Use this file in the analysis."
                ),
                "file": st.column_config.TextColumn("File"),
                "folder": st.column_config.TextColumn(
                    "Folder",
                    help="Type a folder name to put the file in it (a new "
                    "name makes a new folder); clear it to take the file out.",
                ),
            },
        )
        new = {
            n: str(d).strip() if isinstance(d, str) else ""
            for n, d in zip(shown, edited["folder"])
        }
        if any(new[n] != folders.get(n, "") for n in shown):
            save_folders(self.workflow_dir, key, {**folders, **new})
            changed()
        if select is not None:
            ticked = {n for n, u in zip(shown, edited["use"]) if u}
            before = selected & set(shown)
            if ticked != before:
                if select["multiple"]:
                    chosen = (selected - set(shown)) | ticked
                else:  # one file: the one just ticked
                    chosen = (ticked - before) or ticked
                    chosen = set(sorted(chosen, key=natural_key)[:1])
                self._set_selection(select, sorted(chosen, key=natural_key))
                changed()

        if counts:
            with st.popover("Rename or remove a folder"):
                old = st.selectbox("Folder", list(counts), key=f"{version_key}-old")
                new_name = st.text_input(
                    "New name", value=old, key=f"{version_key}-new-{old}"
                ).strip()
                c1, c2 = st.columns(2)
                if c1.button(
                    "Rename",
                    key=f"{version_key}-rename",
                    disabled=not new_name or new_name == old,
                    use_container_width=True,
                ):
                    rename_folder(self.workflow_dir, key, old, new_name)
                    changed()
                if c2.button(
                    "Remove folder",
                    key=f"{version_key}-remove",
                    help="The files stay; they are just no longer in a folder.",
                    use_container_width=True,
                ):
                    rename_folder(self.workflow_dir, key, old, "")
                    changed()

    def _set_selection(self, select: dict, names: List[str]) -> None:
        """Make the files ``names`` the selection of ``select``.

        The selection widget is not drawn while the pop-out is open, and the
        browser would send its old value back with the next run, so the new
        one waits under ``_pending-<widget>`` until the widget is drawn again.
        """
        paths = [select["paths"][n] for n in names if n in select["paths"]]
        st.session_state[f"_pending-{select['widget']}"] = (
            paths if select["multiple"] else (paths[0] if paths else None)
        )

    def _browse_input_files(
        self, key: str, name: str, multiple: bool, upload: dict
    ) -> None:
        """The pop-out of ``select_input_file(upload=...)``: the files by
        folder, which of them are used, and the ways to add more."""
        plain_name = name.replace("*", "")

        @st.dialog(f"📂 {plain_name}", width="large", on_dismiss="rerun")
        def browse():
            # The same ways to add files as the upload page's tabs.
            importing = data_import_ui.enabled()
            # A protein database comes from UniProt rather than from a PRIDE
            # dataset, so its UniProt tab follows "Your files" and PRIDE is left out.
            uniprot = bool(upload.get("uniprot"))
            pride = importing and not uniprot
            labels = ["📁 Your files"]
            if uniprot:
                labels.append("🔎 Import from UniProt proteome")
            labels.append("💻 Data on your computer")
            if importing:
                labels.append("☁️ Cloud data")
            if pride:
                labels.append("🧬 Import from PRIDE")
            tabs = dict(zip(labels, st.tabs(labels)))
            tab_list = list(tabs.values())
            with tab_list[0]:
                # Takes the example files out once files of the user's own are in.
                self._ensure_fallback(key, upload.get("fallback"))
                options = self._input_file_options(key)
                if not options:
                    st.info(
                        "No files yet: add some "
                        + ("from UniProt, " if uniprot else "")
                        + "from your computer"
                        + (", from the cloud or from PRIDE." if pride
                           else " or from the cloud." if importing else ".")
                    )
                else:
                    paths = {Path(o).name: o for o in options}
                    files_dir = Path(self.workflow_dir, "input-files", key).resolve()
                    shown = [
                        n if Path(p).resolve().parent == files_dir else f"(local) {n}"
                        for n, p in paths.items()
                    ]
                    self._input_folders(
                        key, plain_name, shown, upload.get("suggest_folders", False),
                        select={
                            "widget": f"{self.parameter_manager.param_prefix}{key}",
                            "paths": paths,
                            "multiple": multiple,
                        },
                    )
                c1, c2 = st.columns(2)
                if c1.button(
                    "Done", type="primary", key=f"_browse-{key}-done",
                    use_container_width=True,
                ):
                    st.rerun()
                if options and c2.button(
                    "🗑️ Remove all files", key=f"_browse-{key}-clear",
                    use_container_width=True,
                    help="Takes the files out of the workspace; files on your "
                    "computer that were only referenced stay where they are.",
                ):
                    shutil.rmtree(Path(self.workflow_dir, "input-files", key), ignore_errors=True)
                    save_folders(self.workflow_dir, key, {})
                    st.session_state.pop(f"{self.parameter_manager.param_prefix}{key}", None)
                    self.params.pop(key, None)
                    self.parameter_manager.save_parameters()
                    st.rerun(scope="fragment")
            # The upload widget fills self.upload_targets, so it is drawn
            # first and the import tabs route files by it.
            self.upload_targets = {}
            with tabs["💻 Data on your computer"]:
                # Unwrapped from its fragment: adding files reruns the whole
                # dialog, so "Your files" lists them at once.
                StreamlitUI.upload_widget.__wrapped__(
                    self, key, name=plain_name, list_files=False,
                    **{k: v for k, v in upload.items() if k not in ("name", "uniprot")},
                )
            if importing:
                with tabs["☁️ Cloud data"]:
                    data_import_ui.link_import_section(
                        self.workflow_dir, self.upload_targets, source=data_import_ui.LINK
                    )
            if pride:
                with tabs["🧬 Import from PRIDE"]:
                    data_import_ui.link_import_section(
                        self.workflow_dir, self.upload_targets, source=data_import_ui.PRIDE
                    )
            if uniprot:
                with tabs["🔎 Import from UniProt proteome"]:
                    # Downloads into this upload folder and selects the file.
                    self.uniprot_proteome_download(key, plain_name)

        browse()

    def _resolve_browser_cwd(self, key: str, mount_root: Path) -> Path:
        """Read cwd for this widget from session state, confine it to mount_root."""
        sess_key = f"mounted_cwd_{key}"
        raw = st.session_state.get(sess_key, str(mount_root))
        try:
            cwd = Path(raw).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            cwd = mount_root
        if cwd != mount_root and mount_root not in cwd.parents:
            cwd = mount_root
        st.session_state[sess_key] = str(cwd)
        return cwd

    def _mounted_drive_browser(
        self,
        key: str,
        name: str,
        file_types: List[str],
        files_dir: Path,
        mount_root: Path,
    ) -> None:
        """Render a tree browser for a mounted host directory.

        Selected files are referenced in place via ``external_files.txt`` —
        the same mechanism the offline tkinter flow uses.
        """
        external_files = Path(files_dir, "external_files.txt")
        if not external_files.exists():
            external_files.touch()

        cwd = self._resolve_browser_cwd(key, mount_root)
        sess_cwd_key = f"mounted_cwd_{key}"

        st.markdown(
            """
            <style>
            div[data-testid="stButton"] button[kind="tertiary"] {
                padding-top: 0.15rem;
                padding-bottom: 0.15rem;
                min-height: 0;
                line-height: 1.3;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown(
                f"**Add {name} files from mounted directory** "
                f"`{mount_root}`"
            )

            # Breadcrumbs: compact tertiary buttons separated by »,
            # with a right-aligned Parent button.
            try:
                rel = cwd.relative_to(mount_root)
                segments = [mount_root.name] + list(rel.parts) if rel.parts else [mount_root.name]
            except ValueError:
                segments = [mount_root.name]
            n = len(segments)
            ratios: List[float] = []
            for i in range(n):
                ratios.append(max(len(segments[i]), 3))
                if i < n - 1:
                    ratios.append(1)
            ratios.append(20)  # flexible spacer
            ratios.append(6)   # parent button slot
            crumb_cols = st.columns(ratios, vertical_alignment="center")
            col_idx = 0
            for i, seg in enumerate(segments):
                target = mount_root.joinpath(*segments[1 : i + 1]) if i > 0 else mount_root
                if crumb_cols[col_idx].button(
                    seg,
                    key=f"crumb_{key}_{i}",
                    type="tertiary",
                ):
                    st.session_state[sess_cwd_key] = str(target)
                    st.rerun(scope="fragment")
                col_idx += 1
                if i < n - 1:
                    crumb_cols[col_idx].markdown(
                        "<span style='color:#888'>»</span>",
                        unsafe_allow_html=True,
                    )
                    col_idx += 1
            # spacer column
            col_idx += 1
            if cwd != mount_root:
                if crumb_cols[col_idx].button(
                    "⬆ Parent",
                    key=f"mounted_parent_{key}",
                    type="tertiary",
                ):
                    st.session_state[sess_cwd_key] = str(cwd.parent)
                    st.rerun(scope="fragment")

            try:
                entries = sorted(
                    (p for p in cwd.iterdir() if not p.name.startswith(".")),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except PermissionError:
                st.error(f"Permission denied reading `{cwd}`.")
                return

            def _is_match(p: Path) -> bool:
                return has_type(p, file_types)

            subdirs = [p for p in entries if p.is_dir() and not _is_match(p)]
            bundled = [p for p in entries if p.is_dir() and _is_match(p)]
            files = [p for p in entries if p.is_file() and _is_match(p)]

            for d in subdirs:
                indent, body = st.columns([1, 60], vertical_alignment="center")
                if body.button(
                    f"📂 {d.name}/",
                    key=f"mounted_dir_{key}_{d.name}",
                    type="tertiary",
                ):
                    st.session_state[sess_cwd_key] = str(d)
                    st.rerun(scope="fragment")

            selectable = bundled + files
            selected_paths: List[str] = []
            for f in selectable:
                cb_key = f"mounted_pick_{key}_{f}"
                size_label = ""
                if f.is_file():
                    try:
                        size_mb = f.stat().st_size / (1024 * 1024)
                        size_label = f"  ·  {size_mb:.1f} MB"
                    except OSError:
                        pass
                icon = "🗂️" if f.is_dir() else "📄"
                if st.checkbox(
                    f"{icon} {f.name}{size_label}",
                    key=cb_key,
                ):
                    selected_paths.append(str(f))

            if not subdirs and not selectable:
                st.info(
                    f"No subdirectories or files matching "
                    f"**{', '.join('.' + ft for ft in file_types)}** here."
                )

            count = len(selected_paths)
            if st.button(
                f"➕ Add {count} selected {name} file(s)" if count else f"➕ Add selected {name} file(s)",
                key=f"mounted_add_{key}",
                type="primary",
                use_container_width=True,
                disabled=count == 0,
            ):
                existing = set(
                    line.strip()
                    for line in external_files.read_text().splitlines()
                    if line.strip()
                )
                added = 0
                with open(external_files, "a") as fh:
                    for p in selected_paths:
                        if p not in existing:
                            fh.write(f"{p}\n")
                            existing.add(p)
                            added += 1
                # Clear the checkboxes by removing their session keys.
                for f in selectable:
                    st.session_state.pop(f"mounted_pick_{key}_{f}", None)
                st.success(f"Added {added} file(s) from `{cwd}`.")
                st.rerun(scope="fragment")

    def uniprot_proteome_download(self, key: str, name: str = "") -> None:
        """Search UniProt proteomes by organism name or taxonomy ID and download
        the chosen one (reviewed entries only, or all of them) as FASTA into the
        folder of ``upload_widget(key)``, as the selected file of
        ``select_input_file(key)``. Call it below that ``upload_widget``.
        """
        from src.workflow.uniprot_ui import proteome_download

        proteome_download(self, key, name)

    def select_protein_database(
        self, key: str, name: str = "Protein database", reactive: bool = False
    ) -> None:
        """Choose a protein database on a configure page: one of the files of
        ``upload_widget(key)`` (``select_input_file``), or a UniProt proteome
        searched and downloaded right here into that upload folder. Either way
        the selection is ``self.params[key]``.
        """
        from src.workflow.uniprot_ui import database_choice

        database_choice(self, key, name, reactive)

    def select_input_file(
        self,
        key: str,
        name: str = "",
        multiple: bool = False,
        display_file_path: bool = False,
        reactive: bool = False,
        upload: dict = None,
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
            upload (dict, optional): Arguments of ``upload_widget()`` for this
                key (``file_types``, ``fallback``, ``suggest_folders``). Adds a
                **Browse** button that opens the files by folder, to select
                them and add new ones (upload and import from a link) in one
                place, so the workflow needs no upload page of its own. The
                ``fallback`` files are used while none are added. With
                ``uniprot=True`` (a protein database) the dialog also searches
                UniProt proteomes and downloads one as the selected file.
        """
        if reactive:
            self._select_input_file_impl(key, name, multiple, display_file_path, reactive, upload)
        else:
            self._select_input_file_fragmented(key, name, multiple, display_file_path, reactive, upload)

    @st.fragment
    def _select_input_file_fragmented(self, key, name, multiple, display_file_path, reactive, upload=None):
        self._select_input_file_impl(key, name, multiple, display_file_path, reactive, upload)

    def _input_file_options(self, key: str) -> List[str]:
        """Paths of the files of upload ``key``: copied ones and existing referenced ones."""
        path = Path(self.workflow_dir, "input-files", key)
        if not path.exists():
            return []
        options = sorted(
            str(f) for f in path.iterdir() if "external_files.txt" not in str(f)
        )
        external_files = Path(path, "external_files.txt")
        if external_files.exists():
            with open(external_files, "r") as f:
                external_files_list = f.read().splitlines()
            # Only make files available that still exist
            options += [f for f in external_files_list if f and os.path.exists(f)]
        return options

    def _ensure_fallback(self, key: str, fallback) -> None:
        """Copy the example files of upload ``key`` while it has no files of
        its own, and take the copies out again once it has."""
        if not fallback:
            return
        files_dir = Path(self.workflow_dir, "input-files", key)
        examples = {
            Path(f).name: Path(f)
            for f in ([fallback] if isinstance(fallback, str) else fallback)
            if Path(f).exists()
        }

        def is_copy(path) -> bool:
            path = Path(path)
            example = examples.get(path.name)
            return (
                example is not None
                and path.parent.resolve() == files_dir.resolve()
                and path.resolve() != example.resolve()
                and filecmp.cmp(path, example, shallow=False)
            )

        options = self._input_file_options(key)
        copies = [o for o in options if is_copy(o)]
        if len(copies) < len(options):
            # Files of the user's own: the examples are no longer needed.
            for c in copies:
                Path(c).unlink(missing_ok=True)
            return
        if options:
            return
        files_dir.mkdir(parents=True, exist_ok=True)
        for example in examples.values():
            if not Path(files_dir, example.name).exists():
                shutil.copy(example, Path(files_dir, example.name))
        self._fallback_folders(key, fallback)

    def _fallback_folders(self, key: str, fallback) -> None:
        """Put the example files of upload ``key`` in the folders a ``fallback``
        dict names (file -> folder); files already in a folder stay there."""
        if not isinstance(fallback, dict):
            return
        named = {Path(f).name: d for f, d in fallback.items() if d}
        if not named:
            return
        folders = load_folders(self.workflow_dir, key)
        missing = {n: d for n, d in named.items() if n not in folders}
        if missing:
            save_folders(self.workflow_dir, key, {**folders, **missing})

    def _select_input_file_impl(self, key, name, multiple, display_file_path, reactive, upload=None):
        """Internal implementation of select_input_file - contains all the widget logic."""
        if not name:
            name = f"**{key}**"
        if upload is not None:
            self._ensure_fallback(key, upload.get("fallback"))
        options = self._input_file_options(key)
        widget = f"{self.parameter_manager.param_prefix}{key}"
        pending = f"_pending-{widget}"
        if pending in st.session_state:  # chosen in the Browse pop-out
            value = st.session_state.pop(pending)
            st.session_state[widget] = (
                [v for v in value if v in options] if multiple
                else (value if value in options else (options[0] if options else None))
            )
            self.params[key] = st.session_state[widget]
        if upload is None and not Path(self.workflow_dir, "input-files", key).exists():
            st.warning(f"No **{name}** files!")
            return
        if (key in self.params.keys()) and isinstance(self.params[key], list):
            self.params[key] = [f for f in self.params[key] if f in options]
        if upload is not None:
            # A selected file can be gone (an example replaced by own files).
            current = st.session_state.get(widget)
            if isinstance(current, list):
                st.session_state[widget] = [f for f in current if f in options]
            elif current is not None and current not in options:
                del st.session_state[widget]

        widget_type = "multiselect" if multiple else "selectbox"
        if multiple:
            self._select_by_folder(key, options)
        if upload is None:
            self.input_widget(
                key,
                name=name,
                widget_type=widget_type,
                options=options,
                display_file_path=display_file_path,
                reactive=reactive,
            )
            return
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        with c1:
            if options:
                self.input_widget(
                    key,
                    name=name,
                    widget_type=widget_type,
                    options=options,
                    display_file_path=display_file_path,
                    reactive=reactive,
                )
            else:
                st.markdown(name)
                st.caption(f"No {name.replace('*', '')} files yet: add them with **Browse**.")
        if c2.button(
            "📂 Browse",
            key=f"_browse-{key}",
            use_container_width=True,
            help="Your files by folder: choose which to use, sort them into "
            "folders and add new ones.",
        ):
            self._browse_input_files(key, name, multiple, upload)

    def _select_by_folder(self, key: str, options: List[str]) -> None:
        """Buttons that select the files of one folder (see ``upload_widget``)."""
        folders = load_folders(self.workflow_dir, key)
        counts = folder_counts(folders, options)
        if not counts:
            return
        widget = f"{self.parameter_manager.param_prefix}{key}"
        pill_key = f"_select-folder-{Path(self.workflow_dir).name}-{key}"
        all_label = f"All files ({len(options)})"
        labels = {all_label: None}
        labels.update({f"📁 {d} ({n})": d for d, n in counts.items()})

        def select():
            label = st.session_state.get(pill_key)
            if label not in labels:
                return
            folder = labels[label]
            st.session_state[widget] = [
                f for f in options
                if folder is None or folders.get(Path(f).name) == folder
            ]
            st.session_state[pill_key] = None

        st.pills(
            "Select a folder",
            list(labels),
            key=pill_key,
            on_change=select,
            help="Selects the files of that folder, replacing the current selection.",
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

        # Streamlit ignores a widget's initial-value argument (value=/default=/index=)
        # once that key already exists in session state -- but on Streamlit < 1.50 the
        # argument is still hashed into the widget's element id. Since this method feeds
        # the persisted parameter straight back in as that argument, the id changed on
        # every interaction, the following interaction arrived under the now-stale id and
        # was silently dropped: selecting six mzML files kept only three. Passing the
        # argument on the first render only is not enough either: the id still changes
        # once, between that render and the next, and the next rerun of the enclosing
        # fragment resets the widget to empty -- a selection restored from params.json
        # was wiped (and saved as empty) by the first reactive rerun of configure().
        # So the argument is never passed: the first render writes the value into
        # session state, which then owns it, and the id never changes.
        def seed(initial: Any) -> dict:
            if key not in st.session_state:
                st.session_state[key] = initial
            return {}

        if widget_type == "text":
            st.text_input(name, key=key, help=help, on_change=on_change, **seed(value))

        elif widget_type == "textarea":
            st.text_area(name, key=key, help=help, on_change=on_change, **seed(value))

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
                step=step_size,
                # "%g" keeps every decimal the user types; Streamlit's float
                # default "%0.2f" rounds to two.
                format="%g" if number_type is float else None,
                key=key,
                help=help,
                on_change=on_change,
                **seed(value),
            )

        elif widget_type == "checkbox":
            st.checkbox(name, key=key, help=help, on_change=on_change, **seed(value))

        elif widget_type == "selectbox":
            if options is not None:
                st.selectbox(
                    name,
                    options=options,
                    key=key,
                    format_func=format_files,
                    help=help,
                    on_change=on_change,
                    **seed(value if value in options else (options[0] if options else None)),
                )
            else:
                st.warning(f"Select widget '{name}' requires options parameter")

        elif widget_type == "multiselect":
            if options is not None:
                st.multiselect(
                    name,
                    options=options,
                    key=key,
                    format_func=format_files,
                    help=help,
                    on_change=on_change,
                    # A saved value that is no longer an option (a deleted
                    # file, a renamed choice) is dropped; Streamlit raises on it.
                    **seed([v for v in (value or []) if v in options]),
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
                    step=step_size,
                    key=key,
                    format=None,
                    help=help,
                    on_change=on_change,
                    **seed(value),
                )
            else:
                st.warning(
                    f"Slider widget '{name}' requires min_value and max_value parameters"
                )

        elif widget_type == "password":
            st.text_input(name, type="password", key=key, help=help, on_change=on_change, **seed(value))

        elif widget_type == "auto":
            # Auto-determine widget type based on value
            if isinstance(value, bool):
                st.checkbox(name, key=key, help=help, on_change=on_change, **seed(value))
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

    def input_TOPP(
        self,
        topp_tool_name: str,
        num_cols: int = 4,
        exclude_parameters: List[str] = [],
        include_parameters: List[str] = [],
        flag_parameters: List[str] = [],
        display_tool_name: bool = True,
        display_subsections: bool = True,
        display_subsection_tabs: bool = False,
        custom_defaults: dict = {},
        tool_instance_name: str = None,
        reactive: bool = False,
        advanced_parameters: List[str] = [],
    ) -> None:
        """
        Generates input widgets for TOPP tool parameters dynamically based on the tool's
        .ini file. Supports excluding specific parameters and adjusting the layout.
        File input and output parameters are excluded.

        Args:
            topp_tool_name (str): The name of the TOPP tool for which to generate inputs.
            num_cols (int, optional): Number of columns to use for the layout. Defaults to 3.
            exclude_parameters (List[str], optional): List of parameter names to exclude from the widget. A name ending in ":" excludes that whole top-level section (e.g. "fd:"). Defaults to an empty list.
            include_parameters (List[str], optional): List of parameter names to include in the widget. Defaults to an empty list.
            flag_parameters (List[str], optional): List of parameter names that should
                be treated as no-value CLI flags during command construction.
            display_tool_name (bool, optional): Whether to display the TOPP tool name. Defaults to True.
            display_subsections (bool, optional): Whether to split parameters into subsections based on the prefix. Defaults to True.
            display_subsection_tabs (bool, optional): Whether to display main subsections in separate tabs (if more than one main section). Defaults to False.
            custom_defaults (dict, optional): Dictionary of custom defaults to use. Defaults to an empty dict.
            tool_instance_name (str, optional): A unique instance name for this tool
                invocation. Allows multiple instances of the same TOPP tool with
                independent parameters (e.g., two IDFilter calls). If not provided,
                defaults to topp_tool_name. The instance name is used for session
                state keys and parameter storage, while topp_tool_name is used for
                the actual tool executable and ini file creation.
            reactive (bool, optional): If True, widget changes trigger the parent
                section to re-render, enabling conditional UI based on this widget's
                value. Use when downstream UI depends on a parameter value (e.g.,
                TMT type driving channel count). Default is False.
            advanced_parameters (List[str], optional): Parameters to treat as
                advanced although the tool does not tag them so: they are left
                off the page and reached through the "All parameters" dialog,
                like the tool's own advanced ones (e.g. output options). A name
                ending in ":" matches a whole top-level section.
        """
        if reactive:
            self._input_TOPP_impl(
                topp_tool_name, num_cols, exclude_parameters, include_parameters,
                flag_parameters, display_tool_name, display_subsections,
                display_subsection_tabs, custom_defaults, tool_instance_name,
                advanced_parameters,
            )
        else:
            self._input_TOPP_fragmented(
                topp_tool_name, num_cols, exclude_parameters, include_parameters,
                flag_parameters, display_tool_name, display_subsections,
                display_subsection_tabs, custom_defaults, tool_instance_name,
                advanced_parameters,
            )

    @st.fragment
    def _input_TOPP_fragmented(
        self,
        topp_tool_name: str,
        num_cols: int = 4,
        exclude_parameters: List[str] = [],
        include_parameters: List[str] = [],
        flag_parameters: List[str] = [],
        display_tool_name: bool = True,
        display_subsections: bool = True,
        display_subsection_tabs: bool = False,
        custom_defaults: dict = {},
        tool_instance_name: str = None,
        advanced_parameters: List[str] = [],
    ) -> None:
        self._input_TOPP_impl(
            topp_tool_name, num_cols, exclude_parameters, include_parameters,
            flag_parameters, display_tool_name, display_subsections,
            display_subsection_tabs, custom_defaults, tool_instance_name,
            advanced_parameters,
        )

    def _read_params_for_update(self, tool_instance_name: str) -> dict:
        """
        Strict read of params.json for the read-modify-write-back sites below.

        Both callers merge into what they read and write the result straight
        back, so a tolerant empty dict from an unreadable file would be written
        over everything stored - erasing `_defaults`, `_flag_params` and every
        other tool's values while looking like a successful save.
        read_parameters_strict() raises instead, and here that raise becomes a
        halt: the write is skipped entirely, so the file on disk is preserved
        for inspection and can still be repaired by hand, or reset from the
        button rendered below.

        Args:
            tool_instance_name (str): Instance currently being rendered, used to
                keep the reset button key unique across tool fragments.

        Returns:
            dict: Stored parameters, or an empty dict for an absent file.

        Does not return if the file exists but cannot be read.
        """
        try:
            return self.parameter_manager.read_parameters_strict()
        except TransientParameterFileError as e:
            # Ordered before InvalidParameterFileError, of which this is a
            # subclass. The storage is not answering; the file itself is most
            # likely intact, so deliberately no reset affordance here - a reset
            # during a Ganesha restart is what would actually destroy it.
            st.error(
                f"**ERROR**: {e} Nothing was written, so no stored parameters "
                "were lost. This usually clears by itself, reload the page in "
                "a moment."
            )
            st.stop()
            # st.stop() raises, so this is only reached when Streamlit is
            # stubbed out; re-raise rather than fall through to the write.
            raise
        except InvalidParameterFileError as e:
            st.error(
                f"**ERROR**: {e} Nothing was written, so no stored parameters "
                "were lost. Repair the file, or reset to defaults to continue."
            )
            if st.button(
                "⚠️ Reset parameters to defaults",
                help="Move the unreadable parameter file aside and start over from the default parameters.",
                key=f"reset_unreadable_params_{tool_instance_name}",
            ):
                try:
                    backup = self.parameter_manager.reset_to_default_parameters()
                except OSError as reset_error:
                    # Without this the button itself raises and the page stops
                    # again on the next render, with no remaining way out.
                    st.error(
                        f"**ERROR**: Could not move "
                        f"{self.parameter_manager.params_file} aside: "
                        f"{reset_error}"
                    )
                else:
                    self.parameter_manager.clear_parameter_session_state()
                    st.toast(
                        f"Parameters reset to defaults, previous file kept as {backup.name}"
                        if backup is not None
                        else "Parameters reset to defaults"
                    )
                    # Every tool section is affected, not just this fragment.
                    st.rerun(scope="app")
            st.stop()
            # st.stop() raises, so this is only reached when Streamlit is
            # stubbed out; re-raise rather than fall through to the write.
            raise

    def _topp_tool_unavailable(self, topp_tool_name: str) -> None:
        """Say why a TOPP tool's parameters cannot be shown: missing, or failing."""
        from src.workflow.ParameterManager import INI_TOOL_MISSING

        reason = getattr(self.parameter_manager, "ini_errors", {}).get(
            topp_tool_name, INI_TOOL_MISSING
        )
        if reason == INI_TOOL_MISSING:
            st.error(
                f"TOPP tool **'{topp_tool_name}'** not found. The OpenMS TOPP "
                "tools are not installed here, or not on the PATH of this app."
            )
            return
        st.error(
            f"TOPP tool **'{topp_tool_name}'** is installed but could not "
            "write its parameters, so they cannot be shown."
        )
        with st.expander("Tool output"):
            st.code(reason, language=None)

    def _input_TOPP_impl(
        self,
        topp_tool_name: str,
        num_cols: int = 4,
        exclude_parameters: List[str] = [],
        include_parameters: List[str] = [],
        flag_parameters: List[str] = [],
        display_tool_name: bool = True,
        display_subsections: bool = True,
        display_subsection_tabs: bool = False,
        custom_defaults: dict = {},
        tool_instance_name: str = None,
        advanced_parameters: List[str] = [],
    ) -> None:
        """Internal implementation of input_TOPP - contains all the widget logic."""
        # Default instance name to the tool name when not provided
        if tool_instance_name is None:
            tool_instance_name = topp_tool_name

        # Register instance-name → real-tool-name mapping in session state
        if "_topp_tool_instance_map" not in st.session_state:
            st.session_state["_topp_tool_instance_map"] = {}
        st.session_state["_topp_tool_instance_map"][tool_instance_name] = topp_tool_name

        # Persist flag_parameters to session_state and params.json so run_topp
        # can skip appending a value for these boolean CLI flags.
        if "_topp_flag_params" not in st.session_state:
            st.session_state["_topp_flag_params"] = {}
        st.session_state["_topp_flag_params"][tool_instance_name] = list(flag_parameters)
        _fp = self._read_params_for_update(tool_instance_name)
        if "_flag_params" not in _fp:
            _fp["_flag_params"] = {}
        _fp["_flag_params"][tool_instance_name] = list(flag_parameters)
        # Atomic: a truncate-then-rewrite interrupted here leaves a torn
        # params.json which every later strict read rejects, wedging this very
        # method on each render.
        self.parameter_manager.write_parameters(_fp)

        if not display_subsections:
            display_subsection_tabs = False
        if display_subsection_tabs:
            display_subsections = True

        # Create pristine ini file (never mutated with custom defaults)
        ini_file_path = Path(self.parameter_manager.ini_dir, f"{topp_tool_name}.ini")
        if not self.parameter_manager.create_ini(topp_tool_name):
            self._topp_tool_unavailable(topp_tool_name)
            return

        # Seed custom defaults into params.json under _defaults key
        if custom_defaults:
            params = self._read_params_for_update(tool_instance_name)
            if "_defaults" not in params:
                params["_defaults"] = {}
            params["_defaults"][tool_instance_name] = custom_defaults
            self.parameter_manager.write_parameters(params)
            # Refresh self.params so widget resolution sees _defaults - reuse
            # what was just written instead of reading the file back, which
            # could be torn by a concurrent writer.
            self.params = params

        # read into Param object
        param = poms.Param()
        poms.ParamXMLFile().load(str(ini_file_path), param)


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
                "input file" in _tags(param, key)
                or "output file" in _tags(param, key)
                or any([_matches_topp_parameter(k, key) for k in excluded_keys])
            )
        ]

        # Track which keys are "included" (shown by default) vs "non-included" (advanced only)
        if include_parameters:
            included_keys = {
                key for key in valid_keys
                if any([_matches_topp_parameter(k, key) for k in include_parameters])
            }
        else:
            included_keys = set(valid_keys)  # All are included when no filter specified
        params = []
        for key in valid_keys:
            entry = param.getEntry(key)
            friendly = _display_name(
                topp_tool_name, _txt(key).split(":1:", 1)[-1], tool_instance_name
            )
            p = {
                "name": _txt(entry.name),
                "friendly": friendly,
                "key": key,
                "value": entry.value,
                "original_is_list": isinstance(entry.value, list),
                "valid_strings": _valid_strings(entry),
                "description": _txt(entry.description),
                "advanced": (
                    "advanced" in _tags(param, key)
                    or any(_matches_topp_parameter(k, key) for k in advanced_parameters)
                ),
                "non_included": key not in included_keys,
                "section_description": param.getSectionDescription(
                    ":".join(_txt(key).split(":")[:-1])
                ),
            }
            # Parameter sections and subsections as string (e.g. "section:subsection")
            if display_subsections:
                p["sections"] = ":".join(
                    _txt(p["key"]).split(":1:")[1].split(":")[:-1]
                )
            params.append(p)

        # Build ini_params dict for three-layer merge
        ini_params = {}
        for p in params:
            name = _txt(p["key"]).split(":1:")[1]
            ini_params[name] = p["value"]

        # Resolve effective values: ini < _defaults < user overrides
        merged = self.parameter_manager.get_merged_params(tool_instance_name, ini_params=ini_params)
        for p in params:
            name = _txt(p["key"]).split(":1:")[1]
            if name in merged:
                p["value"] = merged[name]
            # Ensure list parameters stay as lists after loading from JSON
            # (JSON may store single-item lists as strings)
            if p["original_is_list"] and isinstance(p["value"], str):
                p["value"] = p["value"].split("\n") if p["value"] else []

        # Apps may still set st.session_state["advanced"] to show every parameter
        # on the page; the template itself has no toggle for it any more.
        show_advanced = bool(st.session_state.get("advanced", False))

        # Split into subsections if required
        param_sections = {}
        section_descriptions = {}
        if display_subsections:
            for p in params:
                # Advanced and non-included parameters are reached through the
                # "All parameters" dialog, unless an app turns them on
                if not show_advanced and (p["advanced"] or p["non_included"]):
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
            # Advanced and non-included parameters are in the dialog only
            param_sections["all"] = [
                p for p in params
                if show_advanced or (not p["advanced"] and not p["non_included"])
            ]

        # Values changed in the "All parameters" dialog, before the widgets are drawn
        self._apply_all_params_pending(tool_instance_name)

        # Tool name, and the button for the "All parameters" dialog
        all_rows = self._all_parameter_rows(params, ini_params, tool_instance_name)
        name_col, all_col = st.columns([3, 2], vertical_alignment="bottom")
        if display_tool_name:
            name_col.markdown(f"**{tool_instance_name}**")
        n_changed = sum(not r["is_default"] for r in all_rows)
        if all_col.button(
            f"All {len(all_rows)} parameters"
            + (f" ({n_changed} changed)" if n_changed else ""),
            key=f"all-params-{tool_instance_name}",
            icon=":material/tune:",
            type="tertiary",
            help="The page shows the common parameters. Search every parameter "
            "of this tool here, including advanced ones, change them, and reset "
            "single parameters to the default or the applied preset.",
            use_container_width=True,
        ):
            st.session_state["_all_params_filter"] = ""
            st.dialog(f"All parameters of {tool_instance_name}", width="large")(
                self._all_parameters_dialog
            )(topp_tool_name, tool_instance_name, exclude_parameters)

        tab_names = [k for k in param_sections.keys() if ":" not in k]
        tabs = None
        if tab_names and display_subsection_tabs:
            tabs = st.tabs([k for k in param_sections.keys() if ":" not in k])

        # Show input widgets
        def show_subsection_header(section: str, display_subsections: bool):
            # Display section name and help text (section description) if required
            if section and display_subsections:
                description = section_descriptions.get(section)
                friendly = _display_name(topp_tool_name, section, tool_instance_name)
                if friendly:
                    # The app's own heading; the help keeps the tool's name
                    st.markdown(
                        f"**{friendly['name']}**",
                        help=(friendly["help"] or description or "")
                        + f"\n\nSection `{section}` of {topp_tool_name}.",
                    )
                    return
                parts = section.split(":")
                st.markdown(
                    ":".join(parts[:-1])
                    + (":" if len(parts) > 1 else "")
                    + f"**{parts[-1]}**",
                    help=description,
                )

        def display_TOPP_params(params: dict, num_cols):
            """Displays individual TOPP parameters in given number of columns"""

            def is_text_area(p):
                value = p["value"]
                if isinstance(value, str) and "\n" in value:
                    return True
                return isinstance(value, list) and not p["valid_strings"]

            # Free-text lists (multi-line text areas) come after the other
            # inputs of a section, so every row holds inputs of one height and
            # they can line up at the bottom: a label that wraps onto a second
            # line no longer pushes its input below its neighbours'.
            text_areas = [p for p in params if is_text_area(p)]
            params = [p for p in params if not is_text_area(p)] + text_areas

            def new_row():
                return st.columns(num_cols, vertical_alignment="bottom")

            cols = new_row()
            i = 0
            for p in params:
                if i and text_areas and p is text_areas[0]:
                    # The text areas start a row of their own
                    i = 0
                    cols = new_row()
                # get key and name – use tool_instance_name in session state key
                key_str = _txt(p['key'])
                if tool_instance_name != topp_tool_name:
                    key_str = key_str.replace(f"{topp_tool_name}:1:", f"{tool_instance_name}:1:", 1)
                key = f"{self.parameter_manager.topp_param_prefix}{key_str}"
                name = p["name"]
                if p.get("friendly"):
                    # The app's own name for it; the help keeps the tool's
                    # name, which logs, presets and the tool's docs use.
                    name = p["friendly"]["name"]
                    p["description"] = (
                        (p["friendly"]["help"] or p["description"])
                        + f"\n\nParameter `{_txt(p['key']).split(':1:', 1)[-1]}`"
                        + f" of {topp_tool_name}."
                    )
                try:
                    # sometimes strings with newline, handle as list
                    if isinstance(p["value"], str) and "\n" in p["value"]:
                        p["value"] = p["value"].split("\n")
                    # bools
                    if isinstance(p["value"], bool):
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
                        value = float(p["value"])
                        # Streamlit's default "%0.2f" rounds what the user
                        # types to two decimals, which makes tolerances such as
                        # 0.015 Da impossible to enter. "%g" shows the value as
                        # typed, and small defaults step in their own decade.
                        step = (
                            10.0 ** math.floor(math.log10(abs(value)))
                            if 0 < abs(value) < 1
                            else 1.0
                        )
                        cols[i].number_input(
                            name,
                            value=value,
                            step=step,
                            format="%g",
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
                        cols = new_row()
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
            

    def _apply_all_params_pending(self, tool_instance_name: str) -> None:
        """Give this tool's widgets the values set in the "All parameters" dialog."""
        pending = st.session_state.get("_all_params_pending")
        if not pending:
            return
        prefix = f"{self.parameter_manager.topp_param_prefix}{tool_instance_name}:1:"
        for key in [k for k in pending if k.startswith(prefix)]:
            st.session_state[key] = pending.pop(key)

    def _all_parameter_rows(
        self, params: list, ini_params: dict, tool_instance_name: str
    ) -> list:
        """One row per parameter of a TOPP tool for the "All parameters" dialog."""
        stored = self.parameter_manager.get_parameters_from_json()
        custom = stored.get("_defaults", {}).get(tool_instance_name, {})
        rows = []
        for p in params:
            name = _txt(p["key"]).split(":1:")[1]
            value = p["value"]
            if isinstance(value, list):
                value = [v.decode() if isinstance(v, bytes) else v for v in value]
            default = custom.get(name, ini_params.get(name))
            if isinstance(default, list):
                default = [v.decode() if isinstance(v, bytes) else v for v in default]
            rows.append(
                {
                    "name": name,
                    "label": p["name"],
                    "section": ":".join(name.split(":")[:-1]),
                    "description": p["description"],
                    "value": value,
                    "default": default,
                    "valid_strings": p["valid_strings"],
                    "is_list": p["original_is_list"],
                    "advanced": p["advanced"],
                    "is_default": ParameterManager._same_value(value, default),
                }
            )
        return rows

    def _all_parameters_dialog(
        self, topp_tool_name: str, tool_instance_name: str, exclude_parameters: list
    ) -> None:
        """Every parameter of a TOPP tool: filter, edit, reset to default or preset.

        Changes go straight to params.json (ParameterManager.set_topp_parameter),
        under their own widget keys, because the tool's widgets on the page are
        drawn in the same run and can not share theirs.
        """
        pm = self.parameter_manager
        ini_path = Path(pm.ini_dir, f"{topp_tool_name}.ini")
        param = poms.Param()
        poms.ParamXMLFile().load(str(ini_path), param)
        stored = pm.get_parameters_from_json()
        user = stored.get(tool_instance_name, {})
        defaults = pm.get_topp_defaults(topp_tool_name, tool_instance_name)

        # The same parameters the page offers: no file parameters, no standard flags
        excluded = [
            "log", "debug", "threads", "no_progress", "force", "version", "test"
        ] + list(exclude_parameters)
        rows = []
        for key in param.keys():
            tags = _tags(param, key)
            if "input file" in tags or "output file" in tags:
                continue
            if any(_matches_topp_parameter(k, key) for k in excluded):
                continue
            entry = param.getEntry(key)
            name = _txt(key).split(":1:")[1]
            friendly = _display_name(topp_tool_name, name, tool_instance_name)
            default = defaults.get(name, entry.value)
            value = user.get(name, default)
            if isinstance(entry.value, list):
                # pyOpenMS gives list items as bytes, and params.json or
                # custom_defaults can hold a list as newline-separated text
                default, value = _as_str_list(default), _as_str_list(value)
            rows.append(
                {
                    "name": name,
                    "label": friendly["name"] if friendly else _txt(entry.name),
                    "friendly": bool(friendly),
                    "section": ":".join(name.split(":")[:-1]),
                    "description": (
                        (friendly["help"] or _txt(entry.description))
                        if friendly
                        else _txt(entry.description)
                    ),
                    "tool_description": _txt(entry.description),
                    "value": value,
                    "default": default,
                    "valid_strings": _valid_strings(entry),
                    "advanced": "advanced" in tags,
                    "is_list": isinstance(entry.value, list),
                }
            )

        preset_name, preset_values, preset_complete = pm.applied_preset_values(
            tool_instance_name
        )

        def preset_value(row):
            if row["name"] in preset_values:
                return True, preset_values[row["name"]]
            if preset_complete:
                return True, row["default"]
            return False, None

        def same(a, b):
            return ParameterManager._same_value(_plain(a), _plain(b))

        n_changed = sum(not same(r["value"], r["default"]) for r in rows)
        off_preset = [
            r for r in rows if preset_value(r)[0] and not same(r["value"], preset_value(r)[1])
        ]

        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        query = c1.text_input(
            "Filter",
            key="_all_params_filter",
            placeholder="Filter by name, section or description, e.g. tolerance",
            label_visibility="collapsed",
        )
        only_changed = c2.toggle("Changed only", key=f"_all_params_changed_{tool_instance_name}")
        summary = f"{len(rows)} parameters, {n_changed} changed from the default"
        if preset_name:
            summary += (
                f" · preset **{preset_name}**: "
                + (f"{len(off_preset)} differ" if off_preset else "all as in the preset")
            )
        st.caption(summary)

        words = query.lower().split()
        shown = [
            r
            for r in rows
            if all(
                w
                in f"{r['label']} {r['name']} {r['description']} {r['tool_description']}".lower()
                for w in words
            )
            and (not only_changed or not same(r["value"], r["default"]))
        ]
        if not shown:
            st.info("No parameter matches the filter.")

        with st.container(height=520, border=False):
            for row in shown:
                self._all_parameters_row(
                    tool_instance_name, row, same, preset_name, preset_value(row)
                )

        if st.button("Done", type="primary", key="_all_params_done"):
            st.rerun()

    def _all_parameters_row(self, instance, row, same, preset_name, preset) -> None:
        """One parameter in the "All parameters" dialog: label, widget, reset buttons."""
        pm = self.parameter_manager
        wkey = f"_all_params_value_{instance}:{row['name']}"
        value, default = row["value"], row["default"]
        changed = not same(value, default)
        has_preset, preset_val = preset

        def show_on_page(r, new):
            # The tool's widgets on the page take the new value on the next
            # full run, before they are drawn (_apply_all_params_pending).
            # Setting their keys now would not stick: the browser sends their
            # old values with the next rerun, and save_parameters() would
            # write those back.
            main_key = f"{pm.topp_param_prefix}{instance}:1:{r['name']}"
            pending = st.session_state.setdefault("_all_params_pending", {})
            if r["is_list"]:
                items = new if isinstance(new, list) else [v for v in str(new).split("\n") if v]
                pending[main_key] = "\n".join(str(v) for v in items)
                if r["valid_strings"]:
                    pending[f"{main_key}_display"] = [
                        v for v in items if v in r["valid_strings"]
                    ]
            else:
                pending[main_key] = new

        def store(k=wkey, r=row):
            new = st.session_state[k]
            stored = new
            if isinstance(new, list):
                stored = "\n".join(str(v) for v in new)
            elif r["is_list"]:
                stored = "\n".join(line for line in str(new).splitlines() if line)
            if pm.set_topp_parameter(instance, r["name"], stored, default=_plain(r["default"])):
                show_on_page(r, stored)

        def as_widget_value(r, v):
            # What this row's widget holds (deleting its key instead would let
            # the browser send the old value back as a change).
            if r["is_list"]:
                items = v if isinstance(v, list) else [x for x in str(v).split("\n") if x]
                items = [x.decode() if isinstance(x, bytes) else str(x) for x in items]
                if r["valid_strings"]:
                    return [x for x in items if x in r["valid_strings"]]
                return "\n".join(items)
            if isinstance(r["default"], bool):
                return v if isinstance(v, bool) else str(v).lower() == "true"
            if isinstance(r["default"], float):
                return float(v)
            if isinstance(r["default"], int):
                return int(v)
            return v

        def reset(k=wkey, r=row):
            if pm.reset_topp_parameter(instance, r["name"]):
                show_on_page(r, r["default"])
                st.session_state[k] = as_widget_value(r, r["default"])

        def to_preset(k=wkey, r=row, v=preset_val):
            if pm.set_topp_parameter(instance, r["name"], _plain(v), default=_plain(r["default"])):
                show_on_page(r, v)
                st.session_state[k] = as_widget_value(r, v)

        c_label, c_value, c_actions = st.columns([5, 4, 3], vertical_alignment="center")
        marker = " :orange[●]" if changed else ""
        if row.get("friendly"):
            # The app's name first, the tool's own name beside it, so both
            # read the same as on the page and in the tool's documentation.
            c_label.markdown(
                f"**{row['label']}**{marker} :gray[· {row['name']}]"
                + (" :gray[· advanced]" if row["advanced"] else ""),
                help=row["description"] or None,
            )
        else:
            section = f":gray[{row['section']}:]" if row["section"] else ""
            c_label.markdown(
                f"{section}**{row['label']}**{marker}"
                + (" :gray[· advanced]" if row["advanced"] else ""),
                help=row["description"] or None,
            )
        if changed:
            c_label.caption(f"default: {_short(default)}")

        common = dict(key=wkey, label_visibility="collapsed", on_change=store)
        label = row["label"]
        if isinstance(default, bool):
            current = value if isinstance(value, bool) else str(value).lower() == "true"
            c_value.checkbox(label, value=current, **common)
        elif row["is_list"]:
            items = _as_str_list(value)
            if row["valid_strings"]:
                c_value.multiselect(
                    label,
                    options=sorted(row["valid_strings"]),
                    default=[v for v in items if v in row["valid_strings"]],
                    **common,
                )
            else:
                c_value.text_area(label, value="\n".join(items), height=68, **common)
        elif isinstance(default, str) and row["valid_strings"]:
            options = row["valid_strings"]
            c_value.selectbox(
                label,
                options=options,
                index=options.index(value) if value in options else 0,
                **common,
            )
        elif isinstance(default, int) and not isinstance(default, bool):
            c_value.number_input(label, value=int(value), step=1, **common)
        elif isinstance(default, float):
            c_value.number_input(label, value=float(value), format="%g", **common)
        else:
            c_value.text_input(label, value=str(value), **common)

        b1, b2 = c_actions.columns(2)
        if changed:
            b1.button(
                "Default",
                key=f"_all_params_reset_{instance}:{row['name']}",
                icon=":material/restart_alt:",
                help=f"Back to the default ({_short(default)})",
                on_click=reset,
                type="tertiary",
            )
        if has_preset and not same(value, preset_val):
            b2.button(
                "Preset",
                key=f"_all_params_preset_{instance}:{row['name']}",
                icon=":material/undo:",
                help=f"Back to the value of preset {preset_name} ({_short(preset_val)})",
                on_click=to_preset,
                type="tertiary",
            )

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
        are displayed in a collapsed "advanced parameters" expander below the others.

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
            # Widgets in num_cols columns; advanced parameters follow in a
            # collapsed expander (the expander keeps their widgets, and so
            # their values, on the page while it is closed)
            show_advanced = bool(st.session_state.get("advanced", False))
            basic, advanced_entries = [], []
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
                if advanced and not show_advanced:
                    advanced_entries.append((key, value, entry))
                else:
                    basic.append((key, value, entry))
            self._python_widget_grid(basic, num_cols)
            if advanced_entries:
                with st.expander(
                    f"{len(advanced_entries)} advanced parameter"
                    + ("s" if len(advanced_entries) != 1 else ""),
                    icon=":material/tune:",
                ):
                    self._python_widget_grid(advanced_entries, num_cols)
        self.parameter_manager.save_parameters()

    def _python_widget_grid(self, entries: list, num_cols: int) -> None:
        """input_widget for each (key, value, DEFAULTS entry), num_cols per row."""
        cols = []
        for i, (key, value, entry) in enumerate(entries):
            if i % num_cols == 0:
                cols = st.columns(num_cols)
            name = entry["name"] if "name" in entry else key
            help = entry["help"] if "help" in entry else ""
            min_value = entry["min"] if "min" in entry else None
            max_value = entry["max"] if "max" in entry else None
            step_size = entry["step_size"] if "step_size" in entry else 1
            widget_type = entry["widget_type"] if "widget_type" in entry else "auto"
            options = entry["options"] if "options" in entry else None

            with cols[i % num_cols]:
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

    def experimental_design(
        self, key: str, name: str = "Experimental design", suggest: bool = False
    ) -> None:
        """
        Table assigning each selected input file a condition, biological replicate and fraction.

        Edits are saved to ``<workflow_dir>/experimental-design.tsv`` in the
        OpenMS design format, so ``execution()`` can pass that file to a TOPP
        tool's ``-design`` or read it with ``ExperimentalDesign.load_design()``.
        A design.tsv (one- or two-table) or SDRF file can be imported, and
        spreadsheet cells can be pasted into the table. Inconsistencies such as
        missing fractions are shown as notices, not errors.

        Args:
            key (str): The input file key whose selection the design covers
                (the key passed to ``select_input_file``). Pass ``reactive=True``
                to that ``select_input_file`` so the table follows the selection.
            name (str, optional): The heading shown above the table.
            suggest (bool, optional): Also fill the condition and replicate of
                files from the groups their names suggest (``ctrl_R1``,
                ``ctrl_R2``, ``treated_R1`` ...): files in no folder from all
                names, files in a folder (see ``upload_widget``) from the
                names in that folder. Without such groups a file in a folder
                takes the folder as its condition when it has none yet.
        """
        files = st.session_state.get(
            f"{self.parameter_manager.param_prefix}{key}", self.params.get(key, [])
        )
        if isinstance(files, str):
            files = [files]
        st.markdown(f"**{name}**")
        if not files:
            st.info("Select input files to define the experimental design.")
            return

        # Widget state keys stay outside param_prefix: save_parameters() writes
        # every session key with that prefix to params.json.
        version_key = f"_design-{Path(self.workflow_dir).name}-{key}"
        st.session_state.setdefault(version_key, 0)
        stored = load_design(self.workflow_dir, files)
        folders = load_folders(self.workflow_dir, key)
        rows = design_rows(files, folders, suggest=suggest)

        def from_names(design, only_empty):
            """Conditions, replicates and fractions from folders and names."""
            design = design.copy()
            for i, f in enumerate(design["file"]):
                row = rows.get(f)
                if row is None or (only_empty and design.at[i, "condition"]):
                    continue
                design.at[i, "condition"] = row.group
                design.at[i, "replicate"] = row.replicate
                design.at[i, "fraction"] = row.fraction
            return design

        prefilled = from_names(stored, only_empty=True)
        if not prefilled.equals(stored):
            stored = prefilled
            save_design(self.workflow_dir, stored, files)
            st.session_state[version_key] += 1
        if rows:
            st.caption(
                "Conditions are taken from the files' folders"
                + (" or, outside a folder, from their names" if suggest else "")
                + " until you change them."
            )
        def number(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        differs = [
            r["file"] for _, r in stored.iterrows()
            if r["file"] in rows and (
                r["condition"] != rows[r["file"]].group
                or number(r["replicate"]) != rows[r["file"]].replicate
                or number(r["fraction"]) != rows[r["file"]].fraction
            )
        ]
        if differs and st.button(
            f"Take conditions from {'folders and names' if suggest else 'folders'} again",
            key=f"{version_key}-refill",
            help=f"{len(differs)} file(s) have a condition, replicate or fraction other than "
            f"their folder{' or name' if suggest else ''} suggests. This sets all three again.",
        ):
            stored = from_names(stored, only_empty=False)
            save_design(self.workflow_dir, stored, files)
            st.session_state[version_key] += 1

        uploaded = st.file_uploader(
            "Import design.tsv or SDRF",
            type=["tsv", "txt", "sdrf"],
            key=f"{version_key}-import",
            help="An OpenMS experimental design (one- or two-table) or an SDRF file. "
            "Files are matched by name; files it does not list keep their current row.",
        )
        applied_key = f"{version_key}-applied"
        if uploaded is not None and st.session_state.get(applied_key) != uploaded.file_id:
            st.session_state[applied_key] = uploaded.file_id
            try:
                imported = read_design(uploaded.getvalue())
            except (ValueError, KeyError, pd.errors.ParserError) as e:
                st.error(f"Could not read {uploaded.name}: {e}")
            else:
                listed = set(imported["file"])
                kept = stored[~stored["file"].isin(listed)]
                stored = align_design(pd.concat([imported, kept]), files)
                matched = len(listed & set(stored["file"]))
                save_design(self.workflow_dir, stored, files)
                st.session_state[version_key] += 1
                st.toast(f"Imported the design of {matched} of {len(files)} file(s)")

        editor_key = f"{version_key}-{st.session_state[version_key]}"
        base = editor_table(
            st.session_state, editor_key, stored,
            fits=lambda table: list(table["file"]) == list(stored["file"]),
        )
        edited = st.data_editor(
            base,
            key=editor_key,
            hide_index=True,
            num_rows="fixed",
            disabled=["file"],
            column_config={
                "file": st.column_config.TextColumn("File"),
                "condition": st.column_config.TextColumn(
                    "Condition", help="The group this file is compared as, e.g. control or treated."
                ),
                "replicate": st.column_config.NumberColumn(
                    "Replicate", help="Biological replicate within the condition.", min_value=1, step=1
                ),
                "fraction": st.column_config.NumberColumn(
                    "Fraction", help="Fraction number; 1 for unfractionated samples.", min_value=1, step=1
                ),
            },
        )
        path = design_path(self.workflow_dir)
        if not path.is_file() or path.read_text(encoding="utf-8") != to_openms_design(edited, files):
            save_design(self.workflow_dir, edited, files)

        for notice in check_design(edited):
            st.info(notice, icon="ℹ️")
        st.download_button(
            "Download design.tsv",
            to_openms_design(edited, files),
            file_name="design.tsv",
            mime="text/tab-separated-values",
        )

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
                # Applied in a callback, before the rerun starts, rather than with
                # st.rerun() from the button branch: that interrupts the script before
                # configure() renders its widgets, and Streamlit drops the state of
                # every widget a run does not reach. Their keys survive, so the
                # widgets re-render from an empty value, e.g. the mzML file selection
                # is lost and the next start fails with no input files.
                st.button(
                    preset_name,
                    key=f"preset_{preset_name}",
                    help=description if description else None,
                    use_container_width=True,
                    on_click=self._apply_preset_callback,
                    args=(preset_name,),
                )
            # Start new row if needed
            if col_idx == num_cols - 1 and i < len(preset_names) - 1:
                cols = st.columns(num_cols)

    def _apply_preset_callback(self, preset_name: str) -> None:
        if self.parameter_manager.apply_preset(preset_name):
            st.toast(f"Applied preset: {preset_name}")
        else:
            st.toast(f"Failed to apply preset: {preset_name}", icon="⚠️")

    def user_presets(self, num_cols: int = 4) -> None:
        """
        Renders the presets the user saved, a form to save the current settings as
        a new one or delete one, and which preset the settings come from.

        Saved presets live in the workflow directory (user-presets.json), so they
        stay with the workspace. Applying one restores every saved setting.
        """
        pm = self.parameter_manager
        names = pm.get_user_preset_names()
        if not pm.get_preset_names():
            st.markdown("---")
        st.markdown("**Your Presets**")
        if names:
            cols = st.columns(num_cols)
            for i, name in enumerate(names):
                col_idx = i % num_cols
                description = pm.get_preset_description(name)
                with cols[col_idx]:
                    st.button(
                        name,
                        key=f"user_preset_{name}",
                        help=description if description else None,
                        use_container_width=True,
                        on_click=self._apply_preset_callback,
                        args=(name,),
                    )
                if col_idx == num_cols - 1 and i < len(names) - 1:
                    cols = st.columns(num_cols)
        else:
            st.caption("Save the current settings to reuse them in a later run.")

        with st.popover("💾 Save or delete a preset"):
            st.text_input("Preset name", key="user_preset_name")
            st.text_input("Description (optional)", key="user_preset_description")
            st.button(
                "Save current settings",
                key="user_preset_save",
                on_click=self._save_user_preset_callback,
            )
            if names:
                st.selectbox("Saved preset", names, key="user_preset_delete_choice")
                st.button(
                    "Delete preset",
                    key="user_preset_delete",
                    on_click=self._delete_user_preset_callback,
                )

        applied, changed = pm.applied_preset_status()
        if applied and changed:
            st.caption(
                f"✏️ Settings changed since you applied **{applied}**. "
                "Save them as a preset to keep them."
            )
        elif applied:
            st.caption(f"✅ Current settings: **{applied}**")

    def _save_user_preset_callback(self) -> None:
        name = st.session_state.get("user_preset_name", "").strip()
        description = st.session_state.get("user_preset_description", "").strip()
        if not name:
            st.toast("Enter a name for the preset", icon="⚠️")
        elif name in self.parameter_manager.get_preset_names():
            st.toast(f"'{name}' is a built-in preset, choose another name", icon="⚠️")
        elif self.parameter_manager.save_user_preset(name, description):
            st.session_state["user_preset_name"] = ""
            st.session_state["user_preset_description"] = ""
            st.toast(f"Saved preset: {name}")
        else:
            st.toast(f"Could not save preset: {name}", icon="⚠️")

    def _delete_user_preset_callback(self) -> None:
        name = st.session_state.get("user_preset_delete_choice")
        if name and self.parameter_manager.delete_user_preset(name):
            st.toast(f"Deleted preset: {name}")
        else:
            st.toast(f"Could not delete preset: {name}", icon="⚠️")

    def file_upload_section(self, custom_upload_function) -> None:
        self.upload_targets = {}
        if not data_import_ui.enabled():
            self._upload_tab(custom_upload_function)
            return
        # The upload widgets fill self.upload_targets, so the Upload tab is
        # drawn first and the import tabs route files by it.
        upload, cloud, pride = st.tabs(
            ["💻 Data on your computer", "☁️ Cloud data", "🧬 Import from PRIDE"]
        )
        with upload:
            self._upload_tab(custom_upload_function)
        with cloud:
            data_import_ui.link_import_section(
                self.workflow_dir, self.upload_targets, source=data_import_ui.LINK
            )
        with pride:
            data_import_ui.link_import_section(
                self.workflow_dir, self.upload_targets, source=data_import_ui.PRIDE
            )

    def _upload_tab(self, custom_upload_function) -> None:
        custom_upload_function()
        # A local install already has the input files on disk.
        if st.session_state.location != "local":
            c1, _ = st.columns(2)
            if c1.button("⬇️ Download files", use_container_width=True):
                self.zip_and_download_files(Path(self.workflow_dir, "input-files"))

    def parameter_section(self, custom_parameter_function) -> None:
        # No "Show advanced parameters" toggle: each TOPP tool's "All N
        # parameters" dialog reaches the advanced ones, and a python tool's
        # sit in an expander. An app can still set this to True itself.
        st.session_state.setdefault("advanced", False)

        # Display threads configuration for local mode only
        if not st.session_state.settings.get("online_deployment", False):
            default_threads = local_thread_default(st.session_state.settings)
            if not local_threads_pinned(st.session_state.settings):
                default_help = (
                    f"Default: all CPUs of this computer but one "
                    f"({usable_cpu_count()} usable, so {default_threads})."
                )
            else:
                default_help = f"Default: {default_threads}, set by this app."
            self.input_widget(
                key="max_threads",
                default=default_threads,
                name="Threads",
                widget_type="number",
                min_value=1,
                help=(
                    "Maximum threads for parallel processing. Threads are "
                    "distributed between parallel commands and per-tool thread "
                    f"allocation. {default_help}"
                ),
            )

        # Display preset buttons if presets are available for this workflow
        self.preset_buttons()
        self.user_presets()

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
                self.parameter_manager.forget_applied_preset()
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
                # encoding="utf-8" explicitly: the payload is decoded as utf-8
                # just above, and writing it back in the platform codepage
                # produced a params.json that no later utf-8 read could decode.
                with open(self.parameter_manager.params_file, "w", encoding="utf-8") as f:
                    f.write(up.read().decode("utf-8"))
                self.parameter_manager.clear_parameter_session_state()
                st.toast("Parameters imported")
                st.rerun()

    def execution_section(
        self,
        start_workflow_function,
        get_status_function=None,
        stop_workflow_function=None,
        autostart: bool = False,
        results_page=None,
        results_label: str = "Open results",
        on_open_results=None,
    ) -> None:
        """Start/Stop, progress and log of the workflow.

        ``autostart`` starts the workflow on this render unless one is running
        (the Run button of the configure page). ``results_page`` is linked
        below the success message of a finished run; ``on_open_results`` runs
        before that button switches to it.
        """
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

        # Started from the configure page's Run button
        if autostart and not is_running:
            start_workflow_function()
            with st.spinner("**Workflow starting...**"):
                time.sleep(1)
                st.rerun()

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

        # Display logs and status. Drawn into one st.empty() slot so the
        # running view replaces the finished one completely: st.rerun()
        # below ends the script early, which otherwise leaves the earlier
        # view's trailing elements on the page.
        status_area = st.empty()
        with status_area.container():
            if is_running:
                # Real-time display during execution
                spinner_text = "**Workflow running...**"
                if job_status == "queued":
                    pos = status.get("queue_position", "?")
                    spinner_text = f"**Waiting in queue (position {pos})...**"

                if job_status != "queued":
                    self._show_run_progress()
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
                outcome = classify_log_outcome(content)
                if outcome == "finished":
                    st.success("**Workflow completed successfully.**")
                    if results_page is not None:
                        self._results_link(results_page, results_label, on_open_results)
                elif outcome == "cancelled":
                    st.warning("**Workflow was cancelled.**")
                else:
                    st.error("**Errors occurred, check log file.**")
                self._show_run_summary(show_failures=outcome != "finished")
                # Apply line limit to static display
                if log_lines_count == "all":
                    display_lines = lines
                else:
                    display_lines = lines[-st.session_state.log_lines_count:]
                st.code("".join(display_lines), language="neon", line_numbers=False)

    def _results_link(self, results_page, label: str, on_open=None) -> None:
        """A primary button that opens the results page of a finished run.

        It leaves ``st.session_state[latest_results_key(workflow_dir)]`` set, so a
        results page that picks among the results itself (no run folders) can
        pop it and show the newest one; ``on_open`` (a multi-run workflow
        selects its newest finished run) runs before the page switch.
        """
        if st.button(label, type="primary", icon=":material/arrow_forward:",
                     key="workflow-open-results"):
            st.session_state[latest_results_key(self.workflow_dir)] = True
            if on_open is not None:
                on_open()
            st.switch_page(results_page)

    def _show_run_progress(self) -> None:
        """Progress of the running workflow: per sample when the run records
        its samples, else per file of the running tool; elapsed times."""
        state = read_progress(self.workflow_dir)
        if not state:
            return
        if len(state.get("samples") or []) > 1:
            self._show_sample_progress(state)
            return
        if not state.get("steps"):
            return
        now = time.time()
        step = state["steps"][-1]
        files = step["files"]
        n = len(files)
        finished = sum(f["status"] in (DONE, FAILED) for f in files)
        active = [i for i, f in enumerate(files) if f["status"] == RUNNING]
        with st.container(border=True):
            st.markdown(
                f"**Elapsed {format_duration(now - state['started'])}** · "
                f"step {len(state['steps'])}: **{step['tool']}**"
                + ("" if step["ended"] is None else " finished")
            )
            # A step without commands (e.g. the workflow's own processing) has no files
            if step["ended"] is None and n:
                counts = file_counts(step)
                if active and n > 1:
                    which = ", ".join(str(i + 1) for i in active)
                    where = (
                        f"running file{'s' if len(active) > 1 else ''} {which} of {n}"
                        f" · {counts[DONE]} done"
                    )
                else:
                    where = f"{counts[DONE]} of {n} file{'s' if n > 1 else ''} done"
                if counts[FAILED]:
                    where += f" · :red[{counts[FAILED]} failed]"
                threads = step.get("threads", 1)
                parallel = step.get("parallel", 1)
                text = (
                    f"{where} · {format_duration(now - step['started'])} · "
                    f"{threads} thread{'s' if threads > 1 else ''}"
                    + (f" × {parallel} in parallel" if parallel > 1 else "")
                )
                st.progress(finished / n if n else 0.0, text=text)
                if len(active) == 1:
                    self._show_tool_progress()
            if n > 1 or step["ended"] is not None:
                lines = []
                for f in files:
                    if f["status"] == DONE:
                        lines.append(f":green[:material/check_circle:] {f['name']} :gray[{format_duration(f['ended'] - f['started'])}]")
                    elif f["status"] == FAILED:
                        lines.append(f":red[:material/cancel:] {f['name']} :red[failed]")
                    elif f["status"] == RUNNING:
                        lines.append(f":blue[:material/progress_activity:] **{f['name']}** :gray[{format_duration(now - f['started'])}]")
                    else:
                        lines.append(f":gray[:material/radio_button_unchecked: {f['name']}]")
                st.markdown("  \n".join(lines))
            earlier = state["steps"][:-1]
            if earlier:
                st.caption("Done: " + " · ".join(self._step_summary(s) for s in earlier))

    def _show_tool_progress(self) -> None:
        """The running tool's own progress ("loading spectra 42 %"), if it reports any."""
        found = tool_progress(Path(self.workflow_dir, "logs", "all.log"))
        if found:
            label, fraction = found
            st.progress(fraction, text=f":gray[{label} · {fraction:.0%}]")

    def _show_sample_progress(self, state: dict) -> None:
        """One line per sample: waiting, running (with its tool), done or failed."""
        now = time.time()
        samples = state["samples"]
        n = len(samples)
        counts = sample_counts(state)
        running = [i for i, s in enumerate(samples) if s["status"] == RUNNING]
        with st.container(border=True):
            head = f"**Elapsed {format_duration(now - state['started'])}**"
            # A step outside every sample, e.g. one over all of them at the end
            shared = None
            steps = state.get("steps") or []
            if steps and steps[-1].get("sample") is None and steps[-1]["ended"] is None:
                shared = steps[-1]
            if running:
                i = running[0]
                head += f" · sample {i + 1} of {n}: **{samples[i]['name']}**"
            elif shared is not None:
                head += f" · **{shared['tool']}**"
            st.markdown(head)
            text = f"{counts[DONE]} of {n} samples done"
            if counts[FAILED]:
                text += f" · :red[{counts[FAILED]} failed]"
            st.progress((counts[DONE] + counts[FAILED]) / n, text=text)
            step = shared
            if running:
                step = current_step(state, samples[running[0]]["name"])
            one_command = (
                step is not None
                and step["ended"] is None
                and file_counts(step)[RUNNING] == 1
            )
            if one_command:
                self._show_tool_progress()
            st.markdown("  \n".join(self._sample_lines(state, now)))

    @staticmethod
    def _sample_lines(state: dict, now: float) -> list:
        """A markdown line per sample, with its time and, while it runs, its tool."""
        lines = []
        for s in state["samples"]:
            if s["status"] == DONE:
                lines.append(f":green[:material/check_circle:] {s['name']} :gray[{format_duration(s['ended'] - s['started'])}]")
            elif s["status"] == FAILED:
                lines.append(f":red[:material/cancel:] {s['name']} :red[failed]")
            elif s["status"] == RUNNING:
                step = current_step(state, s["name"])
                tool = ""
                if step is not None:
                    tool = f" · {step['tool']}" + ("" if step["ended"] is None else " finished")
                lines.append(f":blue[:material/progress_activity:] **{s['name']}** :gray[{format_duration(now - s['started'])}{tool}]")
            else:
                lines.append(f":gray[:material/radio_button_unchecked: {s['name']}]")
        return lines

    @staticmethod
    def _step_summary(step: dict) -> str:
        """'FeatureFinderMetabo: 3 files in 0:20'."""
        n = len(step["files"])
        took = format_duration((step["ended"] or time.time()) - step["started"])
        summary = f"{step['tool']}: " + (f"{n} files in {took}" if n > 1 else took)
        failed = file_counts(step)[FAILED]
        if failed and n > 1:
            summary += f" ({n - failed} done, {failed} failed)"
        elif failed:
            summary += " (failed)"
        return summary

    def _show_run_summary(self, show_failures: bool) -> None:
        """After a run: the time per tool and, for a failed tool, where it failed."""
        state = read_progress(self.workflow_dir)
        if not state or not state.get("steps"):
            return
        if show_failures:
            for failure in failures(state):
                st.error(
                    f"**{failure['context']}**"
                    + (f": {failure['message']}" if failure["message"] else "")
                )
                if failure["output"]:
                    with st.expander(
                        f"Tool output (exit code {failure['returncode']})"
                    ):
                        st.code("\n".join(failure["output"]), language="neon")
        if len(state.get("samples") or []) > 1:
            st.markdown("  \n".join(self._sample_lines(state, time.time())))
            st.caption(self._tool_totals(state["steps"]))
            return
        st.caption(" · ".join(self._step_summary(s) for s in state["steps"]))

    @staticmethod
    def _tool_totals(steps: list) -> str:
        """'FLASHDeconv: 4 runs in 2:10 · FLASHTnT: 4 runs in 5:02 (1 failed)'."""
        totals = {}
        for step in steps:
            took = (step["ended"] or time.time()) - step["started"]
            runs, seconds, failed = totals.get(step["tool"], (0, 0.0, 0))
            totals[step["tool"]] = (
                runs + 1,
                seconds + took,
                failed + (file_counts(step)[FAILED] > 0),
            )
        parts = []
        for tool, (runs, seconds, failed) in totals.items():
            part = f"{tool}: " + (
                f"{runs} runs in {format_duration(seconds)}" if runs > 1 else format_duration(seconds)
            )
            if failed:
                part += f" ({failed} failed)"
            parts.append(part)
        return " · ".join(parts)

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

        elif job_status == "canceled":
            st.warning(f"**Status: {label}** - Workflow was cancelled.")

        # Expandable job details
        with st.expander("Job Details", expanded=False):
            st.code(f"""Job ID: {status.get('job_id', 'N/A')}
Submitted: {status.get('enqueued_at', 'N/A')}
Started: {status.get('started_at', 'N/A')}""")



    def results_section(self, custom_results_function) -> None:
        custom_results_function()

    def results_download_section(
        self, exclude: list[str] | None = None, results_dir: str | Path | None = None
    ) -> None:
        """
        Offer every file under the workflow's results directory for download.

        Lists the files, lets the user download any single one, and builds a
        ZIP of the chosen result folders on request. Only the selected file (or
        the ZIP) is read into memory, so large result sets stay cheap to render.

        A local install exports instead: the user sets a folder at the top and
        one button copies every listed file to ``<folder>/<workflow>-results``.

        Args:
            exclude: Names of files or folders to leave out (matched against
                every part of a file's path relative to the results directory,
                glob patterns allowed), e.g. caches: ``["insight_cache", "*.tmp"]``.
            results_dir: Directory to offer. Defaults to ``<workflow_dir>/results``.
        """
        from fnmatch import fnmatch

        results_dir = Path(results_dir or Path(self.workflow_dir, "results"))
        exclude = list(exclude or [])

        def excluded(rel: Path) -> bool:
            return any(fnmatch(part, pattern) for part in rel.parts for pattern in exclude)

        files = []
        if results_dir.exists():
            for path in sorted(results_dir.rglob("*")):
                rel = path.relative_to(results_dir)
                if path.is_file() and not excluded(rel):
                    files.append(rel)

        if not files:
            st.info("No results yet. Run the workflow first.")
            return

        def folder_of(rel: Path) -> str:
            return rel.parts[0] if len(rel.parts) > 1 else "."

        def human_size(n_bytes: float) -> str:
            for unit in ["B", "KB", "MB", "GB"]:
                if n_bytes < 1024 or unit == "GB":
                    return f"{n_bytes:.0f} {unit}" if unit == "B" else f"{n_bytes:.1f} {unit}"
                n_bytes /= 1024

        key_prefix = f"results-download-{Path(self.workflow_dir).name}"
        local = st.session_state.get("location") == "local"
        if local:
            export_dir = export_folder_input(key_prefix)

        st.dataframe(
            [
                {
                    "Folder": folder_of(rel),
                    "File": str(rel.relative_to(folder_of(rel))),
                    "Size": human_size(Path(results_dir, rel).stat().st_size),
                    "Modified": datetime.fromtimestamp(
                        Path(results_dir, rel).stat().st_mtime
                    ).strftime("%Y-%m-%d %H:%M"),
                }
                for rel in files
            ],
            hide_index=True,
            width="stretch",
        )

        if local:
            if st.button(
                "📤 Export",
                type="primary",
                key=f"{key_prefix}-export",
                width="stretch",
            ):
                export_files(
                    [(Path(results_dir, rel), rel) for rel in files],
                    Path(export_dir, f"{Path(self.workflow_dir).name}-results"),
                )
            return

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Single file**")
            selected = st.selectbox(
                "File",
                files,
                format_func=str,
                key=f"{key_prefix}-file",
                label_visibility="collapsed",
            )
            if selected is not None:
                st.download_button(
                    "⬇️ Download file",
                    data=Path(results_dir, selected).read_bytes(),
                    file_name=Path(selected).name,
                    key=f"{key_prefix}-file-button",
                    width="stretch",
                )

        with c2:
            st.markdown("**ZIP archive**")
            folders = sorted({folder_of(rel) for rel in files})
            chosen = st.multiselect(
                "Folders",
                folders,
                default=folders,
                key=f"{key_prefix}-folders",
                label_visibility="collapsed",
            )
            zip_path = Path(self.workflow_dir, "downloads", "results.zip")
            prepared_key = f"{key_prefix}-prepared"
            if st.button(
                "📦 Prepare ZIP",
                disabled=not chosen,
                key=f"{key_prefix}-zip",
                width="stretch",
            ):
                zip_path.parent.mkdir(parents=True, exist_ok=True)
                selected_files = [rel for rel in files if folder_of(rel) in chosen]
                with st.spinner(f"Compressing {len(selected_files)} files..."):
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for rel in selected_files:
                            zip_file.write(Path(results_dir, rel), Path("results", rel))
                # Keyed on the folder too: a multi-run workflow offers one run at a time.
                st.session_state[prepared_key] = (str(results_dir), sorted(chosen))
            if st.session_state.get(prepared_key) == (str(results_dir), sorted(chosen)) and zip_path.exists():
                with open(zip_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download ZIP",
                        data=f,
                        file_name=f"{Path(self.workflow_dir).name}-results.zip",
                        mime="application/zip",
                        key=f"{key_prefix}-zip-button",
                        width="stretch",
                    )

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
        params = remove_full_paths(
            {k: v for k, v in self.params.items() if k != THREADS_USER_MARKER}
        )

        summary_text = ""
        python = {}
        topp = {}
        general = {}

        for k, v in params.items():
            if k == "_defaults":
                continue
            if isinstance(v, dict):
                topp[k] = v
            elif ".py" in k:
                script = k.split(".py")[0] + ".py"
                if script not in python:
                    python[script] = {}
                python[script][k.split(".py")[1][1:]] = v
            else:
                general[k] = v

        # Merge _defaults into topp so summary shows custom defaults + user overrides
        defaults = params.get("_defaults", {})
        for tool_name, default_vals in defaults.items():
            if tool_name not in topp:
                topp[tool_name] = {}
            topp[tool_name] = {**default_vals, **topp.get(tool_name, {})}

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
