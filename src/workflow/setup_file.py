"""A workflow's setup as one file to hand to a colleague or open later.

A setup file is a ZIP of what a run is started from, without any data or
results: the settings (``params.json``), the experimental design
(``experimental-design.tsv``), the input folder labels
(``input-folders.json``) and ``setup.json``, which lists the input files by
name and size and which of them each file selection picked.

Opening it in another workspace (or on another computer) brings the
settings, design and folders back and picks the same files again by name
among the files there. The files it names that are not there are reported,
so they can be uploaded and picked.

Streamlit-free, so it can be tested and used anywhere.
"""

import io
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from src.workflow.ExperimentalDesign import DESIGN_FILE, read_design
from src.workflow.InputFolders import FOLDERS_FILE
from src.workflow.RunManager import FOLLOW_UP_KEY

MANIFEST = "setup.json"
PARAMS = "params.json"
FORMAT = 1
#: Larger members are refused: settings, a design and labels are small.
MAX_MEMBER_BYTES = 20 * 1024 * 1024

PathLike = Union[str, Path]


def _name(path: str) -> str:
    return re.split(r"[\\/]", str(path))[-1]


def input_files(workflow_dir: PathLike) -> Dict[str, List[str]]:
    """The input files of each upload key: copied ones and referenced ones that exist."""
    root = Path(workflow_dir, "input-files")
    files: Dict[str, List[str]] = {}
    if not root.is_dir():
        return files
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        paths = [str(p) for p in sorted(folder.iterdir()) if p.name != "external_files.txt"]
        external = folder / "external_files.txt"
        if external.is_file():
            for line in external.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and os.path.exists(line):
                    paths.append(line)
        files[folder.name] = paths
    return files


def still_missing(workflow_dir: PathLike, missing: Optional[Dict[str, List[str]]]) -> Dict[str, List[str]]:
    """The names of ``missing`` (per upload key) that are still not among the workflow's input files."""
    if not missing:
        return {}
    here = input_files(workflow_dir)
    left = {}
    for key, names in missing.items():
        present = {_name(p) for p in here.get(key, [])}
        names = [n for n in names if n not in present]
        if names:
            left[key] = names
    return left


def _resolved(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except (OSError, RuntimeError):
        return str(path)


def _selections(params: dict, files: Dict[str, List[str]], workflow_dir: Path) -> Dict[str, dict]:
    """The settings that pick input files, as {setting: {key, files (names), multiple}}.

    A picked file that is gone since still counts by its folder, so the
    selection keeps its name and the other workspace is told about it.
    """
    owner = {}
    for key, paths in files.items():
        for path in paths:
            owner[_resolved(path)] = key
    root = _resolved(str(Path(workflow_dir, "input-files")))

    def key_of(value: str) -> Optional[str]:
        path = _resolved(value)
        if path in owner:
            return owner[path]
        parent = Path(path).parent
        return parent.name if str(parent.parent) == root and parent.name in files else None

    found = {}
    for setting, value in params.items():
        multiple = isinstance(value, list)
        values = value if multiple else [value]
        if not values or not all(isinstance(v, str) and v for v in values):
            continue
        keys = {key_of(v) for v in values}
        if len(keys) != 1 or None in keys:
            continue
        found[setting] = {"key": keys.pop(), "files": [_name(v) for v in values], "multiple": multiple}
    return found


def export_setup(
    workflow_dir: PathLike, app: str = "", version: str = "", workflow: str = ""
) -> bytes:
    """The workflow's setup as the bytes of a ZIP file."""
    workflow_dir = Path(workflow_dir)
    params_path = workflow_dir / PARAMS
    params = {}
    if params_path.is_file():
        params = json.loads(params_path.read_text(encoding="utf-8"))
    params.pop(FOLLOW_UP_KEY, None)
    files = input_files(workflow_dir)
    manifest = {
        "format": FORMAT,
        "app": app,
        "version": version,
        "workflow": workflow or workflow_dir.name,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": {
            key: [{"name": _name(p), "size": _size(p)} for p in paths] for key, paths in files.items()
        },
        "selections": _selections(params, files, workflow_dir),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(manifest, indent=2))
        archive.writestr(PARAMS, json.dumps(params, indent=2))
        for member in (DESIGN_FILE, FOLDERS_FILE):
            path = workflow_dir / member
            if path.is_file():
                archive.write(path, member)
    return buffer.getvalue()


def _size(path: str) -> Optional[int]:
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def is_setup_file(data: bytes) -> bool:
    """Whether ``data`` looks like a setup file (a ZIP) rather than a parameters JSON."""
    return data[:4] == b"PK\x03\x04"


