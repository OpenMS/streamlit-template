"""The tools an assistant gets, for one workspace.

Every tool works inside the workspace its token (or the stdio server's
``--workspace``) names, on the same files the workflow pages use:

    <workflow>/input-files/<key>/   input files (external_files.txt: referenced ones)
    <workflow>/params.json          the settings of the next run
    <workflow>/runs/<id>/           a run of a multi-run workflow, else <workflow>/results/

A tool raises ``ToolError`` with a message the assistant can act on; the
protocol layer returns it as a tool result with ``isError`` set.
"""

import base64
import binascii
import difflib
import importlib
import json
import logging
import os
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlencode

from . import activity, describe, runner

logger = logging.getLogger("agent-access")

EXTERNAL_FILES = "external_files.txt"
_SAFE_NAME = re.compile(r"^[^/\\\x00]{1,200}$")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
TABLE_SUFFIXES = {".tsv": "\t", ".csv": ",", ".txt": "\t"}
TEXT_SUFFIXES = {".md", ".log", ".json", ".txt", ".tsv", ".csv", ".yaml", ".yml", ".html",
                 ".mztab", ".xml", ".ini", ".msalign", ".feature", ".fasta", ".svg"}
MAX_ROWS = 500
MAX_TEXT = 200_000
MAX_LISTED = 2000


class ToolError(Exception):
    """A tool call that cannot be done; the message tells the assistant why."""


def _schema(properties: dict, required: tuple = ()) -> dict:
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


WORKFLOW = {"type": "string", "description": "The workflow, as get_app_info lists it."}
RUN_ID = {"type": "string", "description": "A run from list_runs. Default: the newest finished run."}
KEY = {"type": "string", "description": "The input, as describe_workflow lists it (e.g. mzML-files)."}

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}
WRITES = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}

