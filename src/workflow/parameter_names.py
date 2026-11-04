"""Display names for TOPP tool parameters, read from ``parameter-names.json``.

A TOPP tool names its parameters for the command line (``algorithm:mtd:mass_error_ppm``,
``SD:tol``). An app can give the ones its configure page shows a name its users
understand, per tool, and optionally its own help text::

    {
        "FeatureFinderMetabo": {
            "algorithm:common:noise_threshold_int": "Noise threshold (intensity)",
            "algorithm:mtd:mass_error_ppm": {
                "name": "Mass tolerance (ppm)",
                "help": "How far apart, in ppm, the peaks of one mass trace may be."
            }
        }
    }

The top-level key is the tool (or a ``tool_instance_name``, which is looked up
first), the inner key the parameter path after ``<Tool>:1:``. A section path
(``"algorithm:mtd": "Mass trace detection"``) names the heading of that
section. Keys starting with ``_`` are comments. Parameters and sections without
an entry keep the tool's own name.

Only the label changes: parameters are stored, preset and passed to the tool
under their real names. Streamlit-free.
"""

import json
from pathlib import Path

PARAMETER_NAMES_FILE = "parameter-names.json"

# path -> ((mtime_ns, size), parsed file); reread when the file changes
_CACHE: dict = {}


def load_parameter_names(path=PARAMETER_NAMES_FILE) -> dict:
    """All tools' parameter names, ``{}`` when the file is missing or invalid."""
    file = Path(path)
    try:
        stat = file.stat()
        mtime = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return {}
    cached = _CACHE.get(str(file))
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    _CACHE[str(file)] = (mtime, data)
    return data


def display_name(tool: str, parameter: str, instance: str = None, path=PARAMETER_NAMES_FILE):
    """The display name and help of one parameter, or ``None`` without an entry.

    Args:
        tool: The TOPP tool, e.g. ``"FLASHDeconv"``.
        parameter: The parameter path after ``<Tool>:1:``, e.g. ``"SD:tol"``.
        instance: The ``tool_instance_name``, if any; its entry wins.

    Returns:
        ``{"name": str, "help": str or None}`` or ``None``.
    """
    names = load_parameter_names(path)
    for owner in (instance, tool):
        if not owner:
            continue
        tool_names = names.get(owner)
        if not isinstance(tool_names, dict):
            continue
        entry = tool_names.get(parameter)
        if isinstance(entry, str) and entry.strip():
            return {"name": entry.strip(), "help": None}
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str) and name.strip():
            help_text = entry.get("help")
            return {
                "name": name.strip(),
                "help": str(help_text) if help_text else None,
            }
    return None
