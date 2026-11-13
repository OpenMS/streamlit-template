"""Download buttons for the processing report (``processing_report.py``)."""

from pathlib import Path
from typing import Optional

import streamlit as st

from .methods_text import methods_text
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
def _report(workflow_dir: str, run_id: Optional[str], workflow: str, stamp: tuple) -> dict:
    return report_for(Path(workflow_dir), run_id, settings=st.session_state.get("settings"),
                      workflow=workflow)


@st.cache_data(max_entries=32, show_spinner=False)
def _pdf(workflow_dir: str, run_id: Optional[str], workflow: str, stamp: tuple) -> Optional[bytes]:
    try:
        return to_pdf(_report(workflow_dir, run_id, workflow, stamp))
    except Exception:  # a layout error in reportlab leaves the Markdown report
        return None


_METHODS_HELP = ("A methods section for a publication, written from this run: the tools, "
                 "their versions and the settings that differ from their defaults, with "
                 "references. Copy it and edit it to fit.")


def methods_box(report: dict, stem: str, key: str, compact: bool = False) -> None:
    """**Methods**: the run's methods section (``methods_text``) to copy or download.

    ``compact`` (a row of a run list, already in a popover) draws only the download.
    """
    text = methods_text(report, st.session_state.get("settings"))
    if not text:
        return
    if compact:
        st.download_button("📝 Methods", text, file_name=f"{stem}-methods.txt", mime="text/plain",
                           key=f"{key}-methods-txt", help=_METHODS_HELP, width="stretch")
        return
    with st.popover("Methods", icon=":material/article:", help=_METHODS_HELP):
        st.caption("A draft to edit: it says what was run, not why. The copy button is at "
                   "the top right of the text.")
        st.code(text, language=None, wrap_lines=True)
        st.download_button("Download", text, file_name=f"{stem}-methods.txt", mime="text/plain",
                           key=f"{key}-methods-txt", icon=":material/download:")


def run_methods(workflow_dir: Path, run_id: Optional[str] = None, workflow: str = "") -> tuple:
    """The methods text of a run (or the last run) and its file stem; ("", "") when none."""
    try:
        report = _report(str(workflow_dir), run_id, workflow, _stamp(workflow_dir, run_id))
        text = methods_text(report, st.session_state.get("settings")) if report["steps"] else ""
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "", ""
    return (text, file_stem(report)) if text else ("", "")


def methods_section(workflow_dir: Path, key: str, run_id: Optional[str] = None,
                    workflow: str = "") -> None:
    """**Methods** of the last run in an expander, to copy or download."""
    text, stem = run_methods(workflow_dir, run_id, workflow)
    with st.expander("**Methods**"):
        if not text:
            st.caption("A methods section for a publication, written from the run: the tools, "
                       "their versions and the settings that differ from their defaults, with "
                       "references. It appears here once a tool of a run has finished.")
            return
        st.caption("Written from the last run, a draft to edit: it says what was run, not why. "
                   "The copy button is at the top right of the text.")
        st.code(text, language=None, wrap_lines=True)
        st.download_button("Download", text, file_name=f"{stem}-methods.txt", mime="text/plain",
                           key=f"{key}-methods-txt", icon=":material/download:")


def run_report(workflow_dir: Path, run_id: Optional[str] = None) -> dict:
    """The processing report of a run (``report_for``), cached until the run changes."""
    return _report(str(workflow_dir), run_id, "", _stamp(workflow_dir, run_id))


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
    methods: bool = True,
) -> None:
    """**Processing report** as Markdown and PDF, for a run (or the last run).

    The report lists every input file with the tools that worked on it, their
    versions, and each tool call's parameters that differ from its defaults.
    ``compact`` draws icon buttons for a row of a run list. ``methods=False``
    leaves out Methods, for a page that shows it in a ``methods_section``.
    """
    stamp = _stamp(workflow_dir, run_id)
    try:
        report = _report(str(workflow_dir), run_id, workflow, stamp)
        md = to_markdown(report) if report["steps"] else ""
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return  # a run whose progress.json is damaged (an imported run) has no report
    if not md:
        return
    stem = file_stem(report)
    help_text = ("How each input file was processed: the tools, their versions "
                 "and the parameters that differ from their defaults.")
    pdf = _pdf(str(workflow_dir), run_id, workflow, stamp)
    if compact:
        st.download_button("📄 Markdown", md, file_name=f"{stem}.md", mime="text/markdown",
                           key=f"{key}-md", help=help_text, width="stretch")
        if pdf:
            st.download_button("📄 PDF", pdf, file_name=f"{stem}.pdf", mime="application/pdf",
                               key=f"{key}-pdf", help=help_text, width="stretch")
        methods_box(report, stem, key, compact=True)
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**Processing report**", help=help_text)
        st.download_button("Markdown", md, file_name=f"{stem}.md", mime="text/markdown",
                           key=f"{key}-md", icon=":material/description:")
        if pdf:
            st.download_button("PDF", pdf, file_name=f"{stem}.pdf", mime="application/pdf",
                               key=f"{key}-pdf", icon=":material/picture_as_pdf:")
        if methods:
            methods_box(report, stem, key)
