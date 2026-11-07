"""The **Assistant analyses** page: what an assistant analysed, and how.

One analysis at a time (``analysis.py``): its question and summary, the
result files the assistant chose to show (``show_analysis``), its steps, and
its processing report. The analysis the assistant showed last is picked when
the page opens from ``show_analysis``.
"""

import json
from pathlib import Path

import pandas as pd
import plotly.io as pio
import streamlit as st

from src.common.common import show_fig, show_table
from src.workflow.processing_report import report_for
from src.workflow.report_ui import report_buttons

from . import analysis
from .ui import enabled

SELECTED = "agent-analysis-selected"
STATUS = {"running": ":material/progress_activity: In progress", "finished": ":material/check: Done",
          "failed": ":material/error: Did not work out"}


def render_page() -> None:
    st.title("Assistant analyses")
    if not enabled():
        st.info("The AI assistant is a developer feature. Unlock developer mode in ⚙️ Settings.")
        return
    workspace = Path(st.session_state.workspace)
    runs = analysis.manager(workspace)
    items = runs.list_runs(None)
    if not items:
        st.info("No analyses yet. Ask the AI assistant connected to this workspace a question "
                "about your data: it analyses it here, and every step it takes is recorded.")
        return
    ids = [r["id"] for r in items]
    names = {r["id"]: f"{r.get('name') or r['id']} · {r['id'][:8]}" for r in items}
    picked = st.session_state.get(SELECTED)
    index = ids.index(picked) if picked in ids else 0
    analysis_id = st.selectbox("Analysis", ids, index=index, format_func=names.get, key="agent-analysis-pick")
    st.session_state[SELECTED] = analysis_id
    _analysis(workspace, analysis_id, runs.get(analysis_id) or {})


def _analysis(workspace: Path, analysis_id: str, run: dict) -> None:
    folder = analysis.run_dir(workspace, analysis_id)
    results = Path(folder, "results")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(STATUS.get(run.get("status"), run.get("status", "")))
        if run.get("based_on", {}).get("name"):
            st.caption(f"Built on **{run['based_on']['name']}**")
    if run.get("question"):
        st.markdown(f"**Question:** {run['question']}")
    if run.get("summary"):
        st.markdown(run["summary"])
    for i, item in enumerate(analysis.shown(folder)):
        path = Path(results, item["file"])
        if not path.is_file():
            continue
        st.subheader(item["title"])
        _draw(path, item, f"agent-analysis-{analysis_id}-{i}")
        if item.get("caption"):
            st.caption(item["caption"])
    st.divider()
    report_buttons(Path(workspace, analysis.ROOT), analysis_id, key=f"agent-analysis-report-{analysis_id}",
                   workflow="AI assistant")
    with st.expander("Steps", icon=":material/list:"):
        _steps(workspace, analysis_id)


def _draw(path: Path, item: dict, key: str) -> None:
    kind = item["kind"]
    try:
        if kind == "plot":
            show_fig(pio.from_json(path.read_text(encoding="utf-8")), path.stem)
        elif kind == "table":
            if path.suffix.lower() in (".parquet", ".pq"):
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path, sep="," if path.suffix.lower() == ".csv" else "\t")
            show_table(df, path.stem)
        elif kind == "image":
            st.image(str(path))
        else:
            st.markdown(path.read_text(encoding="utf-8", errors="replace")[:100_000])
    except (OSError, ValueError, json.JSONDecodeError) as e:
        st.warning(f"{path.name} cannot be shown: {e}")


def _steps(workspace: Path, analysis_id: str) -> None:
    report = report_for(Path(workspace, analysis.ROOT), analysis_id,
                        settings=st.session_state.get("settings"), workflow="AI assistant")
    if not report["steps"]:
        st.caption("No steps yet.")
        return
    rows = [{"Step": s["number"], "Tool": s["tool"], "Version": s["version"] or "",
             "Status": s["status"], "Time": s["duration"],
             "By": "assistant" if s.get("by_assistant") else "workflow", "Why": s.get("note", "")}
            for s in report["steps"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
