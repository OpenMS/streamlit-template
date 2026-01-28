"""
Admin utilities for the Streamlit template.

Provides functionality for admin-only operations like saving workspaces as demos.
"""

import hmac
import shutil
from pathlib import Path

import streamlit as st


def is_admin_configured() -> bool:
    """
    Check if admin password is configured in Streamlit secrets.

    Returns:
        bool: True if admin password is configured, False otherwise.
    """
    try:
        return bool(st.secrets.get("admin", {}).get("password"))
    except (FileNotFoundError, KeyError):
        return False


def verify_admin_password(password: str) -> bool:
    """
    Verify the provided password against the configured admin password.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        password: The password to verify.

    Returns:
        bool: True if password matches, False otherwise.
    """
    if not is_admin_configured():
        return False

    try:
        stored_password = st.secrets["admin"]["password"]
        # Use constant-time comparison for security
        return hmac.compare_digest(password, stored_password)
    except (FileNotFoundError, KeyError):
        return False


def get_demo_target_dir() -> Path:
    """
    Get the directory where demo workspaces are stored.

    Returns:
        Path: The demo workspaces directory.
    """
    return Path("example-data/workspaces")


def demo_exists(demo_name: str) -> bool:
    """
    Check if a demo workspace with the given name already exists.

    Args:
        demo_name: Name of the demo to check.

    Returns:
        bool: True if demo exists, False otherwise.
    """
    target_dir = get_demo_target_dir()
    demo_path = target_dir / demo_name
    return demo_path.exists()


def _remove_directory_with_symlinks(path: Path) -> None:
    """
    Remove a directory that may contain symlinks.

    Handles symlinks properly by removing them without following.

    Args:
        path: Path to the directory to remove.
    """
    if not path.exists():
        return

    for item in path.rglob("*"):
        if item.is_symlink():
            item.unlink()

    # Now remove the rest normally
    if path.exists():
        shutil.rmtree(path)


def save_workspace_as_demo(workspace_path: Path, demo_name: str) -> tuple[bool, str]:
    """
    Save the current workspace as a demo workspace.

    Copies all files from the workspace to the demo directory, following symlinks
    to copy actual file contents rather than symlink references.

    Args:
        workspace_path: Path to the source workspace.
        demo_name: Name for the new demo workspace.

    Returns:
        tuple[bool, str]: (success, message) tuple indicating result.
    """
    # Deferred import to avoid circular dependency with common.py
    from src.common.common import is_safe_workspace_name

    # Validate demo name
    if not demo_name:
        return False, "Demo name cannot be empty."

    if not is_safe_workspace_name(demo_name):
        return False, "Invalid demo name. Avoid path separators and special characters."

    # Validate source workspace exists
    if not workspace_path.exists():
        return False, "Source workspace does not exist."

    # Get target directory
    target_dir = get_demo_target_dir()
    demo_path = target_dir / demo_name

    try:
        # Ensure parent directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Remove existing demo if it exists (handles symlinks properly)
        if demo_path.exists():
            _remove_directory_with_symlinks(demo_path)

        # Copy workspace to demo directory, following symlinks to get actual files
        shutil.copytree(
            workspace_path,
            demo_path,
            symlinks=False,  # Follow symlinks, copy actual files
            dirs_exist_ok=False
        )

        return True, f"Workspace saved as demo '{demo_name}' successfully."

    except PermissionError:
        return False, "Permission denied. Cannot write to demo directory."
    except OSError as e:
        return False, f"Failed to save demo: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
