"""An assistant's own analysis, recorded by the app as it happens.

The assistant does not click through a workflow here: it runs the TOPP tools
of its own choosing on the workspace's input files and on the results of any
run, and the app records every step the way the workflow framework records a
workflow's: ``CommandExecutor.run_topp`` writes the step, with the tool's
version, its parameters and its input and output files, to the analysis's
``logs/progress.json``. Figures and tables the assistant writes itself
(``save_figure``, ``save_table``) are recorded as steps too, with the files
they were made from. The processing report of an analysis
(``processing_report.report_for``) therefore says how each result was made,
step by step and why, back to the input files; an analysis built on a run of
a workflow starts with that run's steps.

An analysis is a run folder under ``<workspace>/assistant/runs/<id>/``
(``RunManager``): ``run.json`` (name, question, summary, ``kind: analysis``),
``results/`` (everything its steps write), ``steps/`` (each step asked for and
its outcome), ``logs/`` and ``view.json``, the files the assistant chose to
show the person on the **Assistant analyses** page (``analysis_view.py``).

A tool runs in a process of its own (``python -m src.agent_access.analysis``),
so a long one outlives the call that asked for it; ``step_result`` follows it.
Only TOPP tools run: an executable next to the OpenMS tools, whose ``.ini``
lists every file and parameter passed. Outputs stay in the analysis's results.

Streamlit-free (``CommandExecutor`` imports Streamlit but needs no session).
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from src.workflow.RunManager import FAILED, FINISHED, RUNNING, RunManager

ROOT = "assistant"
KIND = "analysis"
VIEW_FILE = "view.json"
# An executable in the same folder as this one is an OpenMS (TOPP) tool
TOPP_MARKER = "FileInfo"
_TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,80}$")
_PARAM = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_:.-]{0,200}$")
_ID = re.compile(r"^[0-9]{8}-[0-9]{6}(-[0-9]+)?$")
LOG_TAIL = 4000
MAX_TABLE_ROWS = 100_000
SHOWABLE = {".json": "plot", ".tsv": "table", ".csv": "table", ".parquet": "table", ".pq": "table",
            ".png": "image", ".svg": "image", ".jpg": "image", ".jpeg": "image",
            ".md": "text", ".txt": "text"}


class AnalysisError(ValueError):
    """A request about an analysis that cannot be done; the message says why."""


def manager(workspace: Path) -> RunManager:
    return RunManager(Path(workspace, ROOT))


def run_dir(workspace: Path, analysis: str) -> Path:
    if not isinstance(analysis, str) or not _ID.match(analysis):
        raise AnalysisError(f"Not an analysis: {analysis!r}. See list_analyses.")
    runs = manager(workspace)
    if runs.get(analysis) is None:
        raise AnalysisError(f"No analysis {analysis!r}. See list_analyses.")
    return runs.run_dir(analysis)


def results_dir(workspace: Path, analysis: str) -> Path:
    return Path(run_dir(workspace, analysis), "results")


# -- an analysis -------------------------------------------------------------------

def begin(workspace: Path, name: str, question: str = "", based_on: Path | None = None,
          based_on_name: str = "") -> str:
    """A new analysis; ``based_on`` is a run folder (or a workflow folder) it builds on.

    The analysis takes that run's settings and recorded steps, so its report
    starts from the input files the run was made from.
    """
    runs = manager(workspace)
    params = Path(based_on, "params.json") if based_on else None
    analysis = runs.new_run(name or "Analysis", params if params and params.is_file() else None)
    run = runs.get(analysis)
    run.update(kind=KIND, by="assistant", question=str(question or "")[:2000])
    folder = runs.run_dir(analysis)
    if based_on:
        run["based_on"] = {"path": Path(os.path.relpath(based_on, workspace)).as_posix(),
                           "name": based_on_name}
        progress = Path(based_on, "logs", "progress.json")
        if progress.is_file():
            Path(folder, "logs").mkdir(exist_ok=True)
            shutil.copy2(progress, Path(folder, "logs", "progress.json"))
        stored = runs.params(analysis)
        if isinstance(stored, dict):
            stored["_follow_up"] = {"name": based_on_name, "note": "analysed further by the AI assistant"}
            _write_json(runs.params_file(analysis), stored)
    runs._write(analysis, run)  # pylint: disable=protected-access
    Path(folder, "steps").mkdir(exist_ok=True)
    return analysis


def finish(workspace: Path, analysis: str, summary: str = "", failed: bool = False) -> dict:
    runs = manager(workspace)
    folder = run_dir(workspace, analysis)
    if running_step(folder) is not None:
        raise AnalysisError("A step is still running; wait for it with get_step.")
    run = runs.get(analysis)
    if summary:
        run["summary"] = str(summary)[:20000]
    # Its logs are its own already (a workflow's are copied in by RunManager.finish)
    run.update(status=FAILED if failed else FINISHED, finished=time.strftime("%Y-%m-%dT%H:%M:%S"))
    runs._write(analysis, run)  # pylint: disable=protected-access
    return run


def list_analyses(workspace: Path) -> list[dict]:
    return [{k: run[k] for k in ("id", "name", "status", "created", "finished", "question", "summary")
             if run.get(k)} for run in manager(workspace).list_runs(None)]


# -- files -------------------------------------------------------------------------

def _external(workspace: Path) -> set[Path]:
    """Files the workspace references in place (external_files.txt) instead of copying."""
    out = set()
    for ext in Path(workspace).glob("*/input-files/*/external_files.txt"):
        try:
            for line in ext.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    out.add(Path(line.strip()).resolve())
        except OSError:
            pass
    return out


def input_path(workspace: Path, analysis: str, value) -> Path:
    """A file a step reads: in the analysis's results, or anywhere in the workspace."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise AnalysisError(f"Not a file path: {value!r}.")
    workspace = Path(workspace).resolve()
    results = results_dir(workspace, analysis).resolve()
    candidates = [Path(value)] if Path(value).is_absolute() else [Path(results, value), Path(workspace, value)]
    for path in candidates:
        resolved = path.resolve()
        inside = resolved.is_relative_to(workspace) and not any(
            p.startswith(".") for p in resolved.relative_to(workspace).parts)
        if (inside or resolved in _external(workspace)) and resolved.exists():
            return resolved
    raise AnalysisError(f"No file {value!r} in this analysis or the workspace (paths are relative "
                        "to the analysis's results, or to the workspace).")


