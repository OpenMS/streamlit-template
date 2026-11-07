"""What an assistant sees of a run's results: each component of the Results page.

A workflow whose Results page is built from components (``COMPONENTS``,
``PRESETS``, ``RESULTS_LAYOUT``, ``available()`` and ``renderers()`` on its
class, as in ``src/Workflow.py``) lets ``look()`` draw any of them headless:
the components' own renderers run in a Streamlit test session (AppTest, in a
process of its own) for the run asked for, and what they drew comes back as
data: tables with their columns, numbers and first rows, plots as their
traces (and as a PNG where plotly can write one), metrics, and the texts
and messages a person would read. Interactive components that only a
browser draws are named, with the result files to read instead.

Streamlit-free apart from the test session, which runs in the subprocess.
"""

import base64
import importlib
import json
import logging
import math
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("agent-access")

MARK = "⁣agent-component:"
MAX_POINTS = 60

HARNESS = r'''
import importlib
import streamlit as st
request = st.session_state["_agent_look"]
module, _, name = request["class"].partition(":")
workflow = getattr(importlib.import_module(module), name)()
renderers = workflow.renderers()
for component in request["components"]:
    st.text("%s" + component)
    try:
        renderers[component]()
    except Exception as e:  # noqa: BLE001 - one component must not hide the rest
        st.error(f"This component failed: {e}")
''' % MARK

SCRIPT = r'''
import json, sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
request = json.loads(sys.stdin.read())
at = AppTest.from_string(request["harness"], default_timeout=request["timeout"])
settings = json.loads(Path("settings.json").read_text(encoding="utf-8"))
settings["test"] = True
at.session_state.settings = settings
at.session_state.workspace = Path(request["workspace"])
at.session_state.location = request["location"]
at.session_state.controllo = True
# What the sidebar sets for a person (the image format of plot downloads, ...)
for name in ("default-parameters.json", str(Path(request["workspace"], "params.json"))):
    try:
        for key, value in json.loads(Path(name).read_text(encoding="utf-8")).items():
            if key != "controllo":
                at.session_state[key] = value
    except (OSError, ValueError, AttributeError):
        pass
at.session_state._agent_look = request
if request.get("run_id"):
    at.session_state["_runs-%s-selected" % request["workflow"]] = request["run_id"]
for key, rows in (request.get("select") or {}).items():
    at.session_state[key] = {"selection": {"rows": rows, "columns": []}}
at.run()
sys.path.insert(0, ".")
from src.agent_access.look import collect
print(json.dumps({"exception": [e.message for e in at.exception],
                  "components": collect(at.main, request)}, default=str))
'''


def catalog(entry: dict) -> dict | None:
    """The Results page's components and views of a workflow class, or None."""
    module, _, name = entry["class"].partition(":")
    try:
        cls = getattr(importlib.import_module(module), name)
    except Exception:  # noqa: BLE001 - reported as "no components"
        return None
    components = getattr(cls, "COMPONENTS", None)
    if not components or not hasattr(cls, "renderers"):
        return None
    return {"class": cls, "components": list(components),
            "presets": list(getattr(cls, "PRESETS", None) or []),
            "layout": getattr(cls, "RESULTS_LAYOUT", "layouts/results.json"),
            "analyses": dict(getattr(cls, "ANALYSES", None) or {})}


def available(cls, workflow_dir: Path, run_id) -> set | None:
    """The optional analyses a run has (None: the class does not say)."""
    if not hasattr(cls, "available"):
        return None
    if run_id is None:
        results = Path(workflow_dir, "results")
    else:
        from src.workflow.RunManager import RunManager
        results = RunManager(workflow_dir).results_dir(run_id)
    shell = object.__new__(cls)
    shell.workflow_dir, shell.results_dir, shell.run_id = Path(workflow_dir), results, run_id
    if run_id is not None:
        from src.workflow.RunManager import RunManager
        shell.runs = RunManager(workflow_dir)
    try:
        return set(cls.available(shell, run_id))
    except Exception:  # noqa: BLE001 - a class whose available() needs more
        try:
            return set(cls.available(shell))
        except Exception:  # noqa: BLE001
            return None


