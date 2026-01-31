import os
import sys
import uuid
import json
import time
import psutil
import shutil

import pandas as pd
import streamlit as st

from typing import Any
from pathlib import Path
from streamlit.components.v1 import html

try:
    from tkinter import Tk, filedialog

    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False

from src.common.captcha_ import captcha_control
from src.common.admin import (
    is_admin_configured,
    verify_admin_password,
    demo_exists,
    save_workspace_as_demo,
)

# Detect system platform
OS_PLATFORM = sys.platform


def is_safe_workspace_name(name: str) -> bool:
    """
    Check if a workspace name is safe (no path traversal characters).

    Args:
        name: The workspace name to validate.

    Returns:
        bool: True if safe, False if contains path separators or parent references.
    """
    if not name:
        return False
    # Reject path separators and parent directory references
    return "/" not in name and "\\" not in name and name not in ("..", ".")


def get_demo_source_dirs() -> list[Path]:
    """
    Get list of demo workspace source directories from settings.

    Supports both legacy 'source_dir' (string) and new 'source_dirs' (array) formats.
    Non-existent directories are silently skipped.

    Returns:
        list[Path]: List of existing source directory paths.
    """
    settings = st.session_state.get("settings", {})
    demo_config = settings.get("demo_workspaces", {})

    if not demo_config.get("enabled", False):
        return []

    # Support both source_dirs (array) and source_dir (string) for backward compatibility
    if "source_dirs" in demo_config:
        dirs = demo_config["source_dirs"]
        if isinstance(dirs, str):
            dirs = [dirs]
    elif "source_dir" in demo_config:
        dirs = [demo_config["source_dir"]]
    else:
        dirs = ["example-data/workspaces"]

    # Return only existing directories
    return [Path(d) for d in dirs if Path(d).exists()]


def get_available_demo_workspaces() -> list[str]:
    """
    Get a list of available demo workspaces from all configured source directories.

    When the same demo name exists in multiple directories, the first occurrence wins.

    Returns:
        list[str]: List of unique demo workspace names.
    """
    seen = set()
    demos = []

    for source_dir in get_demo_source_dirs():
        for p in source_dir.iterdir():
            if p.is_dir() and p.name not in seen:
                seen.add(p.name)
                demos.append(p.name)

    return demos


def find_demo_workspace_path(demo_name: str) -> Path | None:
    """
    Find the source path for a demo workspace by searching all configured directories.

    Directories are searched in order; the first match is returned.

    Args:
        demo_name: Name of the demo workspace to find.

    Returns:
        Path to the demo workspace, or None if not found or name is unsafe.
    """
    # Validate against path traversal attacks
    if not is_safe_workspace_name(demo_name):
        return None

    for source_dir in get_demo_source_dirs():
        demo_path = source_dir / demo_name
        if demo_path.exists() and demo_path.is_dir():
            return demo_path
    return None


def _symlink_tree(source: Path, target: Path) -> None:
    """
    Recursively create directory structure and symlink files from source to target.

    Creates real directories but symlinks individual files, allowing users to
    add new files to workspace directories without affecting the original.
    params.json and .ini files are copied instead of symlinked so they can be
    modified independently.

    Args:
        source: Source directory path.
        target: Target directory path.
    """
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target_item = target / item.name
        if item.is_dir():
            _symlink_tree(item, target_item)
        elif item.name == "params.json" or item.suffix == ".ini":
            # Copy config files so they can be modified independently
            shutil.copy2(item, target_item)
        else:
            # Create symlink to the source file
            target_item.symlink_to(item.resolve())


def copy_demo_workspace(demo_name: str, target_path: Path) -> bool:
    """
    Copy a demo workspace to the target path.

    On Linux, creates symlinks to demo files instead of copying them.
    On other platforms, copies files normally.

    Searches all configured source directories for the demo (first match wins).

    Args:
        demo_name: Name of the demo workspace to copy.
        target_path: Destination path for the workspace.

    Returns:
        bool: True if copy was successful, False otherwise.
    """
    demo_path = find_demo_workspace_path(demo_name)

    if demo_path is None:
        return False

    try:
        if target_path.exists():
            shutil.rmtree(target_path)

        # Use symlinks on Linux for efficiency
        if OS_PLATFORM == "linux":
            _symlink_tree(demo_path, target_path)
        else:
            shutil.copytree(demo_path, target_path)
        return True
    except Exception:
        return False


