"""Checks of the selected input files before a run (Streamlit-free).

Each selected mzML and FASTA file is read when it is selected, so a file a
tool cannot use stops the run before it starts instead of failing a tool
part-way (``check_file``): an mzML that is not one, is cut off or holds no
spectra, a FASTA that is not one or holds no proteins. Smaller issues (a
byte-order mark, lowercase residues, a repeated accession) are warnings.
A file is read once per size and modification time; an mzML only at its
start and end.

Workflows name their outputs after the input files (``FileManager.get_files``
keeps the file name and swaps the extension), so two selected files with the
same name but in different folders, or with different extensions (``a.mzML``
and ``a.raw``), write to the same result files and one replaces the other.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Bytes read at the start and the end of an mzML file
MZML_HEAD = 1 << 16
MZML_TAIL = 1 << 12
FASTA_SUFFIXES = (".fasta", ".fa", ".faa", ".fas")
# Examples named in a message
MAX_EXAMPLES = 3


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


# ----------------------------------------------------------------------------- file contents

@dataclass
class FileCheck:
    """What reading a file found: its spectra or proteins, and its problems.

    ``errors`` make a file unusable (the run does not start); ``warnings``
    are shown but the file is used.
    """
    path: str
    kind: str = ""  # "spectra" or "proteins"; "" for a file that is not checked
    count: Optional[int] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


_CACHE: Dict[Tuple[str, int, int], FileCheck] = {}


def _mzml(path: Path, size: int) -> FileCheck:
    check = FileCheck(str(path), "spectra")
    if size == 0:
        check.errors.append("is empty")
        return check
    with open(path, "rb") as f:
        head = f.read(MZML_HEAD)
        f.seek(max(0, size - MZML_TAIL))
        tail = f.read()
    if b"<mzML" not in head and b"<indexedmzML" not in head:
        check.errors.append("is not an mzML file")
        return check
    m = re.search(rb"<spectrumList\b[^>]*\bcount=\"(\d+)\"", head)
    if m:
        check.count = int(m.group(1))
        if check.count == 0:
            check.errors.append("holds no spectra")
    end = tail.rstrip()
    if not (end.endswith(b"</mzML>") or end.endswith(b"</indexedmzML>")):
        check.errors.append("is cut off: it ends before its last spectrum (copy or download it again)")
    return check


def _fasta(path: Path, size: int) -> FileCheck:
    check = FileCheck(str(path), "proteins")
    if size == 0:
        check.errors.append("is empty")
        return check
    with open(path, "rb") as f:
        bom = f.read(3) == b"\xef\xbb\xbf"
    entries, seen, repeated, lower, empty = 0, set(), [], 0, 0
    first, residues = True, 0
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if first and not line.startswith(">"):
                check.errors.append("is not a FASTA file: it does not start with a '>' header line")
                return check
            first = False
            if line.startswith(">"):
                if entries and residues == 0:
                    empty += 1
                entries += 1
                residues = 0
                accession = line[1:].split(maxsplit=1)[0] if line[1:].strip() else ""
                if accession in seen and len(repeated) < MAX_EXAMPLES:
                    repeated.append(accession)
                seen.add(accession)
            else:
                residues += len(line)
                if line != line.upper():
                    lower += 1
    if entries and residues == 0:
        empty += 1
    check.count = entries
    if entries == 0:
        check.errors.append("holds no proteins")
        return check
    if bom:
        check.warnings.append("starts with a byte-order mark, which some tools read as part of the first header")
    if repeated:
        check.warnings.append("repeats accessions (" + ", ".join(f"`{a}`" for a in repeated)
                              + "), so results cannot tell those proteins apart")
    if lower:
        check.warnings.append(f"has lowercase residues on {lower:,} lines, which some tools skip")
    if empty:
        check.warnings.append(f"has {empty:,} entries without a sequence")
    return check


def check_file(path) -> FileCheck:
    """Read an mzML or FASTA file for what makes it unusable. Other files
    (vendor raw data, results of other tools) and missing files are not checked."""
    path = Path(str(path))
    suffix = path.suffix.lower()
    if suffix != ".mzml" and suffix not in FASTA_SUFFIXES:
        return FileCheck(str(path))
    try:
        stat = path.stat()
    except OSError:
        return FileCheck(str(path))
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _CACHE:
        try:
            _CACHE[key] = (_mzml if suffix == ".mzml" else _fasta)(path, stat.st_size)
        except OSError as e:
            _CACHE[key] = FileCheck(str(path), errors=[f"cannot be read ({e.strerror or e})"])
    return _CACHE[key]


def check_files(files) -> List[FileCheck]:
    """``check_file`` of a selection (one path or a list)."""
    if isinstance(files, (str, Path)):
        files = [files]
    if not isinstance(files, (list, tuple)):
        return []
    return [check_file(f) for f in dict.fromkeys(str(f) for f in files if f)]


def selection_checks(workflow_dir, params: dict) -> Dict[str, List[FileCheck]]:
    """``check_files`` of each input file selection of a workflow's ``params``."""
    root = Path(workflow_dir, "input-files")
    return {
        key: check_files(value)
        for key, value in (params or {}).items()
        if isinstance(value, (str, list)) and value and Path(root, key).is_dir()
    }


def unusable_message(checks: List[FileCheck]) -> str:
    """The files that cannot be used and why ("" when all can)."""
    bad = list({c.path: c for c in checks if c.errors}.values())
    if not bad:
        return ""
    lines = [f"`{Path(c.path).name}` {' and '.join(c.errors)}." for c in bad]
    if len(bad) == 1:
        return f"This file cannot be used: {lines[0]} Replace it or leave it out."
    return f"{len(bad)} files cannot be used: " + " ".join(lines) + " Replace them or leave them out."


def warning_message(checks: List[FileCheck]) -> str:
    """The warnings of the usable files ("" when there are none)."""
    lines = [f"`{Path(c.path).name}` {' and '.join(c.warnings)}." for c in checks if c.warnings and not c.errors]
    return " ".join(lines)


def count_summary(checks: List[FileCheck]) -> str:
    """'12,480 spectra in 3 files', '20,431 proteins' ("" when nothing was counted)."""
    counted = [c for c in checks if c.count is not None and not c.errors]
    if not counted:
        return ""
    kinds = {}
    for c in counted:
        n, files = kinds.get(c.kind, (0, 0))
        kinds[c.kind] = (n + c.count, files + 1)
    parts = []
    for kind, (n, files) in kinds.items():
        parts.append(f"{n:,} {kind}" + (f" in {files} files" if files > 1 else ""))
    return ", ".join(parts)