def look(app_root: Path, workspace: Path, workflow: str, class_name: str, run_id,
         components: list[str], online: bool, rows: int = 20, images: bool = True,
         select: dict | None = None, timeout: float = 120) -> dict:
    request = {"harness": HARNESS, "class": class_name, "workspace": str(workspace),
               "workflow": workflow, "run_id": run_id, "components": components,
               "location": "online" if online else "local", "timeout": timeout,
               "rows": rows, "images": images, "select": select or {}}
    try:
        proc = subprocess.run([sys.executable, "-c", SCRIPT], cwd=app_root, input=json.dumps(request),
                              capture_output=True, text=True, timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return {"error": "Drawing the components took too long."}
    except OSError as e:
        return {"error": f"The components could not be drawn: {e}"}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        logger.warning("looking at %s failed: %s", components, " ".join(tail))
        return {"error": "The components could not be drawn: " + " ".join(tail)}


# -- in the subprocess: what the test session drew ------------------------------

def collect(root, request: dict) -> dict:
    out: dict[str, list] = {}
    current = None
    for element in _walk(root):
        kind = getattr(element, "type", "")
        if kind == "text" and str(element.value).startswith(MARK):
            current = str(element.value)[len(MARK):]
            out[current] = []
            continue
        if current is None:
            continue
        item = _describe(element, kind, request)
        if item:
            out[current].append(item)
    return out


def _walk(node):
    children = getattr(node, "children", None)
    if isinstance(children, dict):
        for child in children.values():
            if getattr(child, "type", "") in ("flex_container", "vertical", "horizontal", "column",
                                              "tab", "expandable", "form", "main", "dialog"):
                yield from _walk(child)
            elif isinstance(getattr(child, "children", None), dict) and child.children:
                yield from _walk(child)
            else:
                yield child


def _describe(element, kind: str, request: dict) -> dict | None:
    if kind == "arrow_data_frame":
        table = _table(element.value, request["rows"])
        key = _select_key(element)
        if key:
            table["select_key"] = key
            chosen = (request.get("select") or {}).get(key)
            if chosen:
                table["selected_rows"] = chosen
        return table
    if kind == "metric":
        return {"type": "metric", "label": element.label, "value": element.value,
                "delta": element.delta or None}
    if kind in ("markdown", "caption", "text", "code", "latex", "title", "header", "subheader"):
        return {"type": "text", "text": str(element.value)[:4000]} if str(element.value).strip() else None
    if kind in ("info", "warning", "error", "success", "exception"):
        return {"type": kind, "text": str(getattr(element, "value", "") or getattr(element, "message", ""))[:2000]}
    if kind == "plotly_chart":
        return _plot(element.proto.spec, request.get("images", True))
    if kind in ("selectbox", "multiselect", "radio", "checkbox", "toggle", "slider", "number_input",
                "text_input", "segmented_control", "pills", "select_slider"):
        return {"type": "control", "label": getattr(element, "label", ""), "value": _plain(element.value)}
    if kind in ("button", "download_button", "empty", "divider", "toast", "balloons"):
        return None
    name = ""
    proto = getattr(element, "proto", None)
    for field in ("component_instance", "bidi_component"):
        try:
            name = getattr(getattr(proto, field), "component_name", "") or name
        except AttributeError:
            pass
    return {"type": "interactive", "element": kind, "component": name,
            "note": "Drawn by the browser only; read the run's result files for its data."}


def _select_key(element) -> str:
    """The session key of a table a person can pick rows in ('' if none)."""
    proto = getattr(element, "proto", None)
    if not proto or not list(getattr(proto, "selection_mode", []) or []):
        return ""
    parts = str(getattr(proto, "id", "")).split("-", 2)
    return parts[2] if len(parts) == 3 and parts[0] == "$$ID" else ""


def _plain(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _table(df, rows: int) -> dict:
    out = {"type": "table", "rows": int(df.shape[0]), "columns": [str(c) for c in df.columns]}
    numeric = df.select_dtypes("number")
    if not numeric.empty:
        stats = numeric.describe().loc[["min", "50%", "mean", "max"]].T
        stats.columns = ["min", "median", "mean", "max"]
        out["numbers"] = {str(k): {s: _num(v) for s, v in row.items()} for k, row in stats.iterrows()}
    head = df.head(rows).reset_index()
    out["first_rows"] = json.loads(head.to_json(orient="records", default_handler=str))
    return out


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v, 6)


def _plot(spec: str, images: bool) -> dict:
    try:
        fig = json.loads(spec)
    except ValueError:
        return {"type": "plot", "note": "unreadable figure"}
    layout = fig.get("layout") or {}

    def title(obj):
        t = (obj or {}).get("title")
        return (t.get("text") if isinstance(t, dict) else t) or None

    out = {"type": "plot", "title": title(layout),
           "x_axis": title(layout.get("xaxis")), "y_axis": title(layout.get("yaxis")), "traces": []}
    for trace in fig.get("data") or []:
        entry = {"kind": trace.get("type", "scatter"), "name": trace.get("name") or None}
        for axis in ("x", "y", "z"):
            values = trace.get(axis)
            if isinstance(values, dict) and "bdata" in values:
                values = _decode(values)
            if isinstance(values, list):
                entry[f"{axis}_count"] = len(values)
                entry[axis] = values[:MAX_POINTS]
        out["traces"].append(entry)
    if images:
        png = _png(fig)
        if png:
            out["image_png_base64"] = png
    return out


def _decode(values: dict):
    try:
        import numpy as np
        array = np.frombuffer(base64.b64decode(values["bdata"]), dtype=values.get("dtype", "f8"))
        return array.tolist()
    except Exception:  # noqa: BLE001
        return None


def _png(fig: dict) -> str:
    """The plot as a PNG, where plotly can write images (kaleido installed)."""
    try:
        import plotly.io as pio
        return base64.b64encode(pio.to_image(pio.from_json(json.dumps(fig)), format="png",
                                             width=900, height=500)).decode()
    except Exception:  # noqa: BLE001 - no image engine: the traces must do
        return ""
