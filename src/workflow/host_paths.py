"""Display host paths without resolving them inside the application container."""

import re
from pathlib import PurePosixPath, PureWindowsPath


def folder_file_uri(folder: str) -> str | None:
    """Return an encoded directory URI for an absolute host path on either OS.

    A Docker server's filesystem cannot resolve a host-relative path. Leave
    such paths as text rather than inventing a host path from the container cwd.
    """
    if not folder or any(ord(character) < 32 for character in folder):
        return None
    # Windows device namespaces are not ordinary file URLs.
    if folder.startswith(("\\\\?\\", "\\\\.\\")):
        return None
    windows = PureWindowsPath(folder)
    if windows.is_absolute():
        path = windows
    else:
        path = PurePosixPath(folder)
        if not path.is_absolute():
            return None
    uri = path.as_uri()
    return uri if uri.endswith("/") else uri + "/"


def folder_reference(folder: str) -> str:
    """Format a literal Markdown path, linking only valid absolute host paths."""
    visible = folder.replace("\r", r"\r").replace("\n", r"\n")
    # Code spans keep punctuation, backslashes and Markdown-looking filenames
    # literal. Padding separates any backticks in the filename from the fence.
    fence = "`" * (max((len(run) for run in re.findall(r"`+", visible)), default=0) + 1)
    label = f"{fence} {visible} {fence}"
    uri = folder_file_uri(folder)
    return f"[{label}](<{uri}>)" if uri else label