@st.fragment(run_every=5)
def monitor_hardware():
    cpu_progress = psutil.cpu_percent(interval=None) / 100
    ram_progress = 1 - psutil.virtual_memory().available / psutil.virtual_memory().total

    st.text(f"Ram ({ram_progress * 100:.2f}%)")
    st.progress(ram_progress)

    st.text(f"CPU ({cpu_progress * 100:.2f}%)")
    st.progress(cpu_progress)

    st.caption(f"Last fetched at: {time.strftime('%H:%M:%S')}")


@st.fragment(run_every=5)
def monitor_queue():
    """Display queue metrics in sidebar (online mode only)"""
    try:
        from src.workflow.health import get_queue_metrics

        metrics = get_queue_metrics()
        if not metrics.get("available", False):
            return

        st.markdown("---")
        st.markdown("**Queue Status**")

        total_workers = metrics.get("total_workers", 0)
        busy_workers = metrics.get("busy_workers", 0)
        queued_jobs = metrics.get("queued_jobs", 0)

        col1, col2 = st.columns(2)
        col1.metric(
            "Workers",
            f"{busy_workers}/{total_workers}",
            help="Busy workers / Total workers"
        )
        col2.metric(
            "Queued",
            queued_jobs,
            help="Jobs waiting in queue"
        )

        # Utilization progress bar
        if total_workers > 0:
            utilization = busy_workers / total_workers
            st.progress(utilization, text=f"{int(utilization * 100)}% utilized")

        # Warning if queue is backing up
        if queued_jobs > total_workers * 2 and total_workers > 0:
            st.warning(f"High queue depth: {queued_jobs} jobs waiting")

        st.caption(f"Last fetched at: {time.strftime('%H:%M:%S')}")

    except Exception:
        pass  # Silently fail if queue not available


def load_params(default: bool = False) -> dict[str, Any]:
    """
    Load parameters from a JSON file and return a dictionary containing them.

    If a 'params.json' file exists in the workspace, load the parameters from there.
    Otherwise, load the default parameters from 'default-parameters.json'.

    Additionally, check if any parameters have been modified by the user during the current session
    and update the values in the parameter dictionary accordingly. Also make sure that all items from
    the parameters dictionary are accessible from the session state as well.

    Args:
        default (bool): Load default parameters. Defaults to True.

    Returns:
        dict[str, Any]: A dictionary containing the parameters.
    """

    # Check if workspace is enabled. If not, load default parameters.
    if not st.session_state.settings["enable_workspaces"]:
        default = True

    # Construct the path to the parameter file
    path = Path(st.session_state.workspace, "params.json")

    # Load the parameters from the file, or from the default file if the parameter file does not exist
    if path.exists() and not default:
        with open(path, "r", encoding="utf-8") as f:
            params = json.load(f)
    else:
        with open("default-parameters.json", "r", encoding="utf-8") as f:
            params = json.load(f)

    # Return the parameter dictionary
    return params


def save_params(params: dict[str, Any]) -> None:
    """
    Save the given dictionary of parameters to a JSON file.

    If a 'params.json' file already exists in the workspace, overwrite it with the new parameters.
    Otherwise, create a new 'params.json' file in the workspace directory and save the parameters there.

    Additionally, check if any parameters have been modified by the user during the current session
    and update the values in the parameter dictionary accordingly.

    This function should be run at the end of each page, if the parameters dictionary has been modified directly.
    Note that session states with the same keys will override any direct changes!

    Args:
        params (dict[str, Any]): A dictionary containing the parameters to be saved.

    Returns:
        dict[str, Any]: Updated parameters.
    """

    # Check if the workspace is enabled and if a 'params.json' file exists in the workspace directory
    if not st.session_state.settings["enable_workspaces"]:
        return

    # Update the parameter dictionary with any modified parameters from the current session
    for key, value in st.session_state.items():
        if key in params.keys():
            params[key] = value

    # Save the parameter dictionary to a JSON file in the workspace directory
    path = Path(st.session_state.workspace, "params.json")
    with open(path, "w", encoding="utf-8") as outfile:
        json.dump(params, outfile, indent=4)

    return params


