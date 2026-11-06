"""The processing report: how each input file of a run was processed.

Built from what the run recorded in ``logs/progress.json`` (``progress.py``):
every tool call with its program, version, the parameters that differ from the
tool's defaults, and the files each command read and wrote. Following the
files written by one call into the next tells, for each input file, every tool
that worked on it, also where it was one of several files (feature linking,
a protein inference over all runs).

``build_report()`` returns a plain dict; ``to_markdown()`` and ``to_pdf()``
write it out. Streamlit-free: ``RunManager.zip()`` puts the report into a run's
ZIP, and the queue worker may write it.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPORT_NAME = "processing-report"

_VERSION = re.compile(r'<ITEM\s+name="version"\s+value="([^"]*)"')


# ---- What the executor records ----


def ini_version(ini_path: Path) -> Optional[str]:
    """The version a TOPP tool wrote into its .ini (``-write_ini``), or None."""
    try:
        with open(ini_path, encoding="utf-8", errors="replace") as f:
            head = f.read(65536)
    except OSError:
        return None
    match = _VERSION.search(head)
    return match.group(1) if match and match.group(1) else None


def _flatten(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return [str(value)] if value not in (None, "") else []


# Inputs every command of a call shares (a protein database, a design), named by
# their run_topp key. They are listed with the call, not as input files of their own.
SHARED_INPUT_KEYS = {"database", "fasta", "design", "exp_design", "in_design"}


def command_io(input_output: Dict[str, list], n_commands: int) -> List[dict]:
    """The files each command reads and writes, as ``run_topp`` pairs them.

    A key starting with ``out`` names outputs, every other key inputs
    (``in``, ``database``, ``design``, ...). Inputs every command shares (one
    file for several commands, or a key in ``SHARED_INPUT_KEYS``) are also
    listed as ``shared``, so the report does not take them for input files.
    """
    commands = []
    for i in range(n_commands):
        inputs: List[str] = []
        outputs: List[str] = []
        shared: List[str] = []
        for key, values in input_output.items():
            if not isinstance(values, (list, tuple)) or not values:
                continue
            value = values[i] if len(values) > 1 and i < len(values) else values[0]
            if key.lower().startswith("out"):
                outputs.extend(_flatten(value))
                continue
            inputs.extend(_flatten(value))
            if key.lower() in SHARED_INPUT_KEYS or (n_commands > 1 and len(values) == 1):
                shared.extend(_flatten(value))
        command = {"inputs": inputs, "outputs": outputs}
        if shared and len(shared) < len(inputs):
            command["shared"] = shared
        commands.append(command)
    return commands


def _looks_like_path(value: str) -> bool:
    return ("/" in value or "\\" in value) and Path(value).exists()


def report_params(params: Dict[str, Any]) -> Dict[str, str]:
    """Parameters as the report shows them: text, file names instead of paths.

    ``threads`` is left out (it depends on the machine, not the method).
    """
    out: Dict[str, str] = {}
    for key, value in params.items():
        if key == "threads" or isinstance(value, dict):
            continue
        if isinstance(value, (list, tuple)):
            items = [Path(str(v)).name if _looks_like_path(str(v)) else str(v) for v in value]
            text = ", ".join(items)
        elif isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = Path(str(value)).name if _looks_like_path(str(value)) else str(value)
        out[str(key)] = text.replace("\n", ", ")
    return out


# ---- The report ----


def _name(path: str) -> str:
    return Path(path).name or str(path)


def _fmt_time(seconds: Optional[float]) -> str:
    if not seconds:
        return ""
    return datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M")


def _duration(start: Optional[float], end: Optional[float]) -> str:
    if not start or not end:
        return ""
    seconds = int(max(0, end - start))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min {s} s"
    return f"{s} s"


def _status(entries: Iterable[dict]) -> str:
    statuses = {e.get("status") for e in entries}
    for status in ("failed", "running", "pending"):
        if status in statuses:
            return {"failed": "failed", "running": "not finished", "pending": "not run"}[status]
    return "done"


def _settings(params: Dict[str, Any]) -> Dict[str, str]:
    """The workflow's own settings: not TOPP or Python tool parameters, not file lists."""
    general = {}
    for key, value in (params or {}).items():
        if key.startswith("_") or key == "max_threads" or isinstance(value, dict):
            continue
        if ".py:" in key or ":1:" in key:
            continue
        if isinstance(value, list) and value and all(_looks_like_path(str(v)) for v in value):
            continue
        general[key] = value
    return report_params(general)


