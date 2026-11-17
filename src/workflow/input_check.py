"""Checks of the selected input files before a run (Streamlit-free).

Workflows name their outputs after the input files (``FileManager.get_files``
keeps the file name and swaps the extension), so two selected files with the
same name but in different folders, or with different extensions (``a.mzML``
and ``a.raw``), write to the same result files and one replaces the other.
"""

import os
from pathlib import Path
from typing import Dict, List


def name_clashes(files) -> List[List[str]]:
    """Groups of ``files`` whose outputs would share a name.

    Files clash when their names without the last extension are equal,
    ignoring case (Windows and macOS file systems do). The same path given
    twice is not a clash. Groups keep the order of ``files``.
    """
    if not isinstance(files, (list, tuple)):
        return []
    groups: Dict[str, List[str]] = {}
    for f in files:
        if not isinstance(f, (str, Path)) or not str(f):
            continue
        paths = groups.setdefault(Path(f).stem.casefold(), [])
        if all(os.path.normpath(str(p)) != os.path.normpath(str(f)) for p in paths):
            paths.append(str(f))
    return [g for g in groups.values() if len(g) > 1]


def selection_clashes(workflow_dir, params: dict) -> Dict[str, List[List[str]]]:
    """Name clashes in each input file selection of a workflow's ``params``.

    A selection is a parameter named like a folder of ``input-files/`` (what
    ``select_input_file`` stores), so other list parameters are left alone.
    """
    root = Path(workflow_dir, "input-files")
    found = {}
    for key, value in (params or {}).items():
        if not isinstance(value, list) or len(value) < 2 or not Path(root, key).is_dir():
            continue
        groups = name_clashes(value)
        if groups:
            found[key] = groups
    return found


def _label(path: str) -> str:
    """The file's name with its folder, which tells apart files of one name."""
    p = Path(path)
    return f"{p.parent.name}/{p.name}" if p.parent.name else p.name


def clash_message(groups: List[List[str]]) -> str:
    """A sentence per clash, for the selection widget and the Run page."""
    lines = []
    for g in groups:
        files = ", ".join(f"`{_label(f)}`" for f in g)
        lines.append(f"**{Path(g[0]).stem}** is the name of {len(g)} selected files ({files}).")
    return (
        " ".join(lines)
        + " Their results would be written to the same files, so one would replace "
        "the other. Rename one of them or leave it out."
    )
