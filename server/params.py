"""
Parameter schemas and persistence for the configure page.

Reads and writes ``<workflow_dir>/params.json`` in exactly the format the
Streamlit ParameterManager uses, so either app can open the other's workspace:

- general widgets:   ``{"<key>": value}``
- python tools:      ``{"<script>.py:<key>": value}``
- TOPP tools:        ``{"<instance>": {"<param:path>": value}}``, non-defaults only
- custom defaults:   ``{"_defaults": {"<instance>": {...}}}``
- CLI flags:         ``{"_flag_params": {"<instance>": [...]}}``
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pyopenms as poms

from src.workflow.ParameterManager import ParameterManager

from .workflow_spec import TOPP, Python, SelectFiles, Widget

# Same base exclusions as StreamlitUI._input_TOPP_impl
BASE_EXCLUDES = ["log", "debug", "threads", "no_progress", "force", "version", "test"]


def _s(v):
    return v.decode() if isinstance(v, bytes) else v


def _matches(pattern: str, param_path: str) -> bool:
    pattern = pattern.lstrip(":")
    return param_path == pattern or param_path.endswith(":" + pattern)


def _py(value):
    """pyOpenMS values to JSON-able Python values."""
    value = _s(value)
    if isinstance(value, list):
        return [_s(v) for v in value]
    return value


def _param_type(value, valid_strings: list[str]) -> str:
    if isinstance(value, list):
        if value and isinstance(value[0], int):
            return "int-list"
        if value and isinstance(value[0], float):
            return "double-list"
        return "string-list"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "double"
    if sorted(valid_strings) == ["false", "true"]:
        return "bool"
    return "string"


def load_ini(pm: ParameterManager, tool: str) -> poms.Param | None:
    if not pm.create_ini(tool):
        return None
    param = poms.Param()
    poms.ParamXMLFile().load(str(Path(pm.ini_dir, f"{tool}.ini")), param)
    return param


def _read_strict(pm: ParameterManager) -> dict:
    # Raises InvalidParameterFileError on a broken file: callers must not
    # write back over a file they could not read (see ParameterManager).
    return pm.read_parameters_strict()


def register_topp(pm: ParameterManager, item: TOPP) -> None:
    """Seed _defaults and _flag_params, as input_TOPP() does on render."""
    params = _read_strict(pm)
    changed = False
    flags = params.setdefault("_flag_params", {})
    if flags.get(item.instance) != list(item.flag_parameters):
        flags[item.instance] = list(item.flag_parameters)
        changed = True
    if item.custom_defaults:
        defaults = params.setdefault("_defaults", {})
        if defaults.get(item.instance) != item.custom_defaults:
            defaults[item.instance] = dict(item.custom_defaults)
            changed = True
    if changed:
        pm.write_parameters(params)


def topp_schema(pm: ParameterManager, item: TOPP) -> dict:
    """Every visible parameter of a TOPP tool with its effective value."""
    param = load_ini(pm, item.tool)
    if param is None:
        return {"tool": item.tool, "instance": item.instance, "available": False, "params": []}
    register_topp(pm, item)
    stored = pm.get_parameters_from_json()
    defaults = stored.get("_defaults", {}).get(item.instance, {})
    user = stored.get(item.instance, {})
    excludes = BASE_EXCLUDES + list(item.exclude_parameters)
    prefix = f"{item.tool}:1:"

    out = []
    for raw_key in param.keys():
        key = _s(raw_key)
        if not key.startswith(prefix):
            continue
        tags = [_s(t) for t in param.getTags(raw_key)]
        if "input file" in tags or "output file" in tags:
            continue
        short = key[len(prefix):]
        if any(_matches(p, short) for p in excludes):
            continue
        entry = param.getEntry(raw_key)
        ini_value = _py(entry.value)
        valid = [_s(v) for v in entry.valid_strings]
        ptype = _param_type(ini_value, valid)
        default = defaults.get(short, ini_value)
        value = user.get(short, default)
        if isinstance(ini_value, list) and isinstance(value, str):
            value = value.split("\n") if value else []
        if ptype == "bool" and isinstance(value, bool):
            value = "true" if value else "false"
        if ptype == "bool" and isinstance(default, bool):
            default = "true" if default else "false"
        section = ":".join(short.split(":")[:-1]) if item.display_subsections else ""
        p: dict[str, Any] = {
            "key": short,
            "name": _s(entry.name),
            "type": ptype,
            "value": value,
            "default": default,
            "valid_strings": [] if ptype == "bool" else valid,
            "description": _s(entry.description),
            "advanced": "advanced" in tags,
            "included": (not item.include_parameters)
            or any(_matches(k, short) for k in item.include_parameters),
            "section": section,
            "section_description": _s(param.getSectionDescription(prefix + section)) if section else "",
            "modified": short in user and user[short] != default,
        }
        if ptype in ("int", "int-list"):
            p["min"], p["max"] = _bound(entry.min_int, -(2**31) + 1), _bound(entry.max_int, 2**31 - 1)
        elif ptype in ("double", "double-list"):
            p["min"], p["max"] = _bound(entry.min_float, -1.7e308), _bound(entry.max_float, 1.7e308)
        out.append(p)
    return {"tool": item.tool, "instance": item.instance, "available": True, "params": out}


def _bound(value, sentinel):
    # pyOpenMS reports "no restriction" as the type's extreme value
    try:
        if abs(float(value)) >= abs(float(sentinel)) * 0.999:
            return None
    except (TypeError, ValueError):
        return None
    return value


def save_topp(pm: ParameterManager, item: TOPP, values: dict[str, Any]) -> dict:
    """
    Store the given values of one tool instance, keeping only those that differ
    from the effective default (custom default if any, else the ini value).
    """
    schema = {p["key"]: p for p in topp_schema(pm, item)["params"]}
    params = _read_strict(pm)
    user = params.setdefault(item.instance, {})
    for key, value in values.items():
        if key not in schema:
            continue
        p = schema[key]
        value = _coerce(p["type"], value)
        if value == p["default"] and not (p["type"].endswith("list") and value == []):
            user.pop(key, None)
        else:
            user[key] = value
    if not user:
        params.pop(item.instance, None)
    pm.write_parameters(params)
    return topp_schema(pm, item)


def _coerce(ptype: str, value):
    if ptype == "bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        return "true" if str(value).lower() == "true" else "false"
    if ptype == "int":
        return int(value)
    if ptype == "double":
        return float(value)
    if ptype.endswith("list"):
        if isinstance(value, str):
            value = [v for v in value.split("\n") if v.strip()]
        if ptype == "int-list":
            return [int(v) for v in value]
        if ptype == "double-list":
            return [float(v) for v in value]
        return [str(v) for v in value]
    return "" if value is None else str(value)


# ------------------------------------------------------------------ python tools


def python_tool_path(script: str) -> Path:
    if not script.endswith(".py"):
        script += ".py"
    path = Path(script)
    if not path.exists():
        path = Path("src", "python-tools", script)
    return path


def python_defaults(script: str) -> list[dict]:
    path = python_tool_path(script)
    if not path.exists():
        return []
    if str(path.parent) not in sys.path:
        sys.path.append(str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    defaults = getattr(module, "DEFAULTS", None)
    return defaults if isinstance(defaults, list) else []


def python_schema(pm: ParameterManager, item: Python) -> dict:
    path = python_tool_path(item.script)
    stored = pm.get_parameters_from_json()
    out = []
    for entry in python_defaults(item.script):
        if "key" not in entry or "value" not in entry or entry.get("hide", False):
            continue
        key = f"{path.name}:{entry['key']}"
        out.append(
            {
                "key": key,
                "name": entry.get("name", entry["key"]),
                "help": entry.get("help", ""),
                "value": stored.get(key, entry["value"]),
                "default": entry["value"],
                "widget_type": entry.get("widget_type", "auto"),
                "options": entry.get("options"),
                "min": entry.get("min"),
                "max": entry.get("max"),
                "step_size": entry.get("step_size", 1),
                "advanced": entry.get("advanced", False),
            }
        )
    return {"script": path.name, "available": path.exists(), "params": out}


# ------------------------------------------------------------- general widgets


def input_files(workflow_dir: Path, key: str) -> list[str]:
    """Files offered for an input key: copies plus still-existing references."""
    path = Path(workflow_dir, "input-files", key)
    if not path.exists():
        return []
    options = sorted(str(f) for f in path.iterdir() if f.name != "external_files.txt")
    ext = path / "external_files.txt"
    if ext.exists():
        options += [f for f in ext.read_text().splitlines() if f and os.path.exists(f)]
    return options


def widget_schema(pm: ParameterManager, workflow_dir: Path, item) -> dict:
    stored = pm.get_parameters_from_json()
    if isinstance(item, SelectFiles):
        options = input_files(workflow_dir, item.key)
        value = stored.get(item.key, [] if item.multiple else (options[0] if options else None))
        if isinstance(value, list):
            value = [v for v in value if v in options]
        elif value not in options:
            value = options[0] if options else None
        return {
            "key": item.key,
            "options": [{"value": o, "label": Path(o).name} for o in options],
            "value": value,
        }
    assert isinstance(item, Widget)
    value = stored.get(item.key, item.default)
    if value is None and item.options is not None:
        value = [] if item.widget_type == "multiselect" else item.options[0]
    return {"key": item.key, "value": value}


def save_general(pm: ParameterManager, values: dict[str, Any]) -> None:
    """Top-level keys: widget values and python-tool values."""
    params = _read_strict(pm)
    for k, v in values.items():
        if k.startswith("_") or ":1:" in k or k == "max_threads" and not isinstance(v, int):
            continue
        params[k] = v
    pm.write_parameters(params)


# --------------------------------------------------------------------- summary


def summary(params: dict) -> dict:
    """Non-default parameters grouped like StreamlitUI.non_default_params_summary."""

    def clean(v):
        if isinstance(v, list):
            return [Path(str(x)).name if Path(str(x)).exists() else x for x in v]
        if isinstance(v, str) and Path(v).exists():
            return Path(v).name
        return v

    general, python, topp = {}, {}, {}
    for k, v in params.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            topp[k] = {kk: clean(vv) for kk, vv in v.items()}
        elif ".py:" in k:
            script, key = k.split(".py:", 1)
            python.setdefault(script + ".py", {})[key] = clean(v)
        else:
            general[k] = clean(v)
    for tool, vals in params.get("_defaults", {}).items():
        topp[tool] = {**vals, **topp.get(tool, {})}
    return {"general": general, "topp": topp, "python": python}