def build_report(
    progress: Optional[dict],
    *,
    app_name: str = "",
    app_version: str = "",
    workflow: str = "",
    run: Optional[dict] = None,
    params: Optional[dict] = None,
    setting_labels: Optional[Dict[str, str]] = None,
) -> dict:
    """The report of one run as a dict (see ``to_markdown`` for its parts).

    Args:
        progress: The run's ``progress.json`` (``read_progress``).
        app_name, app_version: From settings.json.
        workflow: The workflow's name.
        run: The run's ``run.json`` (``RunManager.get``), for its name and times.
        params: The parameters the run started with, for the workflow settings.
        setting_labels: Names users know for settings keys (prefix removed).
    """
    progress = progress or {}
    steps_in = progress.get("steps") or []
    aliases = progress.get("aliases") or {}
    produced: Dict[str, set] = {}  # file -> the input files it was made from
    inputs: Dict[str, List[dict]] = {}  # input file name -> tool calls on it
    order: List[str] = []
    steps: List[dict] = []
    software: Dict[str, str] = {}

    def origin(path: str) -> set:
        seen = set()
        while path in aliases and path not in produced and path not in seen:
            seen.add(path)
            path = aliases[path]["source"]
        if path in produced:
            return produced[path]
        name = _name(path)
        if name not in inputs:
            inputs[name] = []
            order.append(name)
        return {name}

    for number, step in enumerate(steps_in, start=1):
        prov = step.get("provenance") or {}
        files = step.get("files") or []
        program = prov.get("program") or step.get("tool", "")
        version = prov.get("version") or ""
        if prov.get("kind") == "python":
            version = version or "Python script"
        if program and prov:
            software.setdefault(program, version)
        entry = {
            "number": number,
            "tool": step.get("tool", program),
            "program": program,
            "kind": prov.get("kind", ""),
            "version": version,
            "params": prov.get("params") or {},
            "status": _status(files),
            "started": _fmt_time(step.get("started")),
            "duration": _duration(step.get("started"), step.get("ended")),
            "commands": len(files),
            "recorded": bool(prov),
        }
        steps.append(entry)
        for index, io in enumerate(prov.get("io") or []):
            roots = set()
            shared = set(io.get("shared") or [])
            for path in io.get("inputs", []):
                if path not in shared:
                    roots |= origin(path)
            for path in io.get("outputs", []):
                produced[path] = roots
            command = files[index] if index < len(files) else {}
            together = len(roots)
            for root in sorted(roots):
                inputs[root].append({
                    "step": number,
                    "tool": entry["tool"],
                    "version": version,
                    "status": _status([command]) if command else entry["status"],
                    "duration": _duration(command.get("started"), command.get("ended")),
                    "with": together - 1,
                    "outputs": [_name(p) for p in io.get("outputs", [])],
                })

    notes = {}
    for path, alias in aliases.items():
        if alias.get("note"):
            for root in origin(path):
                notes.setdefault(root, []).append(alias["note"])

    env = progress.get("environment") or {}
    labels = setting_labels or {}
    settings = {labels.get(k, k): v for k, v in _settings(params or {}).items()}
    run = run or {}
    return {
        "title": f"Processing report: {run.get('name') or workflow or app_name}",
        "app": {"name": app_name, "version": app_version},
        "workflow": workflow,
        "run": {
            "name": run.get("name", ""),
            "status": run.get("status", ""),
            "created": run.get("created", ""),
            "finished": run.get("finished", ""),
            "follows": ((params or {}).get("_follow_up") or {}).get("name", "")
            if isinstance((params or {}).get("_follow_up"), dict) else "",
            "follow_note": ((params or {}).get("_follow_up") or {}).get("note", "")
            if isinstance((params or {}).get("_follow_up"), dict) else "",
        },
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "started": _fmt_time(progress.get("started")),
        "environment": env,
        "software": [{"name": k, "version": v} for k, v in software.items()],
        "settings": settings,
        "inputs": [{"name": n, "calls": inputs[n], "notes": notes.get(n, [])} for n in order],
        "steps": steps,
    }


