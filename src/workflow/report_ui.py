"""Download buttons for the processing report (``processing_report.py``)."""

from pathlib import Path
from typing import Optional

import streamlit as st

from .processing_report import file_stem, report_for, to_markdown, to_pdf
from .progress import progress_path


def _stamp(workflow_dir: Path, run_id: Optional[str]) -> tuple:
    """What the report depends on: its progress.json and run.json, by time."""
    base = Path(workflow_dir, "runs", run_id) if run_id else Path(workflow_dir)
    stamps = []
    for path in (progress_path(base), progress_path(workflow_dir), Path(base, "run.json")):
        try:
            stamps.append(path.stat().st_mtime_ns)
        except OSError:
            stamps.append(None)
    return tuple(stamps)


@st.cache_data(max_entries=32, show_spinner=False)
def _report(workflow_dir: str, run_id: Optional[str], workflow: str, _stamp: tuple) -> dict:
    return report_for(Path(workflow_dir), run_id, settings=st.session_state.get("settings"),
                      workflow=workflow)


@st.cache_data(max_entries=32, show_spinner=False)
def _pdf(workflow_dir: str, run_id: Optional[str], workflow: str, _stamp: tuple) -> Optional[bytes]:
    return to_pdf(_report(workflow_dir, run_id, workflow, _stamp))


def has_report(workflow_dir: Path, run_id: Optional[str] = None) -> bool:
    """True when the run recorded tool calls to report on."""
    report = _report(str(workflow_dir), run_id, "", _stamp(workflow_dir, run_id))
    return bool(report["steps"])


def report_buttons(
    workflow_dir: Path,
    run_id: Optional[str] = None,
    key: str = "processing-report",
    workflow: str = "",
    compact: bool = False,
) -> None:
    """**Processing report** as Markdown and PDF, for a run (or the last run).

    The report lists every input file with the tools that worked on it, their
    versions, and each tool call's parameters that differ from its defaults.
    ``compact`` draws icon buttons for a row of a run list.
    """
    stamp = _stamp(workflow_dir, run_id)
    report = _report(str(workflow_dir), run_id, workflow, stamp)
    if not report["steps"]:
        return
    stem = file_stem(report)
    help_text = ("How each input file was processed: the tools, their versions "
                 "and the parameters that differ from their defaults.")
    md = to_markdown(report)
    pdf = _pdf(str(workflow_dir), run_id, workflow, stamp)
    if compact:
        st.download_button("📄 Markdown", md, file_name=f"{stem}.md", mime="text/markdown",
                           key=f"{key}-md", help=help_text, width="stretch")
        if pdf:
            st.download_button("📄 PDF", pdf, file_name=f"{stem}.pdf", mime="application/pdf",
                               key=f"{key}-pdf", help=help_text, width="stretch")
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**Processing report**", help=help_text)
        st.download_button("Markdown", md, file_name=f"{stem}.md", mime="text/markdown",
                           key=f"{key}-md", icon=":material/description:")
        if pdf:
            st.download_button("PDF", pdf, file_name=f"{stem}.pdf", mime="application/pdf",
                               key=f"{key}-pdf", icon=":material/picture_as_pdf:")
