"""Whether the disk holding a workflow has room for the run about to start.

A large study can fill the disk part-way through: the tools then fail on the
file being written, often hours in, with an error that does not say why. The
space a run needs is estimated from its input files:

    size of the selected input files * space_factor

(``space_factor`` is how much a run writes per byte of input; an app sets it
on its workflow class as ``disk_space_factor``). When the free space of the
disk under the workflow folder is below the estimate, the Run button and the
Run page say so before the run starts. The run is not blocked: the estimate
is rough, and the user may free space while the run goes.

Streamlit-free, so it can be tested and used outside a page.
"""
import os
import shutil
from pathlib import Path

from .job_timeout import _is_input_path

# How much a run writes per byte of input, when a workflow does not say.
DEFAULT_FACTOR = 2.0


def _size(path: Path) -> int:
    """Bytes of a file, or of every file in a vendor folder (Bruker .d)."""
    try:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += Path(root, name).stat().st_size
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def input_bytes(params: dict) -> int:
    """Total size of the distinct input files the parameters of a run select."""
    found = set()
    for key, value in (params or {}).items():
        if key.startswith("_"):
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if isinstance(v, str) and v and _is_input_path(v):
                found.add(str(Path(v).resolve()))
    return sum(_size(Path(p)) for p in found)


def free_bytes(path) -> int | None:
    """Free bytes on the disk holding ``path`` (its nearest existing parent);
    None when it cannot be read."""
    path = Path(path)
    while not path.exists() and path.parent != path:
        path = path.parent
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def format_bytes(n: int) -> str:
    """'512 MB', '3.4 GB', '1.2 TB'."""
    size = float(max(0, n))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000:
            return f"{size:.0f} {unit}" if unit in ("B", "KB", "MB") else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} TB"


def space_warning(params: dict, workflow_dir, factor: float = DEFAULT_FACTOR,
                  free: int | None = None) -> str:
    """A warning when the run's estimated output does not fit ("" when it does,
    when ``factor`` is 0 or less, or when the free space is unknown)."""
    if not factor or factor <= 0:
        return ""
    if free is None:
        free = free_bytes(workflow_dir)
    if free is None:
        return ""
    size = input_bytes(params)
    needed = int(size * factor)
    if needed <= free:
        return ""
    return (
        f"This analysis may need about {format_bytes(needed)} of disk space "
        f"({format_bytes(size)} of input files), but only {format_bytes(free)} "
        "is free. It may stop part-way when the disk is full: free some space "
        "or select fewer files."
    )
