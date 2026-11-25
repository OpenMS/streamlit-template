"""How a run came about, for the **History** of a run (``run_widgets``).

Streamlit-free: ``timeline`` reads the run's ``run.json`` and parameters
(which run it follows, adds files to or reuses results of, when it started and
ended), ``changed_settings`` lists the settings a processing report
(``processing_report.report_for``) records as different from the defaults.
"""

from typing import List, Optional

from .RunManager import ADDS_TO, FOLLOW_UP_KEY, RunManager, format_time

OUTCOMES = {
    "finished": "finished",
    "failed": "failed",
    "cancelled": "was cancelled",
    "interrupted": "was interrupted",
}


def _name(runs: RunManager, run_id: Optional[str]) -> str:
    run = runs.get(run_id) if run_id else None
    return (run or {}).get("name") or str(run_id or "")


def timeline(runs: RunManager, run_id: str) -> List[str]:
    """What happened to ``run_id``, oldest first, as Markdown lines."""
    run = runs.get(run_id)
    if run is None:
        return []
    params = runs.params(run_id) or {}
    follow = params.get(FOLLOW_UP_KEY)
    follow = follow if isinstance(follow, dict) else {}
    events = []
    origin = ""
    if follow.get("reuses"):
        reused = ", ".join(f"**{_name(runs, r)}**" for r in follow["reuses"])
        kept = ", ".join(follow.get("kept") or [])
        origin = f"reusing the results of {kept} from {reused}" if kept else f"reusing results of {reused}"
    elif run.get(ADDS_TO) or follow.get("adds_to"):
        origin = f"adding files to **{_name(runs, run.get(ADDS_TO) or follow.get('adds_to'))}**"
    elif follow.get("name"):
        origin = f"from the settings of **{follow['name']}**"
        if follow.get("note"):
            origin += f" ({follow['note']})"
    started = f"Started {format_time(run.get('created'))}"
    events.append(f"{started}, {origin}." if origin else f"{started}.")
    status = run.get("status", "")
    if status in OUTCOMES and run.get("finished"):
        events.append(f"{OUTCOMES[status].capitalize()} {format_time(run.get('finished'))}.")
    elif status == "running":
        events.append("Still running.")
    added = [r for r in runs.experiment(run_id) if r != run_id] if runs.experiment_root(run_id) == run_id else []
    if added:
        names = ", ".join(f"**{_name(runs, r)}**" for r in added)
        events.append(f"Files were added to it by {names}.")
    return events


def changed_settings(report: dict) -> List[List[str]]:
    """``[tool, parameter, value]`` for every setting of the run that is not its default.

    The workflow's own settings come first (tool "Workflow"), then each tool
    call's parameters as the processing report recorded them; a tool called
    several times with the same values is listed once.
    """
    rows, seen = [], set()
    for key, value in (report.get("settings") or {}).items():
        rows.append(["Workflow", str(key), str(value)])
    for step in report.get("steps") or []:
        tool = step.get("tool") or step.get("program") or ""
        for key, value in (step.get("params") or {}).items():
            row = (tool, str(key), str(value))
            if row not in seen:
                seen.add(row)
                rows.append(list(row))
    return rows