def report_for(workflow_dir: Path, run_id: Optional[str] = None, settings: Optional[dict] = None,
               workflow: str = "") -> dict:
    """``build_report`` for a run of ``workflow_dir`` (or its last run, without ``run_id``)."""
    from .progress import read_progress  # pylint: disable=import-outside-toplevel

    workflow_dir = Path(workflow_dir)
    latest = run_id is None
    if latest:
        # A multi-run workflow: the newest run, whose logs are still the workflow's own
        runs_dir = Path(workflow_dir, "runs")
        runs = sorted((d for d in runs_dir.iterdir() if Path(d, "run.json").exists()),
                      key=lambda d: d.name, reverse=True) if runs_dir.is_dir() else []
        run_id = runs[0].name if runs else None
    base = Path(workflow_dir, "runs", run_id) if run_id else workflow_dir
    progress = read_progress(base) if not latest else None
    progress = progress or read_progress(workflow_dir if latest else base)
    run, params = None, {}
    if run_id:
        try:
            run = json.loads(Path(base, "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            run = None
    try:
        params = json.loads(Path(base, "params.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        params = {}
    if run_id is None and "_follow_up" not in params:
        # An app without run folders keeps it apart, so the next settings start fresh
        try:
            params["_follow_up"] = json.loads(Path(workflow_dir, "last-follow-up.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if settings is None:
        try:
            settings = json.loads(Path("settings.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            settings = {}
    prefix = f"{workflow_dir.name}-param-"
    return build_report(
        progress,
        app_name=settings.get("app-name", ""),
        app_version=str(settings.get("version", "")),
        workflow=workflow or workflow_dir.name,
        run=run,
        params={k[len(prefix):] if k.startswith(prefix) else k: v for k, v in params.items()},
    )


# ---- Markdown ----


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ") if value not in (None, "") else "–"


def _table(header: List[str], rows: List[List[Any]]) -> List[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def _summary_lines(report: dict) -> List[List[str]]:
    app = report["app"]
    run = report["run"]
    env = report["environment"]
    rows = [["App", " ".join(x for x in (app["name"], app["version"]) if x)]]
    if report["workflow"]:
        rows.append(["Workflow", report["workflow"]])
    if run["name"]:
        rows.append(["Run", run["name"]])
    if run["status"]:
        rows.append(["Status", run["status"]])
    if run.get("follows"):
        rows.append(["Settings from", run["follows"] + (f" ({run['follow_note']})" if run.get("follow_note") else "")])
    if report["started"]:
        rows.append(["Started", report["started"]])
    if run["finished"]:
        rows.append(["Finished", run["finished"].replace("T", " ")[:16]])
    if env.get("pyopenms"):
        rows.append(["pyOpenMS", env["pyopenms"]])
    if env.get("python"):
        rows.append(["Python", env["python"]])
    rows.append(["Report written", report["generated"]])
    return [r for r in rows if r[1]]


def _call_text(call: dict) -> str:
    text = f"{call['tool']}"
    if call["with"]:
        text += f" (with {call['with']} other file{'s' if call['with'] > 1 else ''})"
    return text


def to_markdown(report: dict) -> str:
    """The report as Markdown."""
    md = [f"# {report['title']}", ""]
    md += _table(["", ""], _summary_lines(report))
    md.append("")
    if not report["steps"]:
        md += ["No tool calls were recorded for this run.", ""]
        return "\n".join(md)

    md += ["## Software", ""]
    md += _table(["Tool", "Version"], [[s["name"], s["version"] or "unknown"] for s in report["software"]])
    md.append("")

    if report["settings"]:
        md += ["## Settings", ""]
        md += _table(["Setting", "Value"], [[k, v] for k, v in report["settings"].items()])
        md.append("")

    md += ["## Input files", "",
           "Every tool that worked on each input file, in order. A tool call that "
           "took several files at once is listed under each of them. The parameters "
           "of each call are listed under **Tool calls**.", ""]
    for item in report["inputs"]:
        md += [f"### {item['name']}", ""]
        for note in item["notes"]:
            md += [f"_{note.capitalize()}._", ""]
        md += _table(
            ["Step", "Tool", "Version", "Status", "Time", "Wrote"],
            [[c["step"], _call_text(c), c["version"] or "unknown", c["status"], c["duration"],
              ", ".join(c["outputs"])] for c in item["calls"]],
        )
        md.append("")

    md += ["## Tool calls", "", "Parameters that differ from the tool's defaults.", ""]
    for step in report["steps"]:
        head = f"### Step {step['number']}: {step['tool']}"
        md += [head, ""]
        facts = [f"Version: {step['version'] or 'unknown'}", f"Status: {step['status']}"]
        if step["commands"] > 1:
            facts.append(f"{step['commands']} commands")
        if step["duration"]:
            facts.append(f"Time: {step['duration']}")
        md += [" · ".join(facts), ""]
        if step["params"]:
            md += _table(["Parameter", "Value"], [[k, v] for k, v in step["params"].items()])
        elif step["recorded"]:
            md += ["All parameters at their defaults."]
        else:
            md += ["Parameters were not recorded for this call."]
        md.append("")
    return "\n".join(md)


# ---- PDF ----


def to_pdf(report: dict) -> Optional[bytes]:
    """The report as a PDF, or None when reportlab is not installed."""
    try:
        from reportlab.lib import colors  # pylint: disable=import-outside-toplevel
        from reportlab.lib.pagesizes import A4  # pylint: disable=import-outside-toplevel
        from reportlab.lib.styles import getSampleStyleSheet  # pylint: disable=import-outside-toplevel
        from reportlab.lib.units import mm  # pylint: disable=import-outside-toplevel
        from reportlab.platypus import (  # pylint: disable=import-outside-toplevel
            KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError:
        return None
    from io import BytesIO  # pylint: disable=import-outside-toplevel
    from xml.sax.saxutils import escape  # pylint: disable=import-outside-toplevel

    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)
    head = styles["BodyText"].clone("head", fontSize=8, leading=10, fontName="Helvetica-Bold")
    width = A4[0] - 30 * mm

    def p(text, style=body):
        return Paragraph(escape(str(text if text not in (None, "") else "–")), style)

    def table(header, rows, widths):
        data = ([[p(h, head) for h in header]] if header else []) + [[p(c, small) for c in r] for r in rows]
        t = Table(data, colWidths=[w * width for w in widths], repeatRows=1 if header else 0)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8cad0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0f4")))
        t.setStyle(TableStyle(style))
        return t

    story = [Paragraph(escape(report["title"]), styles["Title"]),
             table(None, _summary_lines(report), [0.25, 0.75]), Spacer(1, 6 * mm)]
    if not report["steps"]:
        story.append(p("No tool calls were recorded for this run."))
    else:
        story += [Paragraph("Software", styles["Heading2"]),
                  table(["Tool", "Version"], [[s["name"], s["version"] or "unknown"] for s in report["software"]], [0.5, 0.5])]
        if report["settings"]:
            story += [Paragraph("Settings", styles["Heading2"]),
                      table(["Setting", "Value"], [[k, v] for k, v in report["settings"].items()], [0.4, 0.6])]
        story += [Paragraph("Input files", styles["Heading2"]),
                  p("Every tool that worked on each input file, in order. A tool call that took several "
                    "files at once is listed under each of them. The parameters of each call are listed "
                    "under Tool calls.")]
        for item in report["inputs"]:
            block = [Paragraph(escape(item["name"]), styles["Heading3"])]
            block += [p(n.capitalize() + ".", small) for n in item["notes"]]
            block.append(table(
                ["Step", "Tool", "Version", "Status", "Time", "Wrote"],
                [[c["step"], _call_text(c), c["version"] or "unknown", c["status"], c["duration"],
                  ", ".join(c["outputs"])] for c in item["calls"]],
                [0.07, 0.28, 0.15, 0.1, 0.1, 0.3]))
            story.append(KeepTogether(block))
        story += [Paragraph("Tool calls", styles["Heading2"]),
                  p("Parameters that differ from the tool's defaults.")]
        for step in report["steps"]:
            facts = [f"Version: {step['version'] or 'unknown'}", f"Status: {step['status']}"]
            if step["commands"] > 1:
                facts.append(f"{step['commands']} commands")
            if step["duration"]:
                facts.append(f"Time: {step['duration']}")
            part = [Paragraph(escape(f"Step {step['number']}: {step['tool']}"), styles["Heading3"]),
                    p(" · ".join(facts), small)]
            if step["params"]:
                part.append(table(["Parameter", "Value"], [[k, v] for k, v in step["params"].items()], [0.45, 0.55]))
            else:
                part.append(p("All parameters at their defaults." if step["recorded"]
                              else "Parameters were not recorded for this call.", small))
            story.append(KeepTogether(part[:2]))
            story += part[2:]

    buffer = BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(15 * mm, 8 * mm, report["title"])
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm,
                      title=report["title"], author=report["app"]["name"],
                      invariant=1).build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def file_stem(report: dict) -> str:
    """A file name for the report, without extension."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", report["run"]["name"] or "").strip("-")
    return f"{REPORT_NAME}-{name}" if name else REPORT_NAME

