"""How long a queued run may take before the queue stops it.

A fixed limit cannot fit a run of two files and one of two hundred: two
hours stopped every large study part-way, and a limit large enough for those
would let a hung run of one file hold a worker for days. The limit therefore
grows with the input files of the run:

    default_timeout + timeout_per_input * input files, at most max_timeout

from ``queue_settings`` in settings.json (defaults 2 h, 30 min per file,
7 days). A workflow with other needs overrides ``WorkflowManager.job_timeout()``.

Streamlit-free: the sync service queues runs with it too.
"""
from pathlib import Path

DEFAULT_TIMEOUT = 7200
TIMEOUT_PER_INPUT = 1800
MAX_TIMEOUT = 7 * 24 * 3600


def _is_input_path(value: str) -> bool:
    """A parameter value naming an input file or a vendor folder (Bruker .d)."""
    path = Path(value)
    # A path with a folder in it, never a bare word such as "ppm" that may
    # happen to name something in the working directory.
    if len(path.parts) < 2:
        return False
    try:
        return path.is_file() or (path.is_dir() and path.suffix.lower() == ".d")
    except OSError:
        return False


def count_input_files(params: dict) -> int:
    """The distinct input files the parameters of a run select.

    Selections are stored as a path or a list of paths (select_input_file);
    TOPP and python-tool parameters are plain values, which do not name files.
    """
    found = set()
    for key, value in (params or {}).items():
        if key.startswith("_"):
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if isinstance(v, str) and v and _is_input_path(v):
                found.add(v)
    return len(found)


def job_timeout(n_inputs: int, queue_settings: dict | None = None) -> int:
    """The time limit (s) of a queued run of ``n_inputs`` input files."""
    qs = queue_settings or {}
    base = int(qs.get("default_timeout", DEFAULT_TIMEOUT))
    per_input = int(qs.get("timeout_per_input", TIMEOUT_PER_INPUT))
    ceiling = max(int(qs.get("max_timeout", MAX_TIMEOUT)), base)
    return min(base + per_input * max(0, int(n_inputs)), ceiling)


def format_duration(seconds: int) -> str:
    """'45 min', '3 h', '4 h 30 min', '7 days' ('30 s' under a minute)."""
    if int(seconds) < 60:
        return f"{int(seconds)} s"
    minutes = int(seconds) // 60
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    if days and not hours and not mins:
        return f"{days} day{'s' if days != 1 else ''}"
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if mins or not parts:
        parts.append(f"{mins} min")
    return " ".join(parts)
