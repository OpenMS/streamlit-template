"""Folders a new workspace links from its demo, and how to write into them.

A workspace that starts from a demo (``copy_demo_workspace``) links the demo's
large files, and links whole the folders named by
``demo_workspaces.link_folders`` in settings.json, so it is set up with a few
dozen operations however many files the demo holds. A linked folder is the
demo's own: whatever is written into it changes the demo every new workspace
starts from. Code that writes into such a folder calls ``own_folder`` first,
which turns the link into a real folder of links to the demo's files; files
written then are the workspace's, and the demo stays as it is. A linked folder
is removed with ``remove_folder``, which drops the link and never the demo's
files (``shutil.rmtree`` refuses a link).

Streamlit-free, so the workflow process and the queue worker can use it.
"""

import os
import shutil
import uuid
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath


def matches(rel: PurePosixPath | str, patterns) -> bool:
    """Whether the folder at ``rel`` (relative to the demo) is linked whole.

    ``patterns`` are glob patterns of folder paths relative to the demo, with
    ``/`` as separator, such as ``cache/files/*``; a ``*`` stands for one
    folder name, never for several levels.
    """
    parts = PurePosixPath(rel).parts
    for pattern in patterns or ():
        wanted = PurePosixPath(str(pattern).strip("/")).parts
        if len(wanted) == len(parts) and all(map(fnmatchcase, parts, wanted)):
            return True
    return False


def own_folder(folder: Path, root: Path) -> Path:
    """Make ``folder`` the workspace's own before anything is written into it.

    A folder linked from a demo becomes a real folder holding a link to each
    of the demo folder's entries (a subfolder stays linked until it is owned
    in turn); any other folder, or one that does not exist yet, is left alone.
    Every linked folder between ``root`` (the workspace, or a folder of it
    that is never linked, such as a cache) and ``folder`` is owned first, so
    a folder created inside a linked one is created in the workspace. Safe
    when another process owns the same folder meanwhile.
    """
    folder, root = Path(folder), Path(root)
    try:
        rel = folder.relative_to(root)
    except ValueError:
        raise ValueError(f"{folder} is not inside {root}") from None
    current = root
    for part in rel.parts:
        current = Path(current, part)
        if current.is_symlink():
            _own(current)
    return folder


def _own(folder: Path) -> None:
    """Replace the link ``folder`` by a real folder of links to its entries."""
    source = folder.resolve()
    staging = folder.with_name(f".{folder.name}.own-{uuid.uuid4().hex[:8]}")
    staging.mkdir()
    try:
        if source.is_dir():
            for entry in os.scandir(source):
                Path(staging, entry.name).symlink_to(
                    Path(entry.path).resolve(), target_is_directory=entry.is_dir()
                )
        try:
            folder.unlink()
        except FileNotFoundError:
            pass  # another process took the link away meanwhile
        try:
            os.rename(staging, folder)
        except OSError:
            # Another process owned it first: keep its folder
            if not folder.is_dir() or folder.is_symlink():
                raise
            shutil.rmtree(staging, ignore_errors=True)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def remove_folder(folder: Path) -> None:
    """Remove ``folder``: a linked one loses only its link, the demo keeps its files."""
    folder = Path(folder)
    if folder.is_symlink():
        folder.unlink()
    elif folder.exists():
        shutil.rmtree(folder)