DEFINITIONS = [
    ("get_app_info", "App overview",
     "What this app is, the workflows it offers, and a link to open the workspace in the "
     "browser. Start here.", _schema({}), READ_ONLY),
    ("describe_workflow", "Describe a workflow",
     "A workflow's inputs and the files in them, its settings with their current values, "
     "each tool's parameters (type, default, allowed values, description), its presets and "
     "whether it is running. Read it before update_settings or start_run.",
     _schema({"workflow": WORKFLOW,
              "include_advanced": {"type": "boolean", "default": False,
                                   "description": "Also list advanced tool parameters."},
              "tool": {"type": "string", "description": "Only this tool's parameters."}},
             ("workflow",)), READ_ONLY),
    ("list_files", "List input files",
     "The input files of a workflow, per input.",
     _schema({"workflow": WORKFLOW, "key": KEY}, ("workflow",)), READ_ONLY),
    ("upload_file", "Upload an input file",
     "Add a file to an input of a workflow, base64-encoded. Files larger than one call "
     "allows are sent in parts: every part but the last with complete=false, all with the "
     "same filename and append=true after the first. A .zip of a Bruker .d folder is "
     "unpacked.",
     _schema({"workflow": WORKFLOW, "key": KEY,
              "filename": {"type": "string"},
              "content_base64": {"type": "string"},
              "append": {"type": "boolean", "default": False,
                         "description": "Add to the part sent before."},
              "complete": {"type": "boolean", "default": True,
                           "description": "False while more parts follow."}},
             ("workflow", "key", "filename", "content_base64")),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
      "openWorldHint": False}),
    ("import_from_link", "Import files from a link",
     "Download input files from a link: a PRIDE accession (PXD...), a Zenodo or Figshare "
     "record, a public S3 or Swift folder, a OneDrive share, or any file URL. Without "
     "`files`, a link with several files is listed so you can choose; with `files` (paths "
     "from that list) or a single-file link, the download starts in the background. "
     "Follow it with get_import_status.",
     _schema({"workflow": WORKFLOW, "url": {"type": "string"},
              "files": {"type": "array", "items": {"type": "string"},
                        "description": "Paths from the listing to download."}},
             ("workflow", "url")),
     {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}),
    ("get_import_status", "Follow an import",
     "Progress of the last import_from_link of a workflow.",
     _schema({"workflow": WORKFLOW}, ("workflow",)), READ_ONLY),
    ("delete_file", "Delete an input file",
     "Remove an input file from a workflow (a referenced file is only unlisted).",
     _schema({"workflow": WORKFLOW, "key": KEY, "filename": {"type": "string"}},
             ("workflow", "key", "filename")),
     {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}),
    ("update_settings", "Change settings",
     "Change the settings of a workflow's next run, as on its configure page. Keys are "
     "general settings by name, or a tool's parameter as \"<Tool>:<path>\" (e.g. "
     "\"FeatureFinderMetabo:algorithm:common:noise_threshold_int\"); a preset is applied "
     "first. Values are checked against the parameter's type and allowed values.",
     _schema({"workflow": WORKFLOW,
              "settings": {"type": "object", "description": "Setting -> value."},
              "preset": {"type": "string", "description": "A preset from describe_workflow."}},
             ("workflow",)), WRITES),
    ("start_run", "Start a run",
     "Start the workflow with the chosen input files, as the Run page does. `inputs` maps "
     "an input to file names from list_files; `settings` and `preset` are applied first as "
     "in update_settings. The run shows on the app's Run page. Follow it with "
     "get_run_status.",
     _schema({"workflow": WORKFLOW,
              "inputs": {"type": "object", "description": "Input -> list of file names.",
                         "additionalProperties": {"type": "array", "items": {"type": "string"}}},
              "settings": {"type": "object"}, "preset": {"type": "string"},
              "name": {"type": "string", "description": "A name for the run."}},
             ("workflow",)),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
      "openWorldHint": False}),
    ("get_run_status", "Run status",
     "Whether the workflow's last run is queued, running, finished, failed or cancelled, "
     "its current step and the last lines of its log.",
     _schema({"workflow": WORKFLOW}, ("workflow",)), READ_ONLY),
    ("get_run_log", "Run log",
     "The end of the last run's log: minimal (the steps), commands (every command with its "
     "run time) or all (everything the tools printed).",
     _schema({"workflow": WORKFLOW,
              "lines": {"type": "integer", "default": 100, "minimum": 1, "maximum": 2000},
              "detail": {"type": "string", "enum": ["minimal", "commands", "all"]}},
             ("workflow",)), READ_ONLY),
    ("stop_run", "Stop the run", "Stop the workflow's running or queued run.",
     _schema({"workflow": WORKFLOW}, ("workflow",)),
     {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}),
    ("list_runs", "List runs",
     "The runs of a workflow with their names, states and times, newest first.",
     _schema({"workflow": WORKFLOW}, ("workflow",)), READ_ONLY),
    ("list_results", "List result files",
     "The result files of a run, with sizes and download links.",
     _schema({"workflow": WORKFLOW, "run_id": RUN_ID}, ("workflow",)), READ_ONLY),
    ("read_result", "Read a result file",
     "Read a result file: a table (TSV, CSV, Parquet) as rows, with offset and limit for "
     "paging, a text file as text. Other files get a download link.",
     _schema({"workflow": WORKFLOW, "run_id": RUN_ID,
              "path": {"type": "string", "description": "As list_results gives it."},
              "offset": {"type": "integer", "default": 0, "minimum": 0},
              "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": MAX_ROWS},
              "columns": {"type": "array", "items": {"type": "string"}}},
             ("workflow", "path")), READ_ONLY),
    ("get_processing_report", "Processing report",
     "What a run did, per input file: every tool, its version and the parameters that "
     "differ from the defaults, as Markdown. Cite it in a methods section.",
     _schema({"workflow": WORKFLOW, "run_id": RUN_ID}, ("workflow",)), READ_ONLY),
    ("get_app_link", "Link to the app",
     "A link that opens this workspace in the browser, on a workflow's configure, run or "
     "results page, for the person to look at what you did.",
     _schema({"workflow": WORKFLOW,
              "page": {"type": "string", "enum": ["configure", "run", "results"]}}),
     READ_ONLY),
]


