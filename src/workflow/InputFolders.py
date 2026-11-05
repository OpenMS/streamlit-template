"""Folders for the input files of an upload widget, and groups suggested from file names.

A folder is a label on an input file: the files stay where they are
(``<workflow_dir>/input-files/<key>/`` or, referenced, wherever
``external_files.txt`` points), so every consumer that lists those
directories keeps working. The labels live in
``<workflow_dir>/input-folders.json`` as ``{key: {file name: folder}}``.

``suggest_groups()`` reads conditions, biological replicates and fractions
from file names such as ``ctrl_R1.mzML`` / ``ctrl_R2.mzML`` /
``treated_R1.mzML``. ``design_rows()`` turns folders (and, optionally, those
suggestions) into rows of the experimental design.

This module has no Streamlit dependency.
"""
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

FOLDERS_FILE = "input-folders.json"
# Sessions are threads of one server process: one save at a time, so two
# sessions on one workspace do not drop each other's folders
_LOCK = threading.Lock()

_COMPRESSION = re.compile(r"\.(gz|bz2|xz|zip)$", re.IGNORECASE)
_EXTENSION = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,5}$")
# A dot between digits is a decimal point (0.1x), not a separator
_SEPARATORS = re.compile(r"(?:[_\-\s]|(?<!\d)\.|\.(?!\d))+")
_FRACTION = re.compile(r"^(?:f|fr|frac|fraction)(\d{1,3})$", re.IGNORECASE)
_REPLICATE = re.compile(
    r"^(?:r|rep|repl|replicate|br|biorep)(\d{1,3})$", re.IGNORECASE
)
_TECHNICAL = re.compile(r"^(?:tr|tech|techrep)(\d{1,3})$", re.IGNORECASE)
_NUMBER = re.compile(r"^\d{1,3}$")
_LETTERS_NUMBER = re.compile(r"^([A-Za-z]+?)(\d{1,3})$")


def _name(path: str) -> str:
    return re.split(r"[\\/]", str(path).rstrip("\\/"))[-1]


# --- folders ----------------------------------------------------------------


def folders_path(workflow_dir: Union[str, Path]) -> Path:
    return Path(workflow_dir, FOLDERS_FILE)


def _load_all(workflow_dir) -> dict:
    path = folders_path(workflow_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_folders(workflow_dir: Union[str, Path], key: str) -> Dict[str, str]:
    """The folder of each file of upload ``key``, by file name; unfiled files are absent."""
    folders = _load_all(workflow_dir).get(key, {})
    if not isinstance(folders, dict):
        return {}
    return {str(f): str(d).strip() for f, d in folders.items() if str(d).strip()}


def save_folders(workflow_dir: Union[str, Path], key: str, folders: Dict[str, str]) -> None:
    """Store the folders of upload ``key``; an empty folder name takes the file out."""
    clean = {
        _name(f): str(d).strip()
        for f, d in folders.items()
        if d is not None and str(d).strip()
    }
    path = folders_path(workflow_dir)
    with _LOCK:
        data = _load_all(workflow_dir)
        if clean:
            data[key] = dict(sorted(clean.items()))
        else:
            data.pop(key, None)
        if data:
            # Written whole, then moved in place: a reader never sees half a file
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2)
                os.replace(tmp, path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        elif path.exists():
            path.unlink()


def rename_folder(workflow_dir, key: str, old: str, new: str) -> None:
    """Rename folder ``old`` of upload ``key``; an empty ``new`` removes the folder (its files stay)."""
    folders = load_folders(workflow_dir, key)
    save_folders(
        workflow_dir, key, {f: (new if d == old else d) for f, d in folders.items()}
    )


def folder_counts(folders: Dict[str, str], files: Sequence[str]) -> Dict[str, int]:
    """Files per folder among ``files`` (paths or names), in natural order of the folder names."""
    counts: Dict[str, int] = {}
    for f in files:
        d = folders.get(_name(f))
        if d:
            counts[d] = counts.get(d, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: natural_key(kv[0])))


