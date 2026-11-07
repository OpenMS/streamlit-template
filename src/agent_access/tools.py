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

from . import activity, analysis, describe, look, runner, show

logger = logging.getLogger("agent-access")


def analysis_mod():
    """The analysis module (the tools' own argument named ``analysis`` hides it)."""
    return analysis

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
ANALYSIS = {"type": "string", "description": "An analysis from begin_analysis or list_analyses."}

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
     "The result files of a run (workflow and run_id) or of an analysis, with sizes and "
     "download links.",
     _schema({"workflow": WORKFLOW, "run_id": RUN_ID, "analysis": ANALYSIS}), READ_ONLY),
    ("read_result", "Read a result file",
     "Read a result file of a run (workflow and run_id) or of an analysis: a table (TSV, CSV, Parquet) as rows, with offset and limit for "
     "paging, a text file as text. Other files get a download link.",
     _schema({"workflow": WORKFLOW, "run_id": RUN_ID,
              "path": {"type": "string", "description": "As list_results gives it."},
              "offset": {"type": "integer", "default": 0, "minimum": 0},
              "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": MAX_ROWS},
              "columns": {"type": "array", "items": {"type": "string"}},
              "analysis": ANALYSIS},
             ("path",)), READ_ONLY),
    ("get_processing_report", "Processing report",
     "What a run did, per input file: every tool, its version and the parameters that "
     "differ from the defaults, as Markdown. Cite it in a methods section. For an analysis: "
     "every step you took, with why, back to the input files.",
     _schema({"workflow": WORKFLOW, "run_id": RUN_ID, "analysis": ANALYSIS}), READ_ONLY),
    ("get_app_link", "Link to the app",
     "A link that opens this workspace in the browser, on a workflow's configure, run or "
     "results page, for the person to look at what you did.",
     _schema({"workflow": WORKFLOW,
              "page": {"type": "string", "enum": ["configure", "run", "results"]}}),
     READ_ONLY),
    ("list_result_views", "Result views",
     "The Results page of a workflow as components (tables, plots) and the views that "
     "arrange them, for one run: what each component shows, whether the run has what it "
     "needs, and which view the person has open. Look at components with "
     "look_at_results; show a view with show_in_app.",
     _schema({"workflow": WORKFLOW, "run_id": RUN_ID}, ("workflow",)), READ_ONLY),
    ("look_at_results", "Look at results",
     "Draw components of the Results page for a run, as the person would see them, and "
     "get what they show: tables (row count, columns, min/median/mean/max of each number "
     "column, first rows), plots (title, axes, every trace's points, and an image where "
     "the server can draw one), metrics and messages. Leave components out to look at "
     "every component the run can fill. A table that can be selected gives its "
     "select_key; pass select={select_key: [row numbers]} to see what the components "
     "that follow a selection draw for those rows. Look at everything before you tell "
     "the person what the results say.",
     _schema({"workflow": WORKFLOW, "run_id": RUN_ID,
              "components": {"type": "array", "items": {"type": "string"},
                             "description": "Component names from list_result_views."},
              "select": {"type": "object", "description": "select_key -> list of row numbers.",
                         "additionalProperties": {"type": "array", "items": {"type": "integer"}}},
              "rows": {"type": "integer", "default": 20, "minimum": 1, "maximum": 200,
                       "description": "First rows of each table."}},
             ("workflow",)), READ_ONLY),
    ("show_in_app", "Show in the app",
     "Bring a page up in the app the person has open in this workspace, with a run picked "
     "and a short note on what to look at. On the results page, show exactly the "
     "components that answer what you discuss: a view from list_result_views, or your own "
     "arrangement as components (rows of up to three names, e.g. [[\"features\", "
     "\"intensities\"]]), which becomes the view \"From the assistant\". Show only what "
     "matters for the conversation, after you looked at it yourself. The app follows "
     "unless the person turned that off; the returned link opens the same page.",
     _schema({"workflow": WORKFLOW,
              "page": {"type": "string", "enum": ["configure", "run", "results"],
                       "default": "results"},
              "run_id": {"type": "string",
                         "description": "The run to pick, from list_runs. Default: the newest "
                                        "finished run."},
              "view": {"type": "string", "description": "A view from list_result_views."},
              "components": {"type": "array", "description": "Rows of component names.",
                             "items": {"type": "array", "items": {"type": "string"},
                                       "minItems": 1, "maxItems": 3}},
              "note": {"type": "string", "maxLength": 500,
                       "description": "One or two sentences on what the person sees."}},
             ("workflow",)), WRITES),
    # -- the assistant's own analysis (analysis.py) --
    ("list_analyses", "List analyses",
     "Your analyses in this workspace, newest first: name, question, state and summary.",
     _schema({}), READ_ONLY),
    ("begin_analysis", "Begin an analysis",
     "Start your own analysis of the data, to answer a question: the app records every step "
     "you take (each TOPP tool with its version and parameters, each figure and table you "
     "write, and why) so its processing report says how each result was made. Build on a "
     "run of a workflow (workflow and run_id) to start from its results and its recorded "
     "steps, or on the input files alone. Returns the files you can use.",
     _schema({"name": {"type": "string", "maxLength": 100},
              "question": {"type": "string", "description": "What the analysis answers."},
              "workflow": WORKFLOW, "run_id": RUN_ID}, ("name",)),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}),
    ("describe_tool", "Describe a TOPP tool",
     "An OpenMS (TOPP) tool's input and output file parameters and its parameters, with types, "
     "defaults, allowed values and descriptions. Read it before run_tool.",
     _schema({"tool": {"type": "string"},
              "include_advanced": {"type": "boolean", "default": False}}, ("tool",)), READ_ONLY),
    ("run_tool", "Run a TOPP tool",
     "Run an OpenMS (TOPP) tool as a step of an analysis. `inputs` and `outputs` map the "
     "tool's file parameters (e.g. in, out) to files: inputs are paths relative to the "
     "analysis's results or to the workspace (as begin_analysis lists them), outputs are file "
     "names in the analysis's results. A list runs the tool once per file. `params` are the "
     "tool's parameters (path: value), `why` one sentence the report keeps. Waits up to `wait` "
     "seconds; a longer step goes on, follow it with get_step.",
     _schema({"analysis": ANALYSIS, "tool": {"type": "string"},
              "inputs": {"type": "object"}, "outputs": {"type": "object"},
              "params": {"type": "object"}, "why": {"type": "string"},
              "wait": {"type": "number", "default": 60, "minimum": 0, "maximum": 600}},
             ("analysis", "tool", "outputs")),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}),
    ("get_step", "Follow a step",
     "The outcome of a step of an analysis: whether it worked, the files it wrote and the end "
     "of its log. Waits up to `wait` seconds while it runs.",
     _schema({"analysis": ANALYSIS, "step": {"type": "integer", "minimum": 1},
              "wait": {"type": "number", "default": 30, "minimum": 0, "maximum": 600}},
             ("analysis", "step")), READ_ONLY),
    ("save_figure", "Save a figure",
     "Write a Plotly figure you made (its JSON: data and layout) into an analysis's results, "
     "as a step: `made_from` names the files its numbers come from, `why` what it shows.",
     _schema({"analysis": ANALYSIS, "file": {"type": "string", "description": "e.g. volcano.json"},
              "figure": {"type": "object"},
              "made_from": {"type": "array", "items": {"type": "string"}},
              "why": {"type": "string"}}, ("analysis", "file", "figure")),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}),
    ("save_table", "Save a table",
     "Write a table you put together into an analysis's results (TSV), as a step: `made_from` "
     "names the files its values come from, `why` what it holds.",
     _schema({"analysis": ANALYSIS, "file": {"type": "string", "description": "e.g. top-features.tsv"},
              "columns": {"type": "array", "items": {"type": "string"}},
              "rows": {"type": "array", "items": {"type": "array"}},
              "made_from": {"type": "array", "items": {"type": "string"}},
              "why": {"type": "string"}}, ("analysis", "file", "columns", "rows")),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}),
    ("show_analysis", "Show an analysis",
     "Open an analysis on the app's Assistant analyses page for the person, with the result "
     "files you choose, in order: figures (.json), tables, images and text, each with a title "
     "and a caption, and a short note. The page also offers its processing report.",
     _schema({"analysis": ANALYSIS,
              "items": {"type": "array", "items": {"type": "object", "properties": {
                  "file": {"type": "string"}, "title": {"type": "string"},
                  "caption": {"type": "string"}}, "required": ["file"]}},
              "note": {"type": "string", "maxLength": 500}}, ("analysis", "items")), WRITES),
    ("finish_analysis", "Finish an analysis",
     "Mark an analysis done, with a summary of what it found (kept in its report).",
     _schema({"analysis": ANALYSIS, "summary": {"type": "string"},
              "failed": {"type": "boolean", "default": False}}, ("analysis",)), WRITES),
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
            f"for mass spectrometry data analysis. Workflows: {names}. Answer the person's "
            "question with an analysis of your own: begin_analysis (on a workflow's run, or on "
            "the input files alone), then run the OpenMS tools you need with run_tool "
            "(describe_tool lists a tool's files and parameters), read what they wrote with "
            "list_results and read_result, and write the figures and tables that answer the "
            "question with save_figure and save_table. Give every step a `why`: the app records "
            "each step with its tool, version, parameters and files, so the analysis's "
            "processing report (get_processing_report) says how each result was made. A whole "
            "workflow is one step away too: start_run, then build an analysis on its run. "
            "Discuss what you found with the person in your chat; show_analysis opens the "
            "figures and tables that matter in their app, and show_in_app a workflow's own "
            "Results views. finish_analysis records your summary. Add input files with "
            "upload_file or import_from_link."
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
        except analysis.AnalysisError as e:
            error = str(e)
            raise ToolError(error) from e
        except ToolError as e:
            error = str(e)
            raise
        finally:
            activity.record(self.workspace, name, arguments.get("workflow") or
                            (analysis.ROOT if arguments.get("analysis") else None), error)

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
        # Not resolve(): a demo workspace's results are often links into the
        # demo's source, which lies outside the workspace.
        rel = Path(os.path.relpath(path.absolute(), self.workspace.absolute())).as_posix()
        if rel.startswith("../"):
            return ""
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

    def _where(self, workflow, run_id, analysis_id) -> tuple[Path, Path, str | None]:
        """(folder for links and reports, results folder, run id) of a run or an analysis."""
        if analysis_id is not None:
            return (Path(self.workspace, analysis.ROOT),
                    analysis.results_dir(self.workspace, analysis_id), analysis_id)
        if workflow is None:
            raise ToolError("Name a workflow (and run_id) or an analysis.")
        workflow, entry, workflow_dir = self._workflow(workflow)
        results, run_id = self._results_dir(workflow_dir, entry, run_id)
        return workflow_dir, results, run_id

    def _list_results(self, workflow=None, run_id=None, analysis=None) -> dict:
        workflow_dir, results, run_id = self._where(workflow, run_id, analysis)
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

    def _read_result(self, path, workflow=None, run_id=None, offset=0, limit=50, columns=None,
                     analysis=None) -> dict:
        workflow_dir, results, run_id = self._where(workflow, run_id, analysis)
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

    def _get_processing_report(self, workflow=None, run_id=None, analysis=None) -> dict:
        from src.workflow import processing_report
        workflow_dir, _, run_id = self._where(workflow, run_id, analysis)
        report = processing_report.report_for(workflow_dir, run_id,
                                              workflow="" if analysis is None else "AI assistant")
        if not report:
            raise ToolError("This run recorded no processing steps.")
        return {"run_id": run_id, "markdown": processing_report.to_markdown(report)}

    def _get_app_link(self, workflow=None, page="results") -> dict:
        if workflow is None:
            return {"link": self._page_link("")}
        workflow, entry, _ = self._workflow(workflow)
        page_file = entry.get(f"{page}_page") or ""
        return {"link": self._page_link(page_file), "page": page if page_file else "home"}

    # -- results as components ---------------------------------------------------

    ASSISTANT_VIEW = "custom-assistant"

    def _catalog(self, entry: dict) -> dict:
        cat = look.catalog(entry)
        if cat is None:
            raise ToolError("This workflow's results page is not built from components; "
                            "use list_results and read_result.")
        return cat

    def _list_result_views(self, workflow, run_id=None) -> dict:
        from src.layout_manager.layout import load_views, missing_analyses
        workflow, entry, workflow_dir = self._workflow(workflow)
        cat = self._catalog(entry)
        _, run_id = self._results_dir(workflow_dir, entry, run_id)
        have = look.available(cat["class"], workflow_dir, run_id)
        components = []
        for c in cat["components"]:
            item = {k: c[k] for k in ("name", "label", "group") if k in c}
            if c.get("requires"):
                item["shown_with"] = c["requires"]
            missing = missing_analyses([c["name"]], cat["components"], have) if have is not None else []
            item["run_has_it"] = not missing
            if missing:
                item["needs"] = [str((cat["analyses"].get(m) or {}).get("label", m))
                                 if isinstance(cat["analyses"].get(m), dict) else m for m in missing]
            components.append(item)
        default = cat["presets"][0]["layout"] if cat["presets"] else [[c["name"]] for c in cat["components"]]
        state = load_views(Path(workflow_dir, cat["layout"]), cat["components"], cat["presets"], default)
        views = [{"name": v["name"], "label": v["label"], "components": v["rows"],
                  "ready_made": bool(v.get("preset")), **({"help": v["help"]} if v.get("help") else {})}
                 for v in state["views"]]
        return {"run_id": run_id, "components": components, "views": views,
                "open_view": state["current"]}

    def _look_at_results(self, workflow, run_id=None, components=None, select=None, rows=20) -> dict:
        from src.layout_manager.layout import missing_analyses
        workflow, entry, workflow_dir = self._workflow(workflow)
        cat = self._catalog(entry)
        _, run_id = self._results_dir(workflow_dir, entry, run_id)
        known = {c["name"]: c for c in cat["components"]}
        have = look.available(cat["class"], workflow_dir, run_id)
        if components is None:
            components = [n for n in known
                          if have is None or not missing_analyses([n], cat["components"], have)]
        if not isinstance(components, list) or not components:
            raise ToolError("Name at least one component (see list_result_views).")
        unknown = [c for c in components if c not in known]
        if unknown:
            raise ToolError(f"Unknown components {unknown}. Components: {', '.join(known)}.")
        if select is not None and not (isinstance(select, dict) and all(
                isinstance(v, list) and all(isinstance(i, int) for i in v) for v in select.values())):
            raise ToolError("select maps a select_key to a list of row numbers.")
        rows = max(1, min(int(rows), 200))
        drawn = look.look(self.app_root, self.workspace, workflow, entry["class"], run_id,
                          components, self.online, rows=rows, select=select or {})
        if drawn.get("error"):
            raise ToolError(drawn["error"])
        images, out = [], {}
        for name in components:
            items = drawn.get("components", {}).get(name, [])
            for item in items:
                png = item.pop("image_png_base64", None)
                if png:
                    images.append({"title": f"{known[name].get('label', name)}: {item.get('title') or 'plot'}",
                                   "data": png})
                    item["image"] = len(images)
            if have is not None and missing_analyses([name], cat["components"], have):
                items = [{"type": "note", "text": "This run lacks what the component needs."}]
            out[name] = {"label": known[name].get("label", name), "shows": items}
        result = {"run_id": run_id, "components": out}
        if drawn.get("exception"):
            result["page_errors"] = drawn["exception"]
        if images:
            result["_images"] = images
        return result

    def _set_view(self, workflow_dir: Path, entry: dict, view, components) -> str:
        from src.layout_manager.layout import load_views, save_views, validate_layout
        cat = self._catalog(entry)
        default = cat["presets"][0]["layout"] if cat["presets"] else [[c["name"]] for c in cat["components"]]
        path = Path(workflow_dir, cat["layout"])
        state = load_views(path, cat["components"], cat["presets"], default)
        if view is not None:
            if view not in {v["name"] for v in state["views"]}:
                raise ToolError(f"No view {view!r}. See list_result_views.")
            state["current"] = view
        else:
            if isinstance(components, list) and components and all(isinstance(c, str) for c in components):
                components = [[c] for c in components]
            problem = validate_layout([components], cat["components"])
            if problem:
                raise ToolError(f"Cannot show these components: {problem}.")
            mine = {"name": self.ASSISTANT_VIEW, "label": "From the assistant",
                    "rows": [list(r) for r in components], "preset": False, "in_bar": True}
            state["views"] = [v for v in state["views"] if v["name"] != self.ASSISTANT_VIEW]
            state["views"].insert(sum(v.get("in_bar", True) for v in state["views"]), mine)
            state["current"] = self.ASSISTANT_VIEW
            view = self.ASSISTANT_VIEW
        save_views(path, state)
        return view

    def _show_in_app(self, workflow, page="results", run_id=None, note="", view=None,
                     components=None) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        if page not in ("configure", "run", "results"):
            raise ToolError("page must be configure, run or results.")
        page_file = entry.get(f"{page}_page") or ""
        if not page_file:
            raise ToolError(f"This app names no {page} page for {workflow}.")
        if run_id is not None:
            if not self._multi_run(entry):
                raise ToolError("This workflow keeps one result set; leave run_id out.")
            if not isinstance(run_id, str) or runner._runs(workflow_dir).get(run_id) is None:
                raise ToolError(f"No run {run_id!r}. See list_runs.")
        if not isinstance(note, str):
            raise ToolError("note must be text.")
        shown_view = None
        if view is not None or components is not None:
            if page != "results":
                raise ToolError("view and components are for the results page.")
            shown_view = self._set_view(workflow_dir, entry, view, components)
        request = show.write(self.workspace, {"workflow": workflow, "page": page,
                                              "page_file": page_file, "run_id": run_id,
                                              "note": note.strip()[:500]})
        return {"shown": True, "page": page, "run_id": run_id, "view": shown_view, "id": request["id"],
                "link": self._page_link(page_file)}


    # -- the assistant's own analysis ----------------------------------------------

    ANALYSIS_PAGE = "content/assistant_analyses.py"

    def _list_analyses(self) -> dict:
        return {"analyses": analysis.list_analyses(self.workspace)[:200]}

    def _usable_files(self, based_on: Path | None) -> dict:
        """Paths (relative to the workspace) a step can read."""
        out = {"inputs": {}}
        for name in self.cfg["workflows"]:
            folder = Path(self.workspace, name, "input-files")
            if folder.is_dir():
                for key_dir in sorted(d for d in folder.iterdir() if d.is_dir()):
                    paths = [Path(name, "input-files", key_dir.name, f["name"]).as_posix()
                             if not f.get("referenced") else
                             str(self._file_path(Path(self.workspace, name), key_dir.name, f["name"]))
                             for f in self._files(Path(self.workspace, name), key_dir.name)]
                    if paths:
                        out["inputs"][f"{name}/{key_dir.name}"] = paths[:MAX_LISTED]
        if based_on is not None:
            results = Path(based_on, "results")
            if results.is_dir():
                out["run_results"] = [p.relative_to(self.workspace).as_posix()
                                      for p in sorted(results.rglob("*")) if p.is_file()][:MAX_LISTED]
        return out

    def _begin_analysis(self, name, question="", workflow=None, run_id=None) -> dict:
        if not isinstance(name, str) or not name.strip():
            raise ToolError("Give the analysis a name.")
        based_on, based_name = None, ""
        if workflow is not None:
            workflow, entry, workflow_dir = self._workflow(workflow)
            results, run_id = self._results_dir(workflow_dir, entry, run_id)
            based_on = results.parent
            run = runner._runs(workflow_dir).get(run_id) if run_id else None
            based_name = (run or {}).get("name") or f"the last run of {workflow}"
        analysis_id = analysis.begin(self.workspace, name.strip()[:100], question, based_on, based_name)
        return {"analysis": analysis_id, "based_on": based_name or None,
                "files": self._usable_files(based_on),
                "note": "Paths are relative to the workspace; outputs are file names in the "
                        "analysis's results, which later steps read by that name."}

    def _describe_tool(self, tool, include_advanced=False) -> dict:
        return analysis.describe_tool(self.workspace, tool, bool(include_advanced))

    def _run_tool(self, analysis, tool, outputs, inputs=None, params=None, why="", wait=60) -> dict:
        step = analysis_mod().tool_step(self.workspace, analysis, tool, inputs or {}, outputs, params, why)
        number = analysis_mod().submit(self.workspace, analysis, step, self.app_root)
        return analysis_mod().step_result(self.workspace, analysis, number, wait)

    def _get_step(self, analysis, step, wait=30) -> dict:
        return analysis_mod().step_result(self.workspace, analysis, step, wait)

    def _save_figure(self, analysis, file, figure, made_from=None, why="") -> dict:
        return analysis_mod().save_figure(self.workspace, analysis, file, figure, made_from, why)

    def _save_table(self, analysis, file, columns, rows, made_from=None, why="") -> dict:
        return analysis_mod().save_table(self.workspace, analysis, file, columns, rows, made_from, why)

    def _show_analysis(self, analysis, items, note="") -> dict:
        chosen = analysis_mod().show(self.workspace, analysis, items)
        if not isinstance(note, str):
            raise ToolError("note must be text.")
        request = show.write(self.workspace, {"workflow": "", "page": "analysis",
                                              "page_file": self.ANALYSIS_PAGE, "analysis": analysis,
                                              "note": note.strip()[:500]})
        return {"shown": len(chosen), "id": request["id"], "link": self._page_link(self.ANALYSIS_PAGE)}

    def _finish_analysis(self, analysis, summary="", failed=False) -> dict:
        run = analysis_mod().finish(self.workspace, analysis, summary, bool(failed))
        return {"analysis": analysis, "status": run["status"]}


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