def _yaml_inputs(app_root: Path) -> tuple[dict, dict]:
    """app.yaml's inputs ({key: types}) and workflow inputs ({class: [keys]})."""
    try:
        import yaml
        spec = yaml.safe_load(Path(app_root, "app.yaml").read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - app.yaml is optional here
        return {}, {}
    types = {k: [str(t) for t in (v or {}).get("types", [])]
             for k, v in (spec.get("inputs") or {}).items() if isinstance(v, dict)}
    per_class = {}
    for wf in spec.get("workflows") or []:
        cls = str(wf.get("class") or "")
        module, _, name = cls.partition(":")
        module = module.removesuffix(".py").replace("/", ".")
        per_class[f"{module}:{name}"] = list(wf.get("inputs") or [])
    return types, per_class


class Tools:
    def __init__(self, app_root: Path, workspace: Path, cfg: dict, app_url: str = "",
                 download_url: str = "", sync_cfg: dict | None = None):
        self.app_root = Path(app_root)
        self.workspace = Path(workspace)
        self.cfg = cfg
        self.online = cfg["online"]
        self.app_url = app_url.rstrip("/")
        self.download_url = download_url
        self.sync_cfg = sync_cfg or {}
        self._handlers = {name: getattr(self, f"_{name}") for name, *_ in DEFINITIONS}
        self._input_types, self._class_inputs = _yaml_inputs(self.app_root)

    # -- protocol hooks --------------------------------------------------------

    def server_name(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", (self.cfg["app_name"] or "openms-app").lower()).strip("-")

    def server_title(self) -> str:
        return self.cfg["app_name"] or "OpenMS app"

    def server_version(self) -> str:
        return str(self.cfg["version"] or "0")

    def instructions(self) -> str:
        names = ", ".join(self.cfg["workflows"]) or "none"
        return (
            f"You are connected to one workspace of {self.server_title()}, an OpenMS web app "
            f"for mass spectrometry data analysis. Workflows: {names}. Call get_app_info, then "
            "describe_workflow; add input files with upload_file or import_from_link, start "
            "the workflow with start_run, follow it with get_run_status and read its results "
            "with list_results and read_result. The person can follow every step in the app: "
            "get_app_link gives them the link."
        )

    def definitions(self) -> list[dict]:
        return [{"name": name, "title": title, "description": desc, "inputSchema": schema,
                 "annotations": dict(annotations, title=title)}
                for name, title, desc, schema, annotations in DEFINITIONS]

    def has(self, name: str) -> bool:
        return name in self._handlers

    def call(self, name: str, arguments: dict) -> dict:
        error = ""
        try:
            return self._handlers[name](**arguments)
        except TypeError as e:
            error = f"Wrong arguments for {name}: {e}"
            raise ToolError(error) from e
        except runner.RunError as e:
            error = str(e)
            raise ToolError(error) from e
        except ToolError as e:
            error = str(e)
            raise
        finally:
            activity.record(self.workspace, name, arguments.get("workflow"), error)

    # -- helpers ---------------------------------------------------------------

    def _workflow(self, workflow) -> tuple[str, dict, Path]:
        entry = self.cfg["workflows"].get(workflow) if isinstance(workflow, str) else None
        if entry is None:
            raise ToolError(f"Unknown workflow {workflow!r}. Workflows: "
                            f"{', '.join(self.cfg['workflows']) or 'none'}.")
        return workflow, entry, Path(self.workspace, workflow)

    def _multi_run(self, entry: dict) -> bool:
        module, _, cls = entry["class"].partition(":")
        try:
            return bool(getattr(getattr(importlib.import_module(module), cls), "multi_run", False))
        except Exception:  # noqa: BLE001 - a class that does not import cannot run either
            logger.exception("cannot import %s", entry["class"])
            raise ToolError(f"The workflow class {entry['class']} cannot be loaded.")

    def _input_keys(self, entry: dict, workflow_dir: Path, params: dict) -> dict[str, list]:
        """Input -> allowed file types (empty: any)."""
        keys = {k: self._input_types.get(k, []) for k in self._class_inputs.get(entry["class"], [])}
        files_dir = Path(workflow_dir, "input-files")
        if files_dir.is_dir():
            for d in files_dir.iterdir():
                if d.is_dir() and _KEY.match(d.name):
                    keys.setdefault(d.name, self._input_types.get(d.name, []))
        return keys

    def _check_key(self, key, keys: dict) -> str:
        if not isinstance(key, str) or not _KEY.match(key):
            raise ToolError(f"Not an input name: {key!r}.")
        if keys and key not in keys:
            raise ToolError(f"Unknown input {key!r}. Inputs: {', '.join(keys)}.")
        return key

    @staticmethod
    def _check_name(filename) -> str:
        if not isinstance(filename, str) or not _SAFE_NAME.match(filename) \
                or filename.startswith(".") or filename == EXTERNAL_FILES:
            raise ToolError(f"Not a file name: {filename!r} (no folders, no leading dot).")
        return filename

    def _files(self, workflow_dir: Path, key: str) -> list[dict]:
        folder = Path(workflow_dir, "input-files", key)
        out = []
        if folder.is_dir():
            for p in sorted(folder.iterdir()):
                if p.name == EXTERNAL_FILES or p.name.startswith("."):
                    continue
                out.append({"name": p.name, "size": _size(p), "folder": p.is_dir()})
            ext = Path(folder, EXTERNAL_FILES)
            if ext.is_file():
                for line in ext.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line:
                        out.append({"name": Path(line).name, "size": _size(Path(line)),
                                    "folder": Path(line).is_dir(), "referenced": True})
        return out[:MAX_LISTED]

    def _file_path(self, workflow_dir: Path, key: str, name: str) -> Path:
        folder = Path(workflow_dir, "input-files", key)
        target = Path(folder, self._check_name(name))
        if target.exists():
            return target
        ext = Path(folder, EXTERNAL_FILES)
        if ext.is_file():
            for line in ext.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip() and Path(line.strip()).name == name:
                    return Path(line.strip())
        raise ToolError(f"No file {name!r} in input {key!r}. Files: "
                        f"{', '.join(f['name'] for f in self._files(workflow_dir, key)) or 'none'}.")

    def _ensure_described(self, entry: dict, workflow_dir: Path) -> str:
        """Show the configure page once if this workspace never did."""
        if describe.read_params(workflow_dir) and Path(workflow_dir, "ini").is_dir():
            return ""
        return describe.prepare(self.app_root, self.workspace, entry["configure_page"], self.online)

    def _results_dir(self, workflow_dir: Path, entry: dict, run_id) -> tuple[Path, str | None]:
        if not self._multi_run(entry):
            return Path(workflow_dir, "results"), None
        runs = runner._runs(workflow_dir)
        if run_id is None:
            run_id = runs.latest()
            if run_id is None:
                raise ToolError("This workflow has no finished run yet.")
        if not isinstance(run_id, str) or runs.get(run_id) is None:
            raise ToolError(f"No run {run_id!r}. See list_runs.")
        return runs.results_dir(run_id), run_id

    def _download_link(self, workflow_dir: Path, path: Path) -> str:
        if not self.online:
            return str(path.resolve())
        rel = path.resolve().relative_to(self.workspace.resolve()).as_posix()
        return f"{self.download_url}?{urlencode({'path': rel})}" if self.download_url else ""

    def _page_link(self, page_file: str) -> str:
        if not self.app_url:
            return ""
        stem = Path(page_file).stem if page_file else ""
        query = urlencode({"workspace": self.workspace.name})
        return f"{self.app_url}/{quote(stem)}?{query}" if stem else f"{self.app_url}/?{query}"

    # -- settings --------------------------------------------------------------

    def _apply_settings(self, workflow: str, workflow_dir: Path, params: dict,
                        settings, preset) -> tuple[dict, list[str]]:
        changed = []
        if preset is not None:
            values = describe.preset(workflow, preset, self.app_root)
            if values is None:
                raise ToolError(f"No preset {preset!r}. Presets: "
                                f"{', '.join(describe.presets(workflow, self.app_root)) or 'none'}.")
            params = describe.apply_preset(params, values)
            changed.append(f"preset {preset}")
        if settings is None:
            return params, changed
        if not isinstance(settings, dict):
            raise ToolError("settings must be an object: setting -> value.")
        tools = describe.topp_tools(params, workflow_dir)
        general = describe.general_settings(params)
        for key, value in settings.items():
            if not isinstance(key, str):
                raise ToolError(f"Not a setting: {key!r}.")
            tool, sep, path = key.partition(":")
            if sep and tool in tools:
                path = path[2:] if path.startswith("1:") else path
                value = self._check_topp(workflow_dir, tool, path, value)
                params[tool] = {**(params.get(tool) or {}), path: value}
                changed.append(key)
            elif key in describe.INTERNAL_KEYS or key.startswith("_"):
                raise ToolError(f"{key!r} is set by the app, not a setting.")
            elif isinstance(value, dict) and key in tools:
                for path, v in value.items():
                    params[key] = {**(params.get(key) or {}),
                                   path: self._check_topp(workflow_dir, key, path, v)}
                    changed.append(f"{key}:{path}")
            elif key in general or not general:
                if key in general and isinstance(general[key], list) != isinstance(value, list):
                    raise ToolError(f"{key!r} takes {'a list' if isinstance(general[key], list) else 'a single value'}.")
                params[key] = value
                changed.append(key)
            else:
                close = difflib.get_close_matches(key, list(general) + [f"{t}:" for t in tools], 3)
                raise ToolError(f"Unknown setting {key!r}." + (f" Did you mean {', '.join(close)}?" if close else
                                " describe_workflow lists the settings."))
        return params, changed

    def _check_topp(self, workflow_dir: Path, tool: str, path: str, value):
        ini = describe.tool_ini(workflow_dir, tool)
        if ini is None:
            return value
        entries = describe.ini_parameters(ini)
        entry = entries.get(path)
        if entry is None:
            close = difflib.get_close_matches(path, list(entries), 3)
            raise ToolError(f"{tool} has no parameter {path!r}."
                            + (f" Did you mean {', '.join(close)}?" if close else ""))
        typ = entry["type"]
        try:
            if typ.endswith("[]"):
                if not isinstance(value, list):
                    value = [value]
                base = typ[:-2]
                value = [_coerce(v, base) for v in value]
                bad = [v for v in value if "choices" in entry and str(v) not in entry["choices"]]
            else:
                value = _coerce(value, typ)
                bad = [value] if "choices" in entry and str(value) not in entry["choices"] else []
        except (TypeError, ValueError):
            raise ToolError(f"{tool}:{path} takes a {typ}, not {value!r}.")
        if bad:
            raise ToolError(f"{tool}:{path} takes one of {', '.join(entry['choices'])}, not {bad[0]!r}.")
        for v in value if isinstance(value, list) else [value]:
            if "min" in entry and isinstance(v, (int, float)) and v < entry["min"]:
                raise ToolError(f"{tool}:{path} is at least {entry['min']}.")
            if "max" in entry and isinstance(v, (int, float)) and v > entry["max"]:
                raise ToolError(f"{tool}:{path} is at most {entry['max']}.")
        return value

    # -- tools -----------------------------------------------------------------

    def _get_app_info(self) -> dict:
        workflows = []
        for name, entry in self.cfg["workflows"].items():
            workflow_dir = Path(self.workspace, name)
            params = describe.read_params(workflow_dir)
            workflows.append({"workflow": name, "description": entry["description"],
                              "inputs": list(self._input_keys(entry, workflow_dir, params))})
        return {"app": self.server_title(), "version": self.server_version(),
                "workspace": self.workspace.name,
                "deployment": "online" if self.online else "local",
                "workflows": workflows,
                "link": self._page_link(""),
                "limits": {"upload_mb_per_call": self.cfg["max_upload_mb"],
                           "import_gb": self.cfg["max_import_gb"]}}

    def _describe_workflow(self, workflow, include_advanced=False, tool=None) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        note = self._ensure_described(entry, workflow_dir)
        params = describe.read_params(workflow_dir)
        names = describe.parameter_names(self.app_root)
        keys = self._input_keys(entry, workflow_dir, params)
        inputs = {}
        for key, types in keys.items():
            selected = params.get(key)
            selected = [selected] if isinstance(selected, str) else selected or []
            inputs[key] = {"file_types": types, "files": self._files(workflow_dir, key),
                           "selected": [Path(s).name for s in selected if isinstance(s, str)],
                           "multiple": not isinstance(params.get(key), str)}
        tools = [t for t in describe.topp_tools(params, workflow_dir) if tool in (None, t)]
        if tool is not None and not tools:
            raise ToolError(f"No tool {tool!r} in {workflow}.")
        out = {
            "workflow": workflow,
            "inputs": inputs,
            "settings": {k: v for k, v in describe.general_settings(params).items() if k not in keys},
            "tools": {t: describe.describe_tool(workflow_dir, params, t, bool(include_advanced),
                                                describe.label_map(names, t)) for t in tools},
            "presets": describe.presets(workflow, self.app_root),
            "multi_run": self._multi_run(entry),
        }
        if note:
            out["note"] = (f"The workflow's defaults are not known yet ({note}). Open its "
                           "configure page once in the app, or set the settings you need.")
        return out

    def _list_files(self, workflow, key=None) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        keys = self._input_keys(entry, workflow_dir, describe.read_params(workflow_dir))
        if key is not None:
            keys = {self._check_key(key, keys): keys.get(key, [])}
        return {"workflow": workflow, "inputs": {k: self._files(workflow_dir, k) for k in keys}}

    def _upload_file(self, workflow, key, filename, content_base64, append=False,
                     complete=True) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        keys = self._input_keys(entry, workflow_dir, describe.read_params(workflow_dir))
        key = self._check_key(key, keys)
        filename = self._check_name(filename)
        types = keys.get(key) or []
        is_d_zip = "d" in [t.lower() for t in types] and filename.lower().endswith(".zip")
        if types and not is_d_zip and not any(filename.lower().endswith(f".{t.lower()}") for t in types):
            raise ToolError(f"{key} takes {', '.join(types)} files, not {filename!r}.")
        if not isinstance(content_base64, str):
            raise ToolError("content_base64 must be a string.")
        limit = int(self.cfg["max_upload_mb"] * 1024 ** 2)
        if len(content_base64) > limit * 4 // 3 + 8:
            raise ToolError(f"One call takes at most {self.cfg['max_upload_mb']} MB; "
                            "send the file in parts (append=true, complete=false).")
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ToolError("content_base64 is not valid base64.")
        folder = Path(workflow_dir, "input-files", key)
        folder.mkdir(parents=True, exist_ok=True)
        part = Path(folder, f".{filename}.agent-part")
        if append and not part.exists():
            raise ToolError(f"No earlier part of {filename!r}; send the first part with append=false.")
        self._check_quota(len(data))
        with open(part, "ab" if append else "wb") as f:
            f.write(data)
        size = part.stat().st_size
        if not complete:
            return {"filename": filename, "received": size, "complete": False}
        if is_d_zip:
            from src.workflow.vendor_files import extract_bruker_zip
            try:
                added = extract_bruker_zip(part, folder)
            finally:
                part.unlink(missing_ok=True)
            if not added:
                raise ToolError(f"{filename!r} holds no Bruker .d folder.")
            return {"key": key, "added": added, "complete": True}
        os.replace(part, Path(folder, filename))
        return {"key": key, "filename": filename, "size": size, "complete": True}

    def _check_quota(self, incoming: int) -> None:
        max_gb = self.sync_cfg.get("max_workspace_gb")
        if not max_gb:
            return
        used = sum(_size(p) for p in self.workspace.iterdir()) if self.workspace.is_dir() else 0
        if used + incoming > max_gb * 1024 ** 3:
            raise ToolError(f"This workspace would grow beyond {max_gb} GB.")

    def _import_from_link(self, workflow, url, files=None) -> dict:
        from src.data_import import job, net, sources
        workflow, entry, workflow_dir = self._workflow(workflow)
        if not isinstance(url, str) or not url.strip():
            raise ToolError("url must be a link.")
        job_dir = Path(workflow_dir, "link-import")
        if job.is_running(job.read_status(job_dir)):
            raise ToolError("An import is running in this workflow; see get_import_status.")
        keys = self._input_keys(entry, workflow_dir, describe.read_params(workflow_dir))
        targets = {k: {"name": k, "file_types": types, "dir": str(Path(workflow_dir, "input-files", k)),
                       "fallback": []} for k, types in keys.items() if types}
        if not targets:
            raise ToolError("This workflow names no file types for its inputs, so imported "
                            "files would have nowhere to go; use upload_file.")
        session = net.make_session(guard=self.online)
        try:
            listing = sources.resolve(session, url.strip())
        except (LookupError, net.BlockedURL) as e:
            raise ToolError(str(e))
        except Exception as e:  # noqa: BLE001 - a network error, said plainly
            raise ToolError(f"The link could not be read: {type(e).__name__}: {e}")
        items = job.build_items(listing.files, targets)
        listed = [{"path": i["path"], "size": i["size"], "input": i["target"] or None}
                  for i in items]
        if files is None and len(items) > 1:
            return {"title": listing.title, "files": listed[:MAX_LISTED], "notes": listing.notes,
                    "next": "Call import_from_link again with `files` set to the paths to download."}
        if files is not None:
            if not isinstance(files, list):
                raise ToolError("files must be a list of paths from the listing.")
            wanted = set(files)
            items = [i for i in items if i["path"] in wanted]
            unknown = wanted - {i["path"] for i in items}
            if unknown:
                raise ToolError(f"Not in the listing: {', '.join(sorted(unknown)[:5])}.")
        skipped = [i["path"] for i in items if not i["target"]]
        items = [i for i in items if i["target"]]
        if not items:
            accepted = "; ".join(k + ": " + ", ".join(t) for k, t in keys.items() if t)
            raise ToolError(f"None of these files fits an input of this workflow ({accepted}).")
        job.start_import(job_dir, items, targets, guard=self.online,
                         max_bytes=int(self.cfg["max_import_gb"] * 1024 ** 3))
        return {"started": [i["path"] for i in items], "skipped": skipped,
                "next": "Follow it with get_import_status."}

    def _get_import_status(self, workflow) -> dict:
        from src.data_import import job
        workflow, _, workflow_dir = self._workflow(workflow)
        status = job.read_status(Path(workflow_dir, "link-import"))
        if not status:
            return {"state": "none"}
        state = status.get("state")
        if job.is_interrupted(status):
            state = "interrupted"
        return {"state": state, "items": status.get("total_items"),
                "done_items": status.get("done_items"),
                "bytes_done": status.get("bytes_done"), "bytes_total": status.get("bytes_total"),
                "imported": [e.get("name") or e.get("path") for e in status.get("imported", [])],
                "errors": status.get("errors", [])[:20]}

    def _delete_file(self, workflow, key, filename) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        keys = self._input_keys(entry, workflow_dir, describe.read_params(workflow_dir))
        key = self._check_key(key, keys)
        folder = Path(workflow_dir, "input-files", key)
        target = Path(folder, self._check_name(filename))
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        else:
            ext = Path(folder, EXTERNAL_FILES)
            lines = ext.read_text(encoding="utf-8").splitlines() if ext.is_file() else []
            kept = [ln for ln in lines if Path(ln.strip()).name != filename]
            if len(kept) == len(lines):
                raise ToolError(f"No file {filename!r} in input {key!r}.")
            ext.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        return {"deleted": filename, "key": key}

    def _update_settings(self, workflow, settings=None, preset=None) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        if runner.status(self.workspace, workflow, self.online)["running"]:
            raise ToolError(f"{workflow} is running; change its settings after it ends.")
        self._ensure_described(entry, workflow_dir)
        params, changed = self._apply_settings(workflow, workflow_dir,
                                               describe.read_params(workflow_dir), settings, preset)
        describe.write_params(workflow_dir, params)
        return {"changed": changed,
                "note": "The configure page shows these after it is reloaded."}

    def _start_run(self, workflow, inputs=None, settings=None, preset=None, name="") -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        self._ensure_described(entry, workflow_dir)
        params = describe.read_params(workflow_dir)
        params, _ = self._apply_settings(workflow, workflow_dir, params, settings, preset)
        keys = self._input_keys(entry, workflow_dir, params)
        if inputs is not None:
            if not isinstance(inputs, dict):
                raise ToolError("inputs must map an input to a list of file names.")
            for key, names in inputs.items():
                key = self._check_key(key, keys)
                names = [names] if isinstance(names, str) else names
                if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                    raise ToolError(f"inputs[{key!r}] must be a list of file names.")
                chosen = [str(self._file_path(workflow_dir, key, n)) for n in names]
                if isinstance(params.get(key), str):
                    if len(chosen) != 1:
                        raise ToolError(f"{key} takes one file.")
                    params[key] = chosen[0]
                else:
                    params[key] = chosen
        empty = [k for k in self._class_inputs.get(entry["class"], []) if not params.get(k)]
        if empty and inputs is None:
            raise ToolError(f"No files chosen for {', '.join(empty)}; pass them in `inputs`.")
        if not isinstance(name, str):
            raise ToolError("name must be text.")
        state = runner.start(self.app_root, self.workspace, workflow, entry["class"], params,
                             name[:100], self.online, self._multi_run(entry))
        state["link"] = self._page_link(entry["run_page"])
        return state

    def _get_run_status(self, workflow) -> dict:
        workflow, entry, _ = self._workflow(workflow)
        state = runner.status(self.workspace, workflow, self.online)
        state["link"] = self._page_link(entry["run_page"])
        return state

    def _get_run_log(self, workflow, lines=100, detail="minimal") -> dict:
        workflow, _, workflow_dir = self._workflow(workflow)
        if not isinstance(lines, int):
            raise ToolError("lines must be a number.")
        return {"detail": detail, "lines": runner.log_lines(workflow_dir, lines, detail)}

    def _stop_run(self, workflow) -> dict:
        workflow, entry, _ = self._workflow(workflow)
        return runner.stop(self.workspace, workflow, self.online, self._multi_run(entry))

    def _list_runs(self, workflow) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        if not self._multi_run(entry):
            results = Path(workflow_dir, "results")
            has = results.is_dir() and any(results.iterdir())
            return {"multi_run": False, "runs": [{"id": None, "name": "Last run",
                                                  "has_results": has}] if has else []}
        runs = runner._runs(workflow_dir)
        return {"multi_run": True, "runs": [
            {k: r.get(k) for k in ("id", "name", "status", "created", "finished", "adds_to") if r.get(k)}
            for r in runs.list_runs()[:200]]}

    def _list_results(self, workflow, run_id=None) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        results, run_id = self._results_dir(workflow_dir, entry, run_id)
        files = []
        if results.is_dir():
            for p in sorted(results.rglob("*")):
                if p.is_file() and not any(part.startswith(".") for part in p.relative_to(results).parts):
                    files.append({"path": p.relative_to(results).as_posix(), "size": p.stat().st_size,
                                  "download": self._download_link(workflow_dir, p)})
                    if len(files) >= MAX_LISTED:
                        break
        out = {"run_id": run_id, "files": files}
        if self.online and files:
            out["download_note"] = ("Download links need the same Authorization: Bearer "
                                    "header as this connection.")
        return out

    def _read_result(self, workflow, path, run_id=None, offset=0, limit=50, columns=None) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        results, run_id = self._results_dir(workflow_dir, entry, run_id)
        rel = PurePosixPath(path) if isinstance(path, str) else None
        if rel is None or rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ToolError(f"Not a result path: {path!r}.")
        target = Path(results, *rel.parts)
        if not target.is_file():
            raise ToolError(f"No result file {path!r}. See list_results.")
        offset, limit = max(0, int(offset)), max(1, min(int(limit), MAX_ROWS))
        suffix = target.suffix.lower()
        info = {"path": path, "run_id": run_id, "size": target.stat().st_size,
                "download": self._download_link(workflow_dir, target)}
        if suffix in (".parquet", ".pq") or (suffix in TABLE_SUFFIXES and _looks_tabular(target, suffix)):
            return {**info, **_read_table(target, suffix, offset, limit, columns)}
        if suffix in TEXT_SUFFIXES or _is_text(target):
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0)
                text = f.read(offset + MAX_TEXT)[offset:]
            return {**info, "text": text, "truncated": info["size"] > offset + len(text)}
        return {**info, "note": "Not a table or text; fetch it from the download link."}

    def _get_processing_report(self, workflow, run_id=None) -> dict:
        from src.workflow import processing_report
        workflow, entry, workflow_dir = self._workflow(workflow)
        _, run_id = self._results_dir(workflow_dir, entry, run_id)
        report = processing_report.report_for(workflow_dir, run_id)
        if not report:
            raise ToolError("This run recorded no processing steps.")
        return {"run_id": run_id, "markdown": processing_report.to_markdown(report)}

    def _get_app_link(self, workflow=None, page="results") -> dict:
        if workflow is None:
            return {"link": self._page_link("")}
        workflow, entry, _ = self._workflow(workflow)
        page_file = entry.get(f"{page}_page") or ""
        return {"link": self._page_link(page_file), "page": page if page_file else "home"}


def _coerce(value, typ: str):
    if typ == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ValueError(value)
    if typ == "int":
        if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
            raise ValueError(value)
        return int(value)
    if typ == "double":
        if isinstance(value, bool):
            raise ValueError(value)
        return float(value)
    if isinstance(value, (dict, list)):
        raise ValueError(value)
    return str(value)


def _size(p: Path) -> int:
    try:
        if p.is_dir():
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        return p.stat().st_size
    except OSError:
        return 0


def _is_text(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as e:
        return e.start > len(head) - 4  # cut in a multi-byte character
    return True


def _looks_tabular(path: Path, suffix: str) -> bool:
    if suffix != ".txt":
        return True
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        return False
    return "\t" in first


def _read_table(path: Path, suffix: str, offset: int, limit: int, columns) -> dict:
    import pandas as pd
    if columns is not None and not (isinstance(columns, list) and all(isinstance(c, str) for c in columns)):
        raise ToolError("columns must be a list of column names.")
    try:
        if suffix in (".parquet", ".pq"):
            import pyarrow.parquet as pq
            pf = pq.ParquetFile(path)
            total = pf.metadata.num_rows
            names = pf.schema_arrow.names
            df = pd.read_parquet(path, columns=[c for c in columns if c in names] if columns else None)
            df = df.iloc[offset:offset + limit]
        else:
            sep = TABLE_SUFFIXES[suffix]
            names = list(pd.read_csv(path, sep=sep, nrows=0).columns)
            df = pd.read_csv(path, sep=sep, skiprows=range(1, offset + 1), nrows=limit,
                             usecols=[c for c in columns if c in names] if columns else None)
            with open(path, "rb") as f:
                total = max(0, sum(1 for _ in f) - 1)
    except ToolError:
        raise
    except Exception as e:  # noqa: BLE001 - the file is not the table it looks like
        raise ToolError(f"{path.name} could not be read as a table: {e}")
    if columns:
        missing = [c for c in columns if c not in names]
        if missing:
            raise ToolError(f"No column {missing[0]!r}. Columns: {', '.join(names[:100])}.")
    rows = json.loads(df.to_json(orient="records", double_precision=10))
    return {"columns": names, "total_rows": total, "offset": offset, "rows": rows,
            "more": offset + len(rows) < total}