def output_path(workspace: Path, analysis: str, value) -> Path:
    """A file a step writes: always in the analysis's results."""
    results = results_dir(workspace, analysis).resolve()
    if not isinstance(value, str) or not value or Path(value).is_absolute() or "\x00" in value:
        raise AnalysisError(f"An output is a file name in the analysis's results, not {value!r}.")
    path = Path(results, value).resolve()
    if not path.is_relative_to(results) or path == results:
        raise AnalysisError(f"An output must stay in the analysis's results: {value!r}.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def files(workspace: Path, analysis: str) -> list[dict]:
    results = results_dir(workspace, analysis)
    return [{"path": p.relative_to(results).as_posix(), "size": p.stat().st_size}
            for p in sorted(results.rglob("*")) if p.is_file()]


def _paths(workspace, analysis, mapping, resolve, what) -> dict:
    if mapping is None:
        return {}
    if not isinstance(mapping, dict):
        raise AnalysisError(f"{what} maps a name to a file path or a list of them.")
    out = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not _PARAM.match(key):
            raise AnalysisError(f"Not a name for {what}: {key!r}.")
        values = value if isinstance(value, list) else [value]
        if not values:
            raise AnalysisError(f"{what} {key!r} names no file.")
        out[key] = [str(resolve(workspace, analysis, v)) for v in values]
    return out


# -- tool steps --------------------------------------------------------------------

def tool_step(workspace: Path, analysis: str, tool: str, inputs: dict, outputs: dict,
              params: dict | None = None, why: str = "") -> dict:
    if not isinstance(tool, str) or not _TOOL.match(tool):
        raise AnalysisError(f"Not a TOPP tool name: {tool!r}.")
    if params is not None and not isinstance(params, dict):
        raise AnalysisError("params maps a parameter (e.g. algorithm:common:noise_threshold_int) to a value.")
    for key, value in (params or {}).items():
        if not isinstance(key, str) or not _PARAM.match(key):
            raise AnalysisError(f"Not a parameter: {key!r}.")
        if not isinstance(value, (str, int, float, bool, list)) or (
                isinstance(value, list) and not all(isinstance(v, (str, int, float)) for v in value)):
            raise AnalysisError(f"{key}: a value is text, a number, true/false or a list of them.")
    ins = _paths(workspace, analysis, inputs, input_path, "inputs")
    outs = _paths(workspace, analysis, outputs, output_path, "outputs")
    if not outs:
        raise AnalysisError("Name at least one output file.")
    return {"kind": "topp", "tool": tool, "inputs": ins, "outputs": outs,
            "params": params or {}, "why": str(why or "")[:1000]}


def is_topp_tool(tool: str) -> bool:
    exe, marker = shutil.which(tool), shutil.which(TOPP_MARKER)
    return bool(exe and marker and Path(exe).resolve().parent == Path(marker).resolve().parent)


def submit(workspace: Path, analysis: str, step: dict, app_root: Path) -> int:
    """Start a tool step in a process of its own; returns its number."""
    folder = run_dir(workspace, analysis)
    _check_open(workspace, analysis, folder)
    if not is_topp_tool(step["tool"]):
        raise AnalysisError(f"{step['tool']} is not an OpenMS tool installed here.")
    number = _record(folder, step)
    proc = subprocess.Popen(  # noqa: S603 - this module, the app's own interpreter
        [sys.executable, "-m", "src.agent_access.analysis", str(folder), str(number)],
        cwd=str(app_root), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    _write_json(Path(folder, "steps", f"{number:03d}.pid.json"), {"pid": proc.pid})
    return number


def _check_open(workspace: Path, analysis: str, folder: Path) -> None:
    if manager(workspace).get(analysis).get("status") != RUNNING:
        raise AnalysisError("This analysis is finished; begin a new one.")
    busy = running_step(folder)
    if busy is not None:
        raise AnalysisError(f"Step {busy} is still running; wait for it with get_step.")


def _record(folder: Path, step: dict) -> int:
    steps = Path(folder, "steps")
    steps.mkdir(exist_ok=True)
    number = 1 + max((int(p.stem) for p in steps.glob("*.json") if p.stem.isdigit()), default=0)
    _write_json(Path(steps, f"{number:03d}.json"), {**step, "number": number, "submitted": time.time()})
    return number


def running_step(folder: Path) -> int | None:
    for path in sorted(Path(folder, "steps").glob("*.json")):
        if not path.stem.isdigit():
            continue
        number = int(path.stem)
        if Path(folder, "steps", f"{number:03d}.result.json").exists():
            continue
        pid = (_read_json(Path(folder, "steps", f"{number:03d}.pid.json")) or {}).get("pid")
        if pid and _alive(pid):
            return number
        if pid:
            _write_json(Path(folder, "steps", f"{number:03d}.result.json"),
                        {"number": number, "ok": False, "error": "The step's process ended without a result."})
    return None


def step_result(workspace: Path, analysis: str, number, wait: float = 0) -> dict:
    folder = run_dir(workspace, analysis)
    if not isinstance(number, int) or not Path(folder, "steps", f"{number:03d}.json").exists():
        raise AnalysisError(f"No step {number!r} in this analysis.")
    deadline = time.time() + max(0.0, min(float(wait), 600.0))
    result_file = Path(folder, "steps", f"{number:03d}.result.json")
    while True:
        result = _read_json(result_file)
        if result is not None:
            return result
        if running_step(folder) != number:
            return _read_json(result_file) or {"number": number, "ok": False,
                                               "error": "The step's process ended without a result."}
        if time.time() >= deadline:
            return {"number": number, "running": True,
                    "note": "Still running; ask again with get_step and a wait."}
        time.sleep(0.5)


def _alive(pid: int) -> bool:
    try:  # a finished child of this process that nobody reaped yet
        done, _ = os.waitpid(int(pid), os.WNOHANG)
        if done:
            return False
    except (ChildProcessError, OSError, ValueError):
        pass
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return False
    return True


# -- figures and tables the assistant writes -----------------------------------------

def save_figure(workspace: Path, analysis: str, file: str, figure, made_from=None, why: str = "") -> dict:
    """Write a Plotly figure (its JSON, as ``fig.to_json()`` gives it) and record it as a step."""
    if isinstance(figure, str):
        try:
            figure = json.loads(figure)
        except ValueError as e:
            raise AnalysisError(f"figure is not JSON: {e}") from e
    if not isinstance(figure, dict) or not isinstance(figure.get("data"), list):
        raise AnalysisError("figure is a Plotly figure: {\"data\": [traces], \"layout\": {...}}.")
    if not str(file).lower().endswith(".json"):
        raise AnalysisError("A figure's file ends in .json.")
    return _write_step(workspace, analysis, "figure", file, json.dumps(figure), made_from, why)


def save_table(workspace: Path, analysis: str, file: str, columns, rows, made_from=None, why: str = "") -> dict:
    """Write a table (TSV) the assistant put together and record it as a step."""
    if not (isinstance(columns, list) and columns and all(isinstance(c, str) for c in columns)):
        raise AnalysisError("columns lists the column names.")
    if not (isinstance(rows, list) and len(rows) <= MAX_TABLE_ROWS
            and all(isinstance(r, list) and len(r) == len(columns) for r in rows)):
        raise AnalysisError(f"rows is a list of at most {MAX_TABLE_ROWS} rows, each with one value per column.")
    if not str(file).lower().endswith(".tsv"):
        raise AnalysisError("A table's file ends in .tsv.")

    def cell(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        return str(v).replace("\t", " ").replace("\n", " ")
    text = "\n".join("\t".join(cell(v) for v in r) for r in [columns] + rows) + "\n"
    return _write_step(workspace, analysis, "table", file, text, made_from, why)


def _write_step(workspace, analysis, kind, file, text, made_from, why) -> dict:
    from src.workflow.processing_report import command_io
    from src.workflow.progress import RunProgress

    folder = run_dir(workspace, analysis)
    _check_open(workspace, analysis, folder)
    if isinstance(made_from, str):
        made_from = [made_from]
    sources = _paths(workspace, analysis, {"in": made_from}, input_path, "made_from") if made_from else {}
    out = output_path(workspace, analysis, file)
    number = _record(folder, {"kind": kind, "file": file, "inputs": sources, "why": str(why or "")[:1000]})
    progress = RunProgress(folder)
    label = "Figure" if kind == "figure" else "Table"
    index = progress.start_step(
        f"{label} by the AI assistant", [out.name],
        provenance={"kind": "assistant", "program": f"{label} by the AI assistant", "version": "",
                    "params": {}, "by": "assistant", "note": str(why or ""),
                    "io": command_io({**sources, "out": [str(out)]}, 1)})
    progress.file_started(index, 0)
    out.write_text(text, encoding="utf-8")
    progress.file_finished(index, 0, True)
    progress.end_step(index)
    result = {"number": number, "ok": True,
              "written": [{"file": out.relative_to(results_dir(workspace, analysis).resolve()).as_posix(),
                           "size": out.stat().st_size}]}
    _write_json(Path(folder, "steps", f"{number:03d}.result.json"), result)
    return result


# -- what the assistant shows ---------------------------------------------------------

def show(workspace: Path, analysis: str, items: list) -> list[dict]:
    """Make ``items`` ({file, title?, caption?}) what the analysis page shows."""
    if not isinstance(items, list) or not items:
        raise AnalysisError("items lists the result files to show, each {file, title, caption}.")
    results = results_dir(workspace, analysis).resolve()
    chosen = []
    for item in items:
        if isinstance(item, str):
            item = {"file": item}
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            raise AnalysisError("Each item is {file, title, caption}.")
        path = Path(results, item["file"]).resolve()
        if not path.is_relative_to(results) or not path.is_file():
            raise AnalysisError(f"No result file {item['file']!r} in this analysis.")
        kind = SHOWABLE.get(path.suffix.lower())
        if kind is None:
            raise AnalysisError(f"{item['file']}: the page shows Plotly figures (.json), tables "
                                "(.tsv, .csv, .parquet), images and text (.md, .txt).")
        chosen.append({"file": path.relative_to(results).as_posix(), "kind": kind,
                       "title": str(item.get("title") or path.stem)[:200],
                       "caption": str(item.get("caption") or "")[:2000]})
    _write_json(Path(run_dir(workspace, analysis), VIEW_FILE), {"items": chosen, "t": time.time()})
    return chosen


def shown(folder: Path) -> list[dict]:
    return (_read_json(Path(folder, VIEW_FILE)) or {}).get("items") or []


# -- in the step's own process --------------------------------------------------------

def execute(folder: Path, number: int) -> dict:
    """Run tool step ``number`` of the analysis in ``folder`` through the framework."""
    from src.workflow.CommandExecutor import CommandExecutor
    from src.workflow.Logger import Logger
    from src.workflow.ParameterManager import ParameterManager

    step = _read_json(Path(folder, "steps", f"{number:03d}.json"))
    logger = Logger(folder)
    pm = ParameterManager(folder)
    # A step's parameters are the ones the assistant passes, never the
    # stored settings of a workflow for the same tool.
    pm.params_file = Path(folder, "tool-params.json")
    executor = CommandExecutor(folder, logger, pm)
    executor.pid_dir.mkdir(parents=True, exist_ok=True)
    log = Path(folder, "logs", "all.log")
    start = log.stat().st_size if log.exists() else 0
    before = len((_read_json(Path(folder, "logs", "progress.json")) or {}).get("steps") or [])
    tool = step["tool"]
    logger.log(f"Assistant: {tool}" + (f" ({step['why']})" if step.get("why") else ""), 0)
    error = _check_tool(pm, tool, step)
    ok = False
    if not error:
        ok = executor.run_topp(tool, {**step["inputs"], **step["outputs"]}, custom_params=step["params"])
        _annotate(executor, before, step)
    shutil.rmtree(executor.pid_dir, ignore_errors=True)
    results = Path(folder, "results").resolve()
    outputs = [Path(p) for paths in step["outputs"].values() for p in paths]
    result = {"number": number, "ok": bool(ok) and all(p.exists() for p in outputs),
              "written": [{"file": p.relative_to(results).as_posix(), "size": _size(p)}
                          for p in outputs if p.exists()]}
    missing = [p.relative_to(results).as_posix() for p in outputs if not p.exists()]
    if missing and not error:
        result["missing_outputs"] = missing
    if error:
        result["error"] = error
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            f.seek(start)
            result["log"] = f.read()[-LOG_TAIL:].strip()
    except OSError:
        pass
    return result


def _size(path: Path) -> int:
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return path.stat().st_size


def _annotate(executor, before: int, step: dict) -> None:
    """Add why the assistant ran the step to what the report reads."""

    def change(state):
        for entry in state["steps"][before:]:
            if entry.get("provenance"):
                entry["provenance"]["by"] = "assistant"
                if step.get("why"):
                    entry["provenance"]["note"] = step["why"]
    executor.progress._update(change)  # pylint: disable=protected-access


def _check_tool(pm, tool: str, step: dict) -> str:
    """Why the tool cannot run with these files and parameters ('' if it can)."""
    if not pm.create_ini(tool):
        return pm.ini_errors.get(tool) or f"{tool} is not installed here."
    kinds = _param_kinds(Path(pm.ini_dir, f"{tool}.ini"), tool)
    file_params = ", ".join(f"-{k} ({v})" for k, v in kinds.items() if v.endswith(("-file", "-prefix")))
    for key in step["inputs"]:
        if kinds.get(key) != "input-file":
            return f"{tool} has no input file parameter -{key}. Its file parameters: {file_params}."
    for key in step["outputs"]:
        if kinds.get(key) not in ("output-file", "output-prefix"):
            return f"{tool} has no output file parameter -{key}. Its file parameters: {file_params}."
    for key in step["params"]:
        if key not in kinds:
            return f"{tool} has no parameter {key}."
        if kinds[key].endswith(("-file", "-prefix")) or key in ("ini", "write_ini", "log"):
            return f"-{key} is a file: give it in inputs or outputs."
    stored = _read_json(pm.params_file) or {}
    stored.setdefault("_flag_params", {})[tool] = [k for k, v in kinds.items() if v == "flag"]
    _write_json(pm.params_file, stored)
    return ""


def _param_kinds(ini: Path, tool: str) -> dict:
    """Parameter path -> its type in the tool's .ini (a bool item is a flag)."""
    try:
        root = ET.parse(ini).getroot()
    except (ET.ParseError, OSError):
        return {}
    out = {}

    def walk(node, path):
        for child in node:
            name = child.get("name", "")
            if child.tag == "NODE":
                walk(child, path + [name])
            elif child.tag in ("ITEM", "ITEMLIST"):
                full = path + [name]
                if len(full) > 2 and full[0] == tool and full[1] == "1":  # <tool>:1:<path>
                    typ = child.get("type", "")
                    out[":".join(full[2:])] = "flag" if typ == "bool" else typ
    walk(root, [])
    return out


def describe_tool(workspace: Path, tool: str, include_advanced: bool = False) -> dict:
    """A TOPP tool's files and parameters, from its .ini."""
    from src.workflow.ParameterManager import ParameterManager

    if not isinstance(tool, str) or not _TOOL.match(tool) or not is_topp_tool(tool):
        raise AnalysisError(f"{tool!r} is not an OpenMS tool installed here.")
    pm = ParameterManager(Path(workspace, ROOT))
    if not pm.create_ini(tool):
        raise AnalysisError(pm.ini_errors.get(tool) or f"{tool} gave no parameters.")
    try:
        root = ET.parse(Path(pm.ini_dir, f"{tool}.ini")).getroot()
    except (ET.ParseError, OSError) as e:
        raise AnalysisError(f"{tool}'s parameters cannot be read: {e}") from e
    out = {"tool": tool, "version": pm.tool_version(tool) or "", "files": [], "parameters": []}

    def walk(node, path):
        for child in node:
            name = child.get("name", "")
            if child.tag == "NODE":
                if not (path == [tool] and name != "1"):
                    walk(child, path + [name])
                continue
            full = path + [name]
            if child.tag not in ("ITEM", "ITEMLIST") or len(full) < 3:
                continue
            key = ":".join(full[2:])
            typ = child.get("type", "")
            tags = child.get("tags", "")
            if key in ("ini", "write_ini", "log", "threads", "no_progress", "debug", "test", "force", "env_var"):
                continue
            item = {"name": key, "type": "flag" if typ == "bool" else typ,
                    "description": (child.get("description") or "")[:300]}
            if child.tag == "ITEMLIST":
                item["list"] = True
                item["default"] = [e.get("value") for e in child if e.tag == "LISTITEM"]
            else:
                item["default"] = child.get("value", "")
            if child.get("restrictions"):
                item["allowed"] = child.get("restrictions")
            if typ.endswith(("-file", "-prefix")):
                item["formats"] = child.get("supported_formats", "")
                out["files"].append(item)
            elif include_advanced or not (child.get("advanced") == "true" or "advanced" in tags):
                out["parameters"].append(item)
    walk(root, [])
    return out


# -- helpers -------------------------------------------------------------------------

def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, value) -> None:
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    folder, number = Path(argv[0]), int(argv[1])
    try:
        result = execute(folder, number)
    except Exception as e:  # noqa: BLE001 - the step's outcome is reported, never lost
        result = {"number": number, "ok": False, "error": f"{type(e).__name__}: {e}"}
    result["ended"] = time.time()
    _write_json(Path(folder, "steps", f"{number:03d}.result.json"), result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