def page_setup(page: str = "") -> dict[str, Any]:
    """
    Set up the Streamlit page configuration and determine the workspace for the current session.

    This function should be run at the start of every page for setup and to get the parameters dictionary.

    Args:
        page (str, optional): The name of the current page, by default "".

    Returns:
        dict[str, Any]: A dictionary containing the parameters loaded from the parameter file.
    """
    if "settings" not in st.session_state:
        with open("settings.json", "r") as f:
            st.session_state.settings = json.load(f)

    # Set Streamlit page configurations
    st.set_page_config(
        page_title=st.session_state.settings["app-name"],
        page_icon="assets/openms_transparent_bg_logo.svg",
        layout="wide",
        initial_sidebar_state="auto",
        menu_items=None,
    )

    # Expand sidebar navigation
    st.markdown(
        """
        <style>
            .stMultiSelect [data-baseweb=select] span{
                max-width: 500px;
                font-size: 1rem;
            }
            div[data-testid='stSidebarNav'] ul {max-height:none}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.logo("assets/openms_transparent_bg_logo.svg")

    # Create google analytics if consent was given
    if (
        ("tracking_consent" not in st.session_state)
        or (st.session_state.tracking_consent is None)
        or (not st.session_state.settings["online_deployment"])
    ):
        st.session_state.tracking_consent = None
    else:
        if (st.session_state.settings["analytics"]["google-analytics"]["enabled"]) and (
            st.session_state.tracking_consent["google-analytics"] == True
        ):
            html(
                """
                <!DOCTYPE html>
                <html lang="en">
                    <head></head>
                    <body><script>
                    window.parent.gtag('consent', 'update', {
                    'analytics_storage': 'granted'
                    });
                    </script></body>
                </html>
                """,
                width=1,
                height=1,
            )
        if (st.session_state.settings["analytics"]["piwik-pro"]["enabled"]) and (
            st.session_state.tracking_consent["piwik-pro"] == True
        ):
            html(
                """
                <!DOCTYPE html>
                <html lang="en">
                    <head></head>
                    <body><script>
                    var consentSettings = {
                        analytics: { status: 1 } // Set Analytics consent to 'on' (1 for on, 0 for off)
                    };
                    window.parent.ppms.cm.api('setComplianceSettings', { consents: consentSettings }, function() {
                        console.log("PiwikPro Analytics consent set to on.");
                    }, function(error) {
                        console.error("Failed to set PiwikPro analytics consent:", error);
                    });
                    </script></body>
                </html>
                """,
                width=1,
                height=1,
            )

    # Determine the workspace for the current session
    if ("workspace" not in st.session_state) or (
        ("workspace" in st.query_params)
        and (st.query_params.workspace != st.session_state.workspace.name)
    ):
        # Clear any previous caches
        st.cache_data.clear()
        st.cache_resource.clear()
        # Check location
        if not st.session_state.settings["online_deployment"]:
            st.session_state.location = "local"
            st.session_state["previous_dir"] = os.getcwd()
            st.session_state["local_dir"] = ""
        else:
            st.session_state.location = "online"
        # if we run the packaged windows version, we start within the Python directory -> need to change working directory to ..\streamlit-template
        if "windows" in sys.argv:
            os.chdir("../streamlit-template")
        # Define the directory where all workspaces will be stored
        if (
            st.session_state.settings["workspaces_dir"]
            and st.session_state.location == "local"
        ):
            workspaces_dir = Path(
                st.session_state.settings["workspaces_dir"],
                "workspaces-" + st.session_state.settings["repository-name"],
            )
        else:
            workspaces_dir = ".."

        # Check if workspace logic is enabled
        if st.session_state.settings["enable_workspaces"]:
            # Get available demo workspaces using helper function
            available_demos = get_available_demo_workspaces()

            if "workspace" in st.query_params:
                requested_workspace = st.query_params.workspace

                # Validate workspace name against path traversal
                if not is_safe_workspace_name(requested_workspace):
                    # Invalid workspace name - fall back to new UUID workspace
                    workspace_id = str(uuid.uuid1())
                    st.session_state.workspace = Path(workspaces_dir, workspace_id)
                    st.query_params.workspace = workspace_id
                # Check if the requested workspace is a demo workspace (online mode)
                elif st.session_state.location == "online" and requested_workspace in available_demos:
                    # Create a new UUID workspace and copy demo contents
                    workspace_id = str(uuid.uuid1())
                    st.session_state.workspace = Path(workspaces_dir, workspace_id)
                    st.query_params.workspace = workspace_id
                    # Copy demo workspace contents using helper function
                    copy_demo_workspace(requested_workspace, st.session_state.workspace)
                else:
                    st.session_state.workspace = Path(
                        workspaces_dir, requested_workspace
                    )
            elif st.session_state.location == "online":
                workspace_id = str(uuid.uuid1())
                st.session_state.workspace = Path(workspaces_dir, workspace_id)
                st.query_params.workspace = workspace_id
            else:
                st.session_state.workspace = Path(workspaces_dir, "default")
                st.query_params.workspace = "default"

        else:
            # Use default workspace when workspace feature is disabled
            st.session_state.workspace = Path(workspaces_dir, "default")

            # For local mode with workspaces disabled, copy demo workspaces if they don't exist
            for demo_name in get_available_demo_workspaces():
                target = Path(workspaces_dir, demo_name)
                if not target.exists():
                    copy_demo_workspace(demo_name, target)

        if st.session_state.location != "online":
            # not any captcha so, controllo should be true
            st.session_state["controllo"] = True

    # If no workspace is specified and workspace feature is enabled, set default workspace and query param
    if (
        "workspace" not in st.query_params
        and st.session_state.settings["enable_workspaces"]
    ):
        st.query_params.workspace = st.session_state.workspace.name

    # Make sure the necessary directories exist
    st.session_state.workspace.mkdir(parents=True, exist_ok=True)
    Path(st.session_state.workspace, "mzML-files").mkdir(parents=True, exist_ok=True)

    # Render the sidebar
    params = render_sidebar(page)

    captcha_control()

    # If run in hosted mode, show captcha as long as it has not been solved
    # if not "local" in sys.argv:
    #    if "controllo" not in st.session_state:
    #        # Apply captcha by calling the captcha_control function
    #        captcha_control()

    # If run in hosted mode, show captcha as long as it has not been solved
    if "controllo" not in st.session_state or (
        "controllo" in params.keys() and params["controllo"] == False
    ):
        # Apply captcha by calling the captcha_control function
        captcha_control()

    return params


def render_sidebar(page: str = "") -> None:
    """
    Renders the sidebar on the Streamlit app, which includes the workspace switcher,
    the mzML file selector, the logo, and settings.

    Args:
        params (dict): A dictionary containing the initial parameters of the app.
            Used in the sidebar to display the following settings:
            - selected-mzML-files : str
                A string containing the selected mzML files.
            - image-format : str
                A string containing the image export format.
        page (str): A string indicating the current page of the Streamlit app.

    Returns:
        None
    """
    params = load_params()
    with st.sidebar:
        # The main page has workspace switcher
        # Display workspace switcher if workspace is enabled in local mode
        if st.session_state.settings["enable_workspaces"]:
            # Workspaces directory specified in the settings.json
            if (
                st.session_state.settings["workspaces_dir"]
                and st.session_state.location == "local"
            ):
                workspaces_dir = Path(
                    st.session_state.settings["workspaces_dir"],
                    "workspaces-" + st.session_state.settings["repository-name"],
                )
            else:
                workspaces_dir = ".."
            # Online: show current workspace name in info text and option to change to other existing workspace
            if st.session_state.location == "local":
                with st.expander("🖥️ **Workspaces**"):
                    # Define callback function to change workspace
                    def change_workspace():
                        for key in params.keys():
                            if key in st.session_state.keys():
                                del st.session_state[key]
                        st.query_params.workspace = st.session_state["chosen-workspace"]

                    # Get all available workspaces as options
                    options = [
                        file.name for file in workspaces_dir.iterdir() if file.is_dir()
                    ]
                    # Let user chose an already existing workspace
                    st.selectbox(
                        "choose existing workspace",
                        options,
                        index=options.index(str(st.session_state.workspace.stem)),
                        on_change=change_workspace,
                        key="chosen-workspace",
                    )
                    # Create or Remove workspaces
                    create_remove = st.text_input("create/remove workspace", "").strip()
                    path = Path(workspaces_dir, create_remove)
                    # Create new workspace
                    if st.button("**Create Workspace**"):
                        if create_remove:
                            path.mkdir(parents=True, exist_ok=True)
                            st.session_state.workspace = path
                            st.query_params.workspace = create_remove
                            # Temporary as the query update takes a short amount of time
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning("Please enter a valid workspace name.")
                    # Remove existing workspace and fall back to default
                    if st.button("⚠️ Delete Workspace"):
                        if path.exists():
                            shutil.rmtree(path)
                            st.session_state.workspace = Path(workspaces_dir, "default")
                            st.query_params.workspace = "default"
                            st.rerun()

            # Demo workspace loader for online mode
            if st.session_state.location == "online":
                available_demos = get_available_demo_workspaces()
                if available_demos:
                    with st.expander("🎮 **Demo Data**"):
                        st.caption("Load example data to explore the app")
                        selected_demo = st.selectbox(
                            "Select demo dataset",
                            available_demos,
                            key="selected-demo-workspace"
                        )
                        if st.button("Load Demo Data"):
                            demo_path = find_demo_workspace_path(selected_demo)
                            if demo_path:
                                # Link or copy demo files to current workspace
                                for item in demo_path.iterdir():
                                    target = st.session_state.workspace / item.name
                                    if item.is_dir():
                                        if target.exists():
                                            shutil.rmtree(target)
                                        # Use symlinks on Linux for efficiency
                                        if OS_PLATFORM == "linux":
                                            _symlink_tree(item, target)
                                        else:
                                            shutil.copytree(item, target)
                                    else:
                                        if target.exists():
                                            target.unlink()
                                        # Copy config files so they can be modified independently
                                        if OS_PLATFORM == "linux" and item.name != "params.json" and item.suffix != ".ini":
                                            target.symlink_to(item.resolve())
                                        else:
                                            shutil.copy2(item, target)
                                st.success(f"Demo data '{selected_demo}' loaded!")
                                time.sleep(1)
                                st.rerun()

                # Save as Demo section (online mode only)
                with st.expander("💾 **Save as Demo**"):
                    st.caption("Save current workspace as a demo for others to use")

                    demo_name_input = st.text_input(
                        "Demo name",
                        key="save-demo-name",
                        placeholder="e.g., workshop-2024",
                        help="Name for the demo workspace (no spaces or special characters)"
                    )

                    # Check if demo already exists
                    demo_name_clean = demo_name_input.strip() if demo_name_input else ""
                    existing_demo = demo_exists(demo_name_clean) if demo_name_clean else False

                    if existing_demo:
                        st.warning(f"Demo '{demo_name_clean}' already exists and will be overwritten.")
                        confirm_overwrite = st.checkbox(
                            "Confirm overwrite",
                            key="confirm-demo-overwrite"
                        )
                    else:
                        confirm_overwrite = True  # No confirmation needed for new demos

                    if st.button("Save as Demo", key="save-demo-btn", disabled=not demo_name_clean):
                        if not is_admin_configured():
                            st.error(
                                "Admin not configured. Create `.streamlit/secrets.toml` with "
                                "an `[admin]` section containing `password = \"your-password\"`"
                            )
                        elif existing_demo and not confirm_overwrite:
                            st.error("Please confirm overwrite to continue.")
                        else:
                            # Show password dialog
                            st.session_state["show_admin_password_dialog"] = True

                    # Password dialog (shown after clicking Save as Demo)
                    if st.session_state.get("show_admin_password_dialog", False):
                        admin_password = st.text_input(
                            "Admin password",
                            type="password",
                            key="admin-password-input",
                            help="Enter the admin password to save this workspace as a demo"
                        )

                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Confirm", key="confirm-save-demo"):
                                if verify_admin_password(admin_password):
                                    success, message = save_workspace_as_demo(
                                        st.session_state.workspace,
                                        demo_name_clean
                                    )
                                    if success:
                                        st.success(message)
                                        st.session_state["show_admin_password_dialog"] = False
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(message)
                                else:
                                    st.error("Invalid admin password.")

                        with col2:
                            if st.button("Cancel", key="cancel-save-demo"):
                                st.session_state["show_admin_password_dialog"] = False
                                st.rerun()

        # All pages have settings, workflow indicator and logo
        with st.expander("⚙️ **Settings**"):
            img_formats = ["svg", "png", "jpeg", "webp"]
            st.selectbox(
                "image export format",
                img_formats,
                img_formats.index(params["image-format"]),
                key="image-format",
            )
            st.markdown("## Spectrum Plotting")
            st.selectbox("Bin Peaks", ["auto", True, False], key="spectrum_bin_peaks")
            if st.session_state["spectrum_bin_peaks"] == True:
                st.number_input(
                    "Number of Bins (m/z)", 1, 10000, 50, key="spectrum_num_bins"
                )
            else:
                st.session_state["spectrum_num_bins"] = 50

        with st.expander("📊 **Resource Utilization**"):
            monitor_hardware()
            # Show queue metrics in online mode
            if st.session_state.settings.get("online_deployment", False):
                monitor_queue()

        # Display OpenMS WebApp Template Version from settings.json
        with st.container():
            st.markdown(
                """
                <style>
                .version-box {
                    border: 1px solid #a4a5ad; 
                    padding: 10px;
                    border-radius: 0.5rem;
                    text-align: center;
                    display: flex;
                    justify-content: center;
                    align-items: center; 
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            version_info = st.session_state.settings["version"]
            app_name = st.session_state.settings["app-name"]
            st.markdown(
                f'<div class="version-box">{app_name}<br>Version: {version_info}</div>',
                unsafe_allow_html=True,
            )
    return params


def v_space(n: int, col=None) -> None:
    """
    Prints empty strings to create vertical space in the Streamlit app.

    Args:
        n (int): An integer representing the number of empty lines to print.
        col: A streamlit column can be passed to add vertical space there.

    Returns:
        None
    """
    for _ in range(n):
        if col:
            col.write("#")
        else:
            st.write("#")


def display_large_dataframe(
    df, chunk_sizes: list[int] = [10, 100, 1_000, 10_000], **kwargs
):
    """
    Displays a large DataFrame in chunks with pagination controls and row selection.

    Args:
        df: The DataFrame to display.
        chunk_sizes: A list of chunk sizes to choose from.
        ...: Additional keyword arguments to pass to the `st.dataframe` function. See: https://docs.streamlit.io/develop/api-reference/data/st.dataframe

    Returns:
        Index of selected row.
    """

    # Dropdown for selecting chunk size
    chunk_size = st.selectbox("Select Number of Rows to Display", chunk_sizes)

    # Calculate total number of chunks
    total_chunks = (len(df) + chunk_size - 1) // chunk_size

    if total_chunks > 1:
        page = int(st.number_input("Select Page", 1, total_chunks, 1, step=1))
    else:
        page = 1

    # Function to get the current chunk of the DataFrame
    def get_current_chunk(df, chunk_size, chunk_index):
        start = chunk_index * chunk_size
        end = min(
            start + chunk_size, len(df)
        )  # Ensure end does not exceed dataframe length
        return df.iloc[start:end], start, end

    # Display the current chunk
    current_chunk_df, start_row, end_row = get_current_chunk(df, chunk_size, page - 1)

    event = st.dataframe(current_chunk_df, **kwargs)

    st.write(
        f"Showing rows {start_row + 1} to {end_row} of {len(df)} ({get_dataframe_mem_useage(current_chunk_df):.2f} MB)"
    )

    rows = event["selection"]["rows"]

    if st.session_state.settings["test"]:  # is a test App, return first row as selected
        return 1
    elif not rows:
        return None
    else:
        # Calculate the index based on the current page and chunk size
        base_index = (page - 1) * chunk_size
        print(base_index)
        return base_index + rows[0]


def show_table(df: pd.DataFrame, download_name: str = "") -> None:
    """
    Displays a pandas dataframe using Streamlit's `dataframe` function and
    provides a download button for the same table.

    Args:
        df (pd.DataFrame): The pandas dataframe to display.
        download_name (str): The name to give to the downloaded file. Defaults to empty string.

    Returns:
        df (pd.DataFrame): The possibly edited dataframe.
    """
    # Show dataframe using container width
    st.dataframe(df, use_container_width=True)
    # Show download button with the given download name for the table if name is given
    if download_name:
        st.download_button(
            "Download Table",
            df.to_csv(sep="\t").encode("utf-8"),
            download_name.replace(" ", "-") + ".tsv",
        )
    return df


def show_fig(
    fig,
    download_name: str,
    container_width: bool = True,
    selection_session_state_key: str = "",
) -> None:
    """
    Displays a Plotly chart and adds a download button to the plot.

    Args:
        fig (plotly.graph_objs._figure.Figure): The Plotly figure to display.
        download_name (str): The name for the downloaded file.
        container_width (bool, optional): If True, the figure will use the container width. Defaults to True.
        selection_session_state_key (str, optional): If set, save the rectangular selection to session state with this key.

    Returns:
        None
    """
    if not selection_session_state_key:
        st.plotly_chart(
            fig,
            use_container_width=container_width,
            config={
                "displaylogo": False,
                "modeBarButtonsToRemove": [
                    "zoom",
                    "pan",
                    "select",
                    "lasso",
                    "zoomin",
                    "autoscale",
                    "zoomout",
                    "resetscale",
                ],
                "toImageButtonOptions": {
                    "filename": download_name,
                    "format": st.session_state["image-format"],
                },
            },
        )
    else:
        st.plotly_chart(
            fig,
            key=selection_session_state_key,
            selection_mode=["points", "box"],
            on_select="rerun",
            config={
                "displaylogo": False,
                "modeBarButtonsToRemove": [
                    "zoom",
                    "pan",
                    "lasso",
                    "zoomin",
                    "autoscale",
                    "zoomout",
                    "resetscale",
                    "select",
                ],
                "toImageButtonOptions": {
                    "filename": download_name,
                    "format": st.session_state["image-format"],
                },
            },
            use_container_width=True,
        )


def reset_directory(path: Path) -> None:
    """
    Remove the given directory and re-create it.

    Args:
        path (Path): Path to the directory to be reset.

    Returns:
        None
    """
    path = Path(path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def get_dataframe_mem_useage(df):
    """
    Get the memory usage of a pandas DataFrame in megabytes.

    Args:
        df (pd.DataFrame): The DataFrame to calculate the memory usage for.

    Returns:
        float: The memory usage of the DataFrame in megabytes.
    """
    # Calculate the memory usage of the DataFrame in bytes
    memory_usage_bytes = df.memory_usage(deep=True).sum()
    # Convert bytes to megabytes
    memory_usage_mb = memory_usage_bytes / (1024**2)
    return memory_usage_mb


def tk_directory_dialog(title: str = "Select Directory", parent_dir: str = os.getcwd()):
    """
    Creates a Tkinter directory dialog for selecting a directory.

    Args:
        title (str): The title of the directory dialog.
        parent_dir (str): The path to the parent directory of the directory dialog.

    Returns:
        str: The path to the selected directory.

    Warning:
        This function is not avaliable in a streamlit cloud context.
    """
    root = Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    file_path = filedialog.askdirectory(title=title, initialdir=parent_dir)
    root.destroy()
    return file_path


def tk_file_dialog(
    title: str = "Select File",
    file_types: list[tuple] = [],
    parent_dir: str = os.getcwd(),
    multiple: bool = True,
):
    """
    Creates a Tkinter file dialog for selecting a file.

    Args:
        title (str): The title of the file dialog.
        file_types (list(tuple)): The file types to filter the file dialog.
        parent_dir (str): The path to the parent directory of the file dialog.
        multiple (bool): If True, multiple files can be selected.

    Returns:
        str: The path to the selected file.

    Warning:
        This function is not avaliable in a streamlit cloud context.
    """
    root = Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    file_types.extend([("All files", "*.*")])
    file_path = filedialog.askopenfilename(
        title=title, filetypes=file_types, initialdir=parent_dir, multiple=True
    )
    root.destroy()
    return file_path


# General warning/error messages
WARNINGS = {
    "missing-mzML": "Upload or select some mzML files first!",
}

ERRORS = {
    "general": "Something went wrong.",
    "workflow": "Something went wrong during workflow execution.",
    "visualization": "Something went wrong during visualization of results.",
}