def _check_selections(selections) -> None:
    """Raise ValueError unless ``selections`` is a manifest's file selections (or absent)."""
    if selections is None:
        return
    if not isinstance(selections, dict):
        raise ValueError("The setup file is damaged: its file selections are not a JSON object.")
    for setting, selection in selections.items():
        if not (
            isinstance(selection, dict)
            and isinstance(selection.get("key"), str)
            and isinstance(selection.get("files"), list)
            and all(isinstance(name, str) for name in selection["files"])
            and isinstance(selection.get("multiple"), bool)
        ):
            raise ValueError(f"The setup file is damaged: the file selection of {setting!r} is not valid.")


def read_setup(data: bytes) -> dict:
    """Check a setup file and return its parts: manifest, params, design and folders (text or None).

    Raises ValueError when it is not a setup file this version can open.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ValueError("Not a setup file (not a ZIP file).") from error
    with archive:
        names = set(archive.namelist())
        if MANIFEST not in names or PARAMS not in names:
            raise ValueError("Not a setup file: setup.json or params.json is missing.")
        parts = {}
        for member in (MANIFEST, PARAMS, DESIGN_FILE, FOLDERS_FILE):
            if member not in names:
                parts[member] = None
                continue
            if archive.getinfo(member).file_size > MAX_MEMBER_BYTES:
                raise ValueError(f"{member} in the setup file is too large.")
            try:
                parts[member] = archive.read(member).decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError(f"{member} in the setup file is not text.") from error
    try:
        manifest = json.loads(parts[MANIFEST])
        params = json.loads(parts[PARAMS])
        folders = json.loads(parts[FOLDERS_FILE]) if parts[FOLDERS_FILE] is not None else None
    except json.JSONDecodeError as error:
        raise ValueError(f"The setup file is damaged: {error}") from error
    if not isinstance(manifest, dict) or not isinstance(params, dict):
        raise ValueError("The setup file is damaged: its settings are not a JSON object.")
    if manifest.get("format") != FORMAT:
        raise ValueError(f"Setup file format {manifest.get('format')!r} is not supported.")
    _check_selections(manifest.get("selections"))
    if folders is not None and not isinstance(folders, dict):
        raise ValueError("The setup file is damaged: its folders are not a JSON object.")
    if parts[DESIGN_FILE] is not None:
        read_design(parts[DESIGN_FILE].encode("utf-8"))  # raises ValueError when it is not a design
    return {"manifest": manifest, "params": params, "design": parts[DESIGN_FILE], "folders": folders}


def _write(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def apply_setup(workflow_dir: PathLike, setup: dict) -> Tuple[dict, Dict[str, List[str]]]:
    """Write the setup's design and folder labels into ``workflow_dir``.

    Returns the settings to save, with each file selection pointed at the
    files of this workflow that have the same names, and the names it picked
    that are not here, per upload key. The caller saves the settings, so a
    workflow keeps one writer of its params.json.
    """
    workflow_dir = Path(workflow_dir)
    workflow_dir.mkdir(parents=True, exist_ok=True)
    params = dict(setup["params"])
    params.pop(FOLLOW_UP_KEY, None)
    here = input_files(workflow_dir)
    missing: Dict[str, List[str]] = {}
    _check_selections(setup["manifest"].get("selections"))
    selections = setup["manifest"].get("selections") or {}
    for setting, selection in selections.items():
        key = selection["key"]
        by_name = {_name(p): p for p in here.get(key, [])}
        names = selection["files"]
        picked = [by_name[n] for n in names if n in by_name]
        for name in names:
            if name not in by_name and name not in missing.setdefault(key, []):
                missing[key].append(name)
        if selection["multiple"]:
            params[setting] = picked
        elif picked:
            params[setting] = picked[0]
        else:
            params.pop(setting, None)
    missing = {key: names for key, names in missing.items() if names}

    if setup.get("design") is not None:
        _write(workflow_dir / DESIGN_FILE, setup["design"])
    if setup.get("folders"):
        path = workflow_dir / FOLDERS_FILE
        current = {}
        if path.is_file():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                current = {}
        if not isinstance(current, dict):
            current = {}
        for key, labels in setup["folders"].items():
            if isinstance(labels, dict):
                merged = dict(current.get(key) or {})
                merged.update({str(k): str(v) for k, v in labels.items()})
                current[key] = merged
        _write(path, json.dumps(current, indent=2))
    return params, missing
