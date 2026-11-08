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
import time
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlencode

from . import activity, describe, look, runner, show

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

QUESTION = {"type": "string", "description": "The person's question, in their words."}
WHY = {"type": "string", "description": "One line on why this run: what it changes and what "
       "it should show."}
BY = "AI assistant"

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
     "Start the workflow with the chosen input files, as the Run page does: the baseline "
     "run of a question, with the workflow's defaults or a preset. `inputs` maps an input "
     "to file names from list_files; `settings` and `preset` are applied first as in "
     "update_settings. `question` (the person's question) and `why` (one line on why this "
     "run) are kept with the run and named in its processing report. The run shows on the "
     "app's Run page. Follow it with get_run_status. Before starting, check list_runs for "
     "a finished run that already answers the question.",
     _schema({"workflow": WORKFLOW,
              "inputs": {"type": "object", "description": "Input -> list of file names.",
                         "additionalProperties": {"type": "array", "items": {"type": "string"}}},
              "settings": {"type": "object"}, "preset": {"type": "string"},
              "name": {"type": "string", "description": "A name for the run."},
              "question": QUESTION, "why": WHY},
             ("workflow", "question", "why")),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
      "openWorldHint": False}),
    ("follow_up", "Start a follow-up run",
     "Start a run from the settings of an earlier run, as the app's own follow-up does: "
     "(1) changed settings on the same files (`settings`, `preset`); (2) an analysis "
     "added to the run on exactly its files, reusing the results of the tools in `keep` "
     "so only the later steps run again; or (3) more files for the run's experiment "
     "(`add_files`: input -> file names not yet in it; upload or import them first). "
     "The new run sits next to the earlier one; the run list, Results page and "
     "processing report name the run it follows, the question and `why`.",
     _schema({"workflow": WORKFLOW,
              "run_id": {"type": "string", "description": "The run to follow, from list_runs."},
              "settings": {"type": "object", "description": "Setting -> value, as in update_settings."},
              "preset": {"type": "string"},
              "keep": {"type": "array", "items": {"type": "string"},
                       "description": "Tools whose results are reused (an added analysis)."},
              "add_files": {"type": "object", "description": "Input -> file names to add.",
                            "additionalProperties": {"type": "array", "items": {"type": "string"}}},
              "name": {"type": "string", "description": "A name for the run."},
              "question": QUESTION, "why": WHY},
             ("workflow", "run_id", "question", "why")),
     {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
      "openWorldHint": False}),
    ("get_run_status", "Run status",
     "Whether the workflow's last run is queued, running, finished, failed or cancelled, "
     "its current step and the last lines of its log. Pass wait to return as soon as the "
     "run ends, or after that many seconds.",
     _schema({"workflow": WORKFLOW,
              "wait": {"type": "integer", "minimum": 0, "maximum": 60, "default": 0,
                       "description": "Seconds to wait for the run to end."}},
             ("workflow",)), READ_ONLY),
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
    ("save_view", "Save a view of your answer",
     "Save the view your answer rests on to the workflow's Results page: the components "
     "that show it (rows of up to three names from list_result_views), the runs it shows "
     "(one to five, side by side when two, else one below the other), the zoom, selection "
     "and point annotations each run opens with, and an explanation of at most five short "
     "points shown above the components. Write the points scientifically and concisely, "
     "and use only numbers the person can find in the view. The view carries the "
     "assistant's icon, the person can only duplicate it, and it becomes the open view; "
     "views of an earlier question move to More. Pass name to change a view you saved. "
     "Then call show_in_app with the view.",
     _schema({"workflow": WORKFLOW,
              "label": {"type": "string", "maxLength": 60,
                        "description": "The view's name in the bar, e.g. \"Treatment vs Control\"."},
              "components": {"type": "array", "description": "Rows of component names.",
                             "items": {"type": "array", "items": {"type": "string"},
                                       "minItems": 1, "maxItems": 3}},
              "runs": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5,
                       "description": "Finished runs from list_runs, in the order shown."},
              "side_by_side": {"type": "boolean", "default": False,
                               "description": "Two runs next to each other instead of one below the other."},
              "question": QUESTION,
              "explanation": {"type": "array", "items": {"type": "string", "maxLength": 300},
                              "minItems": 1, "maxItems": 5,
                              "description": "At most five points, each one sentence."},
              "defaults": {"type": "array", "maxItems": 5,
                           "description": "Per run, in the order of runs: what it opens with. "
                                          "selection maps an identifier to a value, zoom a "
                                          "component to {\"x\": [lo, hi], \"y\": [lo, hi]}, "
                                          "annotations a component to {point id: "
                                          "{\"highlight\": true, \"annotation\": text}}.",
                           "items": {"type": "object", "properties": {
                               "selection": {"type": "object"}, "zoom": {"type": "object"},
                               "annotations": {"type": "object"}}}},
              "name": {"type": "string", "description": "A view you saved before, to change it."}},
             ("workflow", "label", "components", "question", "explanation")), WRITES),
    ("delete_view", "Delete a view you saved",
     "Delete a view you saved with save_view. Views the person made and ready-made views "
     "cannot be deleted.",
     _schema({"workflow": WORKFLOW, "name": {"type": "string"}}, ("workflow", "name")),
     {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True}),
    ("show_in_app", "Show in the app",
     "Bring a page up in the app the person has open in this workspace, with a run picked "
     "and a short note on what to look at. On the results page, open the view your answer "
     "rests on: one you saved with save_view, or a view from list_result_views. The app "
     "follows unless the person turned that off; the returned link opens the same page.",
     _schema({"workflow": WORKFLOW,
              "page": {"type": "string", "enum": ["configure", "run", "results"],
                       "default": "results"},
              "run_id": {"type": "string",
                         "description": "The run to pick, from list_runs. Default: the first "
                                        "run of the view, else the newest finished run."},
              "view": {"type": "string", "description": "A view from save_view or list_result_views."},
              "note": {"type": "string", "maxLength": 500,
                       "description": "One or two sentences on what the person sees."}},
             ("workflow",)), WRITES),
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
            f"for mass spectrometry data analysis. Workflows: {names}.\n"
            "Working rules:\n"
            "1. Data is processed only by the app's workflows. You run no tools or code of "
            "your own on the data; every number you report comes from a workflow run.\n"
            "2. Start with get_app_info and describe_workflow. Check list_runs: reuse a "
            "finished run that fits the question. Else start a baseline run with start_run "
            "(the workflow's defaults or a preset).\n"
            "3. Go further only with follow_up: changed settings, an analysis added to a run "
            "(keep), or more files or experiments (add_files, after upload_file or "
            "import_from_link). Every run takes the person's question and one line on why "
            "it was started; the processing report names both. Tell the person in the chat "
            "what you add and why before you start it.\n"
            "4. Follow a run with get_run_status (wait up to 60 s per call). Read its results with list_result_views, "
            "look_at_results, list_results and read_result before you answer.\n"
            "5. Write scientifically and concisely. State only numbers the person can find "
            "in the results you show them.\n"
            "6. Show the person what your answer rests on: save_view with the components, "
            "the runs (several side by side or one below the other), the zoom, selection and "
            "annotations they open with, and at most five points of explanation; then "
            "show_in_app with the view and a short note. One answer may save several views. "
            "Change or delete only views you saved. get_app_link gives the person the link."
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

    def _class(self, entry: dict):
        module, _, cls = entry["class"].partition(":")
        try:
            return getattr(importlib.import_module(module), cls)
        except Exception:  # noqa: BLE001 - a class that does not import cannot run either
            logger.exception("cannot import %s", entry["class"])
            raise ToolError(f"The workflow class {entry['class']} cannot be loaded.")

    def _runs_of(self, entry: dict, workflow_dir: Path):
        """The workflow's result sets, or None when it keeps one.

        A multi-run workflow keeps them in run folders (``RunManager``). A
        workflow that stores its results elsewhere (a cache of datasets, for
        example) gives a class method ``results_store(workflow_dir)``
        returning an object with the same ``list_runs()``, ``get(id)``,
        ``latest()`` and ``results_dir(id)``.
        """
        store = getattr(self._class(entry), "results_store", None)
        if callable(store):
            return store(workflow_dir)
        return runner._runs(workflow_dir) if self._multi_run(entry) else None

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
        """Show the configure page once if this workspace never did.

        Other pages write params.json too (the upload page its file selection)
        and make an empty ini folder; only the configure page writes the
        settings and the tools' .ini files.
        """
        params = describe.read_params(workflow_dir)
        settings = set(params) - set(self._input_keys(entry, workflow_dir, params))
        if settings or any(Path(workflow_dir, "ini").glob("*.ini")):
            return ""
        return describe.prepare(self.app_root, self.workspace, entry["configure_page"], self.online)

    def _results_dir(self, workflow_dir: Path, entry: dict, run_id) -> tuple[Path, str | None]:
        runs = self._runs_of(entry, workflow_dir)
        if runs is None:
            return Path(workflow_dir, "results"), None
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

    def _start_run(self, workflow, inputs=None, settings=None, preset=None, name="",
                   question="", why="") -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        self._ensure_described(entry, workflow_dir)
        params = describe.read_params(workflow_dir)
        # A baseline follows no earlier run, whatever the configure page left there
        params.pop("_follow_up", None)
        params, _ = self._apply_settings(workflow, workflow_dir, params, settings, preset)
        self._choose_inputs(entry, workflow_dir, params, inputs)
        empty = [k for k in self._class_inputs.get(entry["class"], []) if not params.get(k)]
        if empty and inputs is None:
            raise ToolError(f"No files chosen for {', '.join(empty)}; pass them in `inputs`.")
        return self._launch(workflow, entry, params, name, question, why)

    def _follow_up(self, workflow, run_id, question="", why="", settings=None, preset=None,
                   keep=None, add_files=None, name="") -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        if not self._multi_run(entry):
            raise ToolError(f"{workflow} keeps no runs side by side; start a new run with "
                            "start_run and the settings you want.")
        if runner.status(self.workspace, workflow, self.online)["running"]:
            raise ToolError(f"{workflow} is running; start the follow-up after it ends.")
        runs = runner._runs(workflow_dir)
        run = runs.get(run_id) if isinstance(run_id, str) else None
        if run is None:
            raise ToolError(f"No run {run_id!r}; list_runs lists the runs.")
        if run.get("status") != "finished":
            raise ToolError(f"Run {run_id} is {run.get('status') or 'not finished'}; only a "
                            "finished run can be followed.")
        if keep is not None and add_files is not None:
            raise ToolError("Pass `keep` (an analysis added to the run) or `add_files` "
                            "(more files for its experiment), not both.")
        if keep is not None and (not isinstance(keep, list)
                                 or not all(isinstance(t, str) for t in keep)):
            raise ToolError("keep must be a list of tool names.")
        inputs = self._class_inputs.get(entry["class"], [])
        files_key = inputs[0] if inputs else None
        add_key = None
        if add_files is not None:
            if not isinstance(add_files, dict) or len(add_files) != 1:
                raise ToolError("add_files maps one input to the file names to add.")
            add_key = next(iter(add_files))
        if keep is not None and files_key is None:
            raise ToolError(f"{workflow} names no input files, so no results can be reused.")
        if not runs.restore_settings(run_id, note=why if isinstance(why, str) else "",
                                     add_files=add_key,
                                     same_files=files_key if keep is not None else None,
                                     keep=keep):
            raise ToolError(f"Run {run_id} recorded no settings to start from.")
        params = describe.read_params(workflow_dir)
        if keep is not None:
            tools = describe.topp_tools(params, workflow_dir)
            unknown = [t for t in keep if t not in tools]
            if unknown:
                raise ToolError(f"Not a tool of {workflow}: {', '.join(unknown)}. "
                                f"Tools: {', '.join(sorted(tools)) or 'none'}.")
        params, _ = self._apply_settings(workflow, workflow_dir, params, settings, preset)
        if add_key is not None:
            self._choose_inputs(entry, workflow_dir, params, add_files)
            already = set(runs.experiment_files(run_id, add_key))
            chosen = params.get(add_key) or []
            chosen = [chosen] if isinstance(chosen, str) else chosen
            twice = [Path(f).name for f in chosen if f in already]
            if twice:
                raise ToolError(f"Already in the experiment: {', '.join(twice)}.")
            if not chosen:
                raise ToolError("add_files names no files.")
        return self._launch(workflow, entry, params, name, question, why)

    def _choose_inputs(self, entry: dict, workflow_dir: Path, params: dict, inputs) -> None:
        if inputs is None:
            return
        keys = self._input_keys(entry, workflow_dir, params)
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

    def _launch(self, workflow: str, entry: dict, params: dict, name, question, why) -> dict:
        if not isinstance(name, str):
            raise ToolError("name must be text.")
        if not isinstance(question, str) or not question.strip():
            raise ToolError("question: the person's question this run helps answer.")
        if not isinstance(why, str) or not why.strip():
            raise ToolError("why: one line on why this run.")
        from src.workflow.RunManager import PURPOSE_KEY, clean_purpose
        params[PURPOSE_KEY] = clean_purpose({"by": BY, "question": question, "why": why})
        state = runner.start(self.app_root, self.workspace, workflow, entry["class"], params,
                             name[:100], self.online, self._multi_run(entry))
        state["link"] = self._page_link(entry["run_page"])
        return state

    def _get_run_status(self, workflow, wait=0) -> dict:
        workflow, entry, _ = self._workflow(workflow)
        if isinstance(wait, bool) or not isinstance(wait, (int, float)):
            raise ToolError("wait is a number of seconds.")
        until = time.monotonic() + max(0, min(float(wait), 60))
        state = runner.status(self.workspace, workflow, self.online)
        while state.get("status") in ("queued", "running") and time.monotonic() < until:
            time.sleep(min(2.0, max(0.1, until - time.monotonic())))
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
        runs = self._runs_of(entry, workflow_dir)
        if runs is None:
            results = Path(workflow_dir, "results")
            has = results.is_dir() and any(results.iterdir())
            return {"multi_run": False, "runs": [{"id": None, "name": "Last run",
                                                  "has_results": has}] if has else []}
        return {"multi_run": True, "runs": [
            {k: r.get(k) for k in ("id", "name", "status", "created", "finished", "adds_to",
                                   "purpose") if r.get(k)}
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

    # -- results as components ---------------------------------------------------

    ASSISTANT_VIEW = "custom-assistant"  # name prefix of the views save_view makes

    def _catalog(self, entry: dict) -> dict:
        cat = look.catalog(entry)
        if cat is None:
            raise ToolError("This workflow's results page is not built from components; "
                            "use list_results and read_result.")
        return cat

    def _list_result_views(self, workflow, run_id=None) -> dict:
        from src.layout_manager.layout import (by_assistant, explanation, load_views,
                                               missing_analyses, view_runs)
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
        views = []
        for v in state["views"]:
            item = {"name": v["name"], "label": v["label"], "components": v["rows"],
                    "ready_made": bool(v.get("preset"))}
            if v.get("help"):
                item["help"] = v["help"]
            if by_assistant(v):
                item.update(saved_by_you=True, runs=view_runs(v), question=v.get("question", ""),
                            explanation=explanation(v))
            views.append(item)
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

    def _views_state(self, workflow_dir: Path, entry: dict):
        from src.layout_manager.layout import load_views
        cat = self._catalog(entry)
        default = cat["presets"][0]["layout"] if cat["presets"] else [[c["name"]] for c in cat["components"]]
        path = Path(workflow_dir, cat["layout"])
        return cat, path, load_views(path, cat["components"], cat["presets"], default)

    def _save_view(self, workflow, label, components, question, explanation, runs=None,
                   side_by_side=False, defaults=None, name=None) -> dict:
        from src.layout_manager.layout import (ASSISTANT, MAX_POINTS, by_assistant, clean_defaults,
                                               missing_analyses, save_views, validate_layout)
        workflow, entry, workflow_dir = self._workflow(workflow)
        cat, path, state = self._views_state(workflow_dir, entry)
        label = " ".join(str(label or "").split())
        if not label or len(label) > 60:
            raise ToolError("label is one to 60 characters.")
        if not isinstance(question, str) or not question.strip():
            raise ToolError("question is the person's question, in their words.")
        if isinstance(explanation, str):
            explanation = [explanation]
        if (not isinstance(explanation, list) or not 1 <= len(explanation) <= MAX_POINTS
                or not all(isinstance(p, str) and p.strip() for p in explanation)):
            raise ToolError(f"explanation is a list of one to {MAX_POINTS} points.")
        if any(len(p) > 300 for p in explanation):
            raise ToolError("Keep each point of the explanation to one sentence (300 characters).")
        if isinstance(components, list) and components and all(isinstance(c, str) for c in components):
            components = [[c] for c in components]
        problem = validate_layout([components], cat["components"])
        if problem:
            raise ToolError(f"Cannot show these components: {problem.replace('Experiment 1', 'The view')}.")
        rows = [list(r) for r in components]

        manager = self._runs_of(entry, workflow_dir)
        if manager is not None:
            if runs is None:
                runs = [manager.latest()] if manager.latest() else []
            if (not isinstance(runs, list) or not 1 <= len(runs) <= 5
                    or not all(isinstance(r, str) for r in runs) or len(set(runs)) != len(runs)):
                raise ToolError("runs lists one to five different runs from list_runs.")
            for run in runs:
                info = manager.get(run)
                if info is None:
                    raise ToolError(f"No run {run!r}. See list_runs.")
                if info.get("status") != "finished":
                    raise ToolError(f"Run {run!r} is {info.get('status')}; show finished runs only.")
                have = look.available(cat["class"], workflow_dir, run)
                lacking = missing_analyses([n for r in rows for n in r], cat["components"], have)
                if lacking:
                    raise ToolError(f"Run {run!r} was not processed with {', '.join(lacking)}, "
                                    "which these components need; add it with follow_up.")
        elif runs:
            raise ToolError("This workflow keeps one result set; leave runs out.")
        else:
            runs = []
        if side_by_side and len(runs) != 2:
            raise ToolError("side_by_side shows exactly two runs.")
        if defaults is not None:
            if not isinstance(defaults, list) or len(defaults) > max(1, len(runs)):
                raise ToolError("defaults has one entry per run, in the order of runs.")
            defaults = [dict(d, dataset=runs[i]) if isinstance(d, dict) and runs else d
                        for i, d in enumerate(defaults)]
            defaults = clean_defaults(defaults)

        views = state["views"]
        if name is not None:
            mine = next((v for v in views if v["name"] == name), None)
            if mine is None or not by_assistant(mine):
                raise ToolError(f"{name!r} is not a view you saved. See list_result_views.")
        else:
            taken = {v["name"] for v in views}
            name = next(f"{self.ASSISTANT_VIEW}-{n}" for n in range(1, len(taken) + 2)
                        if f"{self.ASSISTANT_VIEW}-{n}" not in taken)
            mine = None
        if label.lower() in {v["label"].lower() for v in views if v["name"] != name}:
            raise ToolError(f"A view is called {label!r} already; give this one another label.")
        question = " ".join(question.split())[:500]
        view = {"name": name, "label": label, "rows": rows, "preset": False, "in_bar": True,
                "by": ASSISTANT, "question": question,
                "explanation": [" ".join(p.split()) for p in explanation],
                "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if runs:
            view["runs"] = list(runs)
        if defaults:
            view["defaults"] = defaults
        # Views of an earlier question go to More; this answer's stay in the bar
        for v in views:
            if by_assistant(v) and v["name"] != name and v.get("question") != question:
                v["in_bar"] = False
        if mine is not None:
            views[views.index(mine)] = view
        else:
            views.insert(sum(v.get("in_bar", True) for v in views), view)
        state.update(current=name, experiments=max(1, len(runs)), side_by_side=bool(side_by_side))
        save_views(path, state)
        return {"view": name, "label": label, "runs": list(runs), "components": rows,
                "note": "Open it with show_in_app(view=...)."}

    def _delete_view(self, workflow, name) -> dict:
        from src.layout_manager.layout import by_assistant, save_views
        workflow, entry, workflow_dir = self._workflow(workflow)
        _, path, state = self._views_state(workflow_dir, entry)
        mine = next((v for v in state["views"] if v["name"] == name), None)
        if mine is None or not by_assistant(mine):
            raise ToolError(f"{name!r} is not a view you saved; only those can be deleted.")
        state["views"].remove(mine)
        if state["current"] == name:
            state.update(current=state["views"][0]["name"], experiments=1, side_by_side=False)
        save_views(path, state)
        return {"deleted": name}

    def _open_view(self, workflow_dir: Path, entry: dict, view: str) -> dict:
        from src.layout_manager.layout import save_views
        _, path, state = self._views_state(workflow_dir, entry)
        chosen = next((v for v in state["views"] if v["name"] == view), None)
        if chosen is None:
            raise ToolError(f"No view {view!r}. See list_result_views.")
        runs = chosen.get("runs") or []
        state.update(current=view, experiments=max(1, len(runs)) if runs else 1)
        if not runs:
            state["side_by_side"] = False
        save_views(path, state)
        return chosen

    def _show_in_app(self, workflow, page="results", run_id=None, note="", view=None) -> dict:
        workflow, entry, workflow_dir = self._workflow(workflow)
        if page not in ("configure", "run", "results"):
            raise ToolError("page must be configure, run or results.")
        page_file = entry.get(f"{page}_page") or ""
        if not page_file:
            raise ToolError(f"This app names no {page} page for {workflow}.")
        if run_id is not None:
            runs = self._runs_of(entry, workflow_dir)
            if runs is None:
                raise ToolError("This workflow keeps one result set; leave run_id out.")
            if not isinstance(run_id, str) or runs.get(run_id) is None:
                raise ToolError(f"No run {run_id!r}. See list_runs.")
        if not isinstance(note, str):
            raise ToolError("note must be text.")
        if view is not None:
            if page != "results":
                raise ToolError("view is for the results page.")
            chosen = self._open_view(workflow_dir, entry, view)
            if run_id is None and chosen.get("runs"):
                run_id = chosen["runs"][0]
        request = show.write(self.workspace, {"workflow": workflow, "page": page,
                                              "page_file": page_file, "run_id": run_id,
                                              "note": note.strip()[:500]})
        return {"shown": True, "page": page, "run_id": run_id, "view": view, "id": request["id"],
                "link": self._page_link(page_file)}

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