def natural_key(text: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


# --- groups from file names --------------------------------------------------


@dataclass
class Suggestion:
    """The group, biological replicate and fraction a file name points to."""

    file: str
    group: str
    replicate: int
    fraction: int


@dataclass
class _Parsed:
    file: str
    tokens: List[str]
    replicate: Optional[int]
    fraction: Optional[int]


def _stem(name: str) -> str:
    name = _COMPRESSION.sub("", name)
    return _EXTENSION.sub("", name)


def _parse(name: str, split_letters: bool) -> _Parsed:
    tokens = [t for t in _SEPARATORS.split(_stem(name)) if t]
    replicate = fraction = None
    kept = []
    for t in tokens:
        if fraction is None and _FRACTION.match(t):
            fraction = int(_FRACTION.match(t).group(1))
        elif replicate is None and _REPLICATE.match(t):
            replicate = int(_REPLICATE.match(t).group(1))
        elif _TECHNICAL.match(t) and len(tokens) > 1:
            continue  # technical replicates share their sample
        else:
            kept.append(t)
    if replicate is None and len(kept) > 1 and _NUMBER.match(kept[-1]):
        replicate = int(kept.pop())
    elif replicate is None and split_letters and kept:
        m = _LETTERS_NUMBER.match(kept[-1])
        if m:
            kept[-1] = m.group(1)
            replicate = int(m.group(2))
    return _Parsed(name, kept, replicate, fraction)


def _drop_identifiers(parsed: List[_Parsed]) -> None:
    """Drop tokens with digits that occur in one file name only: run numbers, dates, injection ids."""
    seen: Dict[str, int] = {}
    for p in parsed:
        for t in set(p.tokens):
            seen[t] = seen.get(t, 0) + 1
    for p in parsed:
        p.tokens = [
            t for t in p.tokens if not (seen[t] == 1 and re.search(r"\d", t))
        ] or p.tokens


def _labels(parsed: List[_Parsed]) -> List[str]:
    """Each file's group label: its tokens without those every file name shares."""
    common = set(parsed[0].tokens)
    for p in parsed[1:]:
        common &= set(p.tokens)
    labels = []
    for p in parsed:
        rest = [t for t in p.tokens if t not in common]
        labels.append("_".join(rest))
    return labels


def _valid(labels: List[str]) -> bool:
    groups: Dict[str, int] = {}
    for label in labels:
        groups[label] = groups.get(label, 0) + 1
    return (
        "" not in groups
        and 2 <= len(groups) < len(labels)
        and max(groups.values()) >= 2
    )


def suggest_groups(files: Sequence[str]) -> List[Suggestion]:
    """Groups (conditions), biological replicates and fractions read from the file names.

    Separators are ``_``, ``-``, ``.`` and spaces. A token such as ``R2``,
    ``rep2`` or ``BR2`` is the replicate, ``F3`` or ``frac3`` the fraction,
    ``TR1`` a technical replicate (left out); otherwise a short number at the
    end is the replicate. Tokens all names share are left out of the group
    name, and so are numbers or dates found in one name only. Returns an
    empty list when the names show no grouping (fewer than two groups, or
    no group with two files).
    """
    names = [_name(f) for f in files]
    if len(names) < 3:
        return []
    for split_letters in (False, True):
        parsed = [_parse(n, split_letters) for n in names]
        labels = _labels(parsed)
        if not _valid(labels):
            _drop_identifiers(parsed)
            labels = _labels(parsed)
        if _valid(labels):
            return _number(parsed, labels)
    return []


def _number(parsed: List[_Parsed], labels: List[str]) -> List[Suggestion]:
    """Replicates as read from the names when they are unique in their group, else counted per group."""
    out = []
    by_group: Dict[str, List[int]] = {}
    for i, label in enumerate(labels):
        by_group.setdefault(label, []).append(i)
    replicate: Dict[int, int] = {}
    for idx in by_group.values():
        read = [(parsed[i].replicate, parsed[i].fraction or 1) for i in idx]
        if all(r is not None for r, _ in read) and len(set(read)) == len(read):
            for i in idx:
                replicate[i] = parsed[i].replicate
            continue
        if all(parsed[i].fraction is not None for i in idx) and all(
            parsed[i].replicate is None for i in idx
        ):
            for i in idx:  # one fractionated sample
                replicate[i] = 1
            continue
        for n, i in enumerate(sorted(idx, key=lambda i: natural_key(parsed[i].file)), 1):
            replicate[i] = n
    for i, p in enumerate(parsed):
        out.append(Suggestion(p.file, labels[i], replicate[i], p.fraction or 1))
    return out


def design_rows(
    files: Sequence[str], folders: Dict[str, str], suggest: bool = False
) -> Dict[str, Suggestion]:
    """Condition, replicate and fraction for each file name that has a folder
    (or, with ``suggest``, a group read from the names).

    The folder is the condition, unless (with ``suggest``) the names of its
    files suggest groups: a folder holding a whole experiment
    (``ctrl_R1``, ``ctrl_R2``, ``drug_R1``, ``drug_R2``) gets those groups as
    its conditions. Replicates come from the names when they are
    unique within the folder, else they are counted within it. Files with
    neither a folder nor a suggestion are absent.
    """
    names = [_name(f) for f in files]
    suggested = {s.file: s for s in suggest_groups(names)} if suggest else {}
    by_folder: Dict[str, List[str]] = {}
    for n in names:
        if folders.get(n):
            by_folder.setdefault(folders[n], []).append(n)
    condition = {}
    for folder, members in by_folder.items():
        # A folder that holds one experiment: the groups its names suggest
        within = {s.file: s.group for s in suggest_groups(members)} if suggest else {}
        for n in members:
            condition[n] = within.get(n, folder)
    for n in names:
        if n not in condition and n in suggested:
            condition[n] = suggested[n].group
    rows: Dict[str, Suggestion] = {}
    by_condition: Dict[str, List[str]] = {}
    for n, c in condition.items():
        by_condition.setdefault(c, []).append(n)
    for c, members in by_condition.items():
        parsed = [_parse(n, True) for n in members]
        read = [(p.replicate, p.fraction or 1) for p in parsed]
        from_names = all(r is not None for r, _ in read) and len(set(read)) == len(read)
        ordered = sorted(members, key=natural_key)
        for p in parsed:
            if from_names:
                rep = p.replicate
            elif p.fraction is not None and all(q.replicate is None for q in parsed):
                rep = 1
            else:
                rep = ordered.index(p.file) + 1
            rows[p.file] = Suggestion(p.file, c, rep, p.fraction or 1)
    return rows
