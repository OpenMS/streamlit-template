"""What an assistant needs to know to set up a workflow, without Streamlit.

A workflow's settings live in ``<workflow>/params.json`` (see
``ParameterManager``): general settings at the top level, a TOPP tool's
parameters in a dict under the tool's (instance) name, keyed by the path
after ``<Tool>:1:``, and the tool's defaults the app chose in ``_defaults``.
What each TOPP parameter means comes from the tool's ``ini/<Tool>.ini``,
which the configure page writes (``prepare`` runs that page once when a
workspace has never shown it).
"""

import json
import logging
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger("agent-access")

# Keys of params.json that are the framework's own, not settings.
INTERNAL_KEYS = {"_defaults", "_flag_params", "_follow_up", "_purpose", "max_threads", "controllo"}
# Options every TOPP tool has; the workflow sets them, not the user.
COMMON_TOPP = {"in", "out", "ini", "log", "instance", "debug", "threads", "no_progress",
               "force", "test", "write_ini", "write_ctd", "write_nested_cwl",
               "write_nested_json"}
FILE_TYPES = {"input-file", "output-file", "input-prefix", "output-prefix"}
MAX_DESCRIPTION = 400


def read_params(workflow_dir: Path) -> dict:
    try:
        data = json.loads(Path(workflow_dir, "params.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_params(workflow_dir: Path, params: dict) -> None:
    workflow_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(workflow_dir, "params.json.agent-tmp")
    tmp.write_text(json.dumps(params, indent=4), encoding="utf-8")
    os.replace(tmp, Path(workflow_dir, "params.json"))


def topp_tools(params: dict, workflow_dir: Path) -> list[str]:
    """The TOPP tools (or instance names) of a workflow: those with settings
    in params.json and those whose .ini the configure page wrote."""
    tools = {k for k, v in params.items() if isinstance(v, dict) and not k.startswith("_")
             and ":" not in k}
    tools |= set((params.get("_defaults") or {}).keys())
    tools |= set((params.get("_flag_params") or {}).keys())
    tools |= {p.stem for p in Path(workflow_dir, "ini").glob("*.ini")}
    return sorted(tools)


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else str(tag)


def _convert(value: str, typ: str):
    try:
        if typ == "int":
            return int(value)
        if typ == "double":
            return float(value)
    except (TypeError, ValueError):
        return value
    return value


def ini_parameters(ini_path: Path) -> dict[str, dict]:
    """Every parameter of a ParamXML .ini, keyed by its path after ``<Tool>:1:``."""
    try:
        root = ET.parse(ini_path).getroot()
    except (ET.ParseError, OSError):
        return {}
    out: dict[str, dict] = {}

    def walk(el, parts):
        for ch in el:
            tag = _local(ch.tag)
            if tag == "NODE":
                walk(ch, parts + [ch.get("name") or ""])
            elif tag in ("ITEM", "ITEMLIST"):
                # parts: [tool, "1", ...]; the tool's own version item sits above "1"
                if len(parts) < 2:
                    continue
                path = ":".join([p for p in parts[2:] if p] + [ch.get("name") or ""])
                typ = (ch.get("type") or "string").lower()
                tags = {t.strip() for t in (ch.get("tags") or "").split(",") if t.strip()}
                if typ in FILE_TYPES or (len(parts) == 2 and path in COMMON_TOPP):
                    continue
                restrictions = ch.get("restrictions") or ""
                if tag == "ITEMLIST":
                    value = [_convert(li.get("value"), typ) for li in ch if _local(li.tag) == "LISTITEM"]
                else:
                    value = _convert(ch.get("value"), typ)
                if typ == "string" and restrictions in ("true,false", "false,true"):
                    typ, value = "bool", str(value).lower() == "true"
                entry = {"type": typ + ("[]" if tag == "ITEMLIST" else ""), "default": value,
                         "description": (ch.get("description") or "")[:MAX_DESCRIPTION],
                         "advanced": ch.get("advanced") == "true" or "advanced" in tags}
                if restrictions and typ != "bool":
                    if typ in ("int", "double") and ":" in restrictions:
                        low, _, high = restrictions.partition(":")
                        if low:
                            entry["min"] = _convert(low, typ)
                        if high:
                            entry["max"] = _convert(high, typ)
                    else:
                        entry["choices"] = restrictions.split(",")
                out[path] = entry
    walk(root, [])
    return out


def tool_ini(workflow_dir: Path, tool: str, real_tool: str | None = None) -> Path | None:
    for name in (tool, real_tool):
        if name and Path(workflow_dir, "ini", f"{name}.ini").is_file():
            return Path(workflow_dir, "ini", f"{name}.ini")
    return None


def describe_tool(workflow_dir: Path, params: dict, tool: str, include_advanced: bool,
                  names: dict) -> dict:
    stored = params.get(tool) if isinstance(params.get(tool), dict) else {}
    defaults = (params.get("_defaults") or {}).get(tool) or {}
    ini = tool_ini(workflow_dir, tool)
    info = {"tool": tool, "parameters": {}}
    if ini is None:
        info["note"] = ("No description of this tool's parameters yet; values set "
                        "under its name are passed on the command line as given.")
        info["parameters"] = {k: {"value": v} for k, v in {**defaults, **stored}.items()}
        return info
    entries = ini_parameters(ini)
    hidden = 0
    for path, entry in entries.items():
        changed = path in stored or path in defaults
        if entry["advanced"] and not include_advanced and not changed:
            hidden += 1
            continue
        default = defaults.get(path, entry["default"])
        item = dict(entry, default=default, value=stored.get(path, default))
        label = names.get(path)
        if label:
            item["label"] = label
        info["parameters"][path] = item
    if hidden:
        info["advanced_hidden"] = hidden
    return info


def presets(workflow: str, app_root: Path = Path(".")) -> dict[str, str]:
    try:
        data = json.loads(Path(app_root, "presets.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = data.get(workflow) or {}
    return {name: (p.get("_description") or "") for name, p in entries.items()
            if isinstance(p, dict) and not name.startswith("_")}


def preset(workflow: str, name: str, app_root: Path = Path(".")) -> dict | None:
    try:
        data = json.loads(Path(app_root, "presets.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    found = (data.get(workflow) or {}).get(name)
    return found if isinstance(found, dict) else None


def apply_preset(params: dict, values: dict) -> dict:
    """``values`` (a presets.json entry) on top of ``params``, as ParameterManager does."""
    params = dict(params)
    for key, value in values.items():
        if key == "_description":
            continue
        if key == "_general" and isinstance(value, dict):
            params.update(value)
        elif isinstance(value, dict) and not key.startswith("_"):
            params[key] = {**(params.get(key) or {}), **value}
    return params


def parameter_names(app_root: Path = Path(".")) -> dict:
    try:
        from src.workflow.parameter_names import load_parameter_names
        return load_parameter_names(Path(app_root, "parameter-names.json"))
    except Exception:  # noqa: BLE001 - labels are a nicety
        return {}


def label_map(names: dict, tool: str) -> dict[str, str]:
    out = {}
    for path, value in (names.get(tool) or {}).items():
        label = value.get("name") if isinstance(value, dict) else value
        if isinstance(label, str):
            out[path] = label
    return out


def general_settings(params: dict) -> dict:
    return {k: v for k, v in params.items()
            if k not in INTERNAL_KEYS and not k.startswith("_") and not isinstance(v, dict)}


PREPARE_SCRIPT = r"""
import json, sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
page, workspace, location = sys.argv[1], sys.argv[2], sys.argv[3]
at = AppTest.from_file(page, default_timeout=float(sys.argv[4]))
settings = json.loads(Path("settings.json").read_text(encoding="utf-8"))
settings["test"] = True
at.session_state.settings = settings
at.session_state.workspace = Path(workspace)
at.session_state.location = location
at.session_state.controllo = True
at.session_state.previous_dir = str(Path.cwd())
at.session_state.local_dir = ""
at.query_params["workspace"] = Path(workspace).name
at.run()
if at.exception:
    print(at.exception[0].message, file=sys.stderr)
    sys.exit(1)
"""


def prepare(app_root: Path, workspace: Path, configure_page: str, online: bool,
            timeout: float = 120) -> str:
    """Show the workflow's configure page once, headless, so it writes the
    workflow's settings with their defaults (and the tools' .ini files) as it
    does for a person. Returns an error message, or "" on success."""
    if not configure_page or not Path(app_root, configure_page).is_file():
        return "this app names no configure page for the workflow"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", PREPARE_SCRIPT, configure_page, str(workspace),
             "online" if online else "local", str(timeout)],
            cwd=app_root, capture_output=True, text=True, timeout=timeout + 30,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return "the configure page took too long"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        logger.warning("preparing %s failed: %s", configure_page, " ".join(tail))
        return "the configure page could not be shown: " + " ".join(tail)
    return ""
