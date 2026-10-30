"""
Streamlit widgets for multi-run workflows: pick the run(s) a page shows, and
manage the runs (rename, download, delete).

The selection is shared by every page of a workflow: choosing a run on one
results page shows the same run on the others. It lives in a plain
session-state key, not in a widget key, because Streamlit drops the state of
widgets that are not drawn on the current page.
"""

from pathlib import Path
from typing import Optional

import streamlit as st

from src.workflow.RunManager import (
    CANCELLED,
    FAILED,
    FINISHED,
    MAX_NAME_LENGTH,
    RUNNING,
    RunManager,
    format_time,
)

STATUS_LABELS = {
    FINISHED: "✅ Finished",
    RUNNING: "⏳ Running",
    FAILED: "❌ Failed",
    CANCELLED: "⏹️ Cancelled",
    "interrupted": "⚠️ Interrupted",
}


def _slug(runs: RunManager) -> str:
    return runs.workflow_dir.name


def selected_run_key(runs: RunManager) -> str:
    """Session-state key holding the id of the run the workflow's pages show."""
    return f"_runs-{_slug(runs)}-selected"


def get_selected_run(runs: RunManager) -> Optional[str]:
    """
    The run the workflow's pages show: the one picked last in this session if
    it still exists and finished, otherwise the newest finished run.
    """
    run_id = st.session_state.get(selected_run_key(runs))
    run = runs.get(run_id)
    if run is None or run.get("status") != FINISHED:
        run_id = runs.latest(FINISHED)
    return run_id


def set_selected_run(runs: RunManager, run_id: Optional[str]) -> None:
    st.session_state[selected_run_key(runs)] = run_id


def run_label(run: dict) -> str:
    return f"{run.get('name', run['id'])} · {format_time(run.get('created'))}"


def run_status(run: dict, workflow_running: bool) -> str:
    """Status for display: a 'running' run is 'interrupted' once nothing runs."""
    status = run.get("status", FINISHED)
    if status == RUNNING and not workflow_running:
        return "interrupted"
    return status


def select_run(
    runs: RunManager,
    label: str = "Run",
    multiple: bool = False,
    key: str = "",
    help: Optional[str] = None,
):
    """
    Let the user pick which finished run(s) to show.

    Args:
        runs: The workflow's RunManager.
        label: Widget label.
        multiple: Pick several runs (e.g. to compare them) instead of one.
        key: Suffix that keeps several selectors on one page apart.
        help: Tooltip.

    Returns:
        The selected run id (``multiple=False``, None if there are no finished
        runs) or a list of run ids (``multiple=True``).
    """
    finished = runs.list_runs(FINISHED)
    options = [r["id"] for r in finished]
    labels = {r["id"]: run_label(r) for r in finished}
    slug = _slug(runs)

    if multiple:
        shared = f"_runs-{slug}-compared{key}"
        widget = f"runs-{slug}-compare-widget{key}"
        chosen = [r for r in st.session_state.get(shared, []) if r in options]
        if not chosen:
            selected = get_selected_run(runs)
            chosen = [selected] if selected else []
        st.session_state[widget] = chosen

        def store_many():
            st.session_state[shared] = st.session_state[widget]

        st.multiselect(
            label, options, key=widget, format_func=lambda r: labels[r],
            on_change=store_many, help=help, placeholder="Choose runs",
        )
        st.session_state[shared] = st.session_state[widget]
        return list(st.session_state[widget])

    if not options:
        return None
    widget = f"runs-{slug}-select-widget{key}"
    st.session_state[widget] = get_selected_run(runs)

    def store_one():
        set_selected_run(runs, st.session_state[widget])

    st.selectbox(
        label, options, key=widget, format_func=lambda r: labels[r],
        on_change=store_one,
        help=help or "Every run of the workflow is kept. Pick the one to show; "
        "rename, download or delete runs on the Download page.",
    )
    set_selected_run(runs, st.session_state[widget])
    return st.session_state[widget]


def run_manager_section(
    runs: RunManager,
    workflow_running: bool = False,
    exclude: Optional[list[str]] = None,
) -> None:
    """
    One row per run with its name, start time and status, and buttons to show
    it, rename it, download it as a ZIP and delete it.

    Args:
        runs: The workflow's RunManager.
        workflow_running: True while a run executes; its row cannot be deleted.
        exclude: Names left out of the ZIP downloads (e.g. caches).
    """
    all_runs = runs.list_runs()
    if not all_runs:
        st.info("No runs yet. Start the workflow on the **Run** page.")
        return

    slug = _slug(runs)
    selected = get_selected_run(runs)

    for run in all_runs:
        run_id = run["id"]
        status = run_status(run, workflow_running)
        row = st.container(border=True)
        c_name, c_status, c_actions = row.columns([4, 1.6, 2.6], vertical_alignment="center")
        shown = " &nbsp;`shown`" if run_id == selected else ""
        c_name.markdown(
            f"**{run.get('name', run_id)}**{shown}  \n"
            f":gray[Started {format_time(run.get('created'))}]"
        )
        c_status.write(STATUS_LABELS.get(status, status))

        b_show, b_rename, b_download, b_delete = c_actions.columns(4, gap="small")

        if b_show.button(
            "👁️", key=f"runs-{slug}-show-{run_id}", help="Show this run on the results pages",
            disabled=status != FINISHED or run_id == selected, width="stretch",
        ):
            set_selected_run(runs, run_id)
            st.rerun()

        with b_rename.popover("✏️", help="Rename", width="stretch"):
            new_name = st.text_input(
                "Name", value=run.get("name", ""), max_chars=MAX_NAME_LENGTH,
                key=f"runs-{slug}-name-{run_id}",
            )
            if st.button("Save", key=f"runs-{slug}-rename-{run_id}", type="primary"):
                if runs.rename(run_id, new_name):
                    st.rerun()
                st.error("The name can not be empty.")

        prepared = f"_runs-{slug}-zip-{run_id}"
        zip_path = Path(runs.workflow_dir, "downloads", f"{run_id}.zip")
        if st.session_state.get(prepared) and zip_path.exists():
            with open(zip_path, "rb") as f:
                b_download.download_button(
                    "⬇️", data=f, file_name=f"{run.get('name', run_id)}.zip",
                    mime="application/zip", key=f"runs-{slug}-dl-{run_id}",
                    help="Download the ZIP", width="stretch", type="primary",
                )
        elif b_download.button(
            "📦", key=f"runs-{slug}-zip-{run_id}", width="stretch",
            help="Pack results, parameters and logs of this run into a ZIP",
            disabled=status == RUNNING,
        ):
            with st.spinner("Compressing..."):
                runs.zip(run_id, exclude=exclude)
            st.session_state[prepared] = True
            st.rerun()

        with b_delete.popover(
            "🗑️", help="Delete", width="stretch", disabled=status == RUNNING,
        ):
            st.markdown(f"Delete **{run.get('name', run_id)}** and all its files?")
            if st.button("Delete", key=f"runs-{slug}-delete-{run_id}", type="primary"):
                runs.delete(run_id)
                st.session_state.pop(prepared, None)
                st.rerun()


def run_name_key(runs: RunManager) -> str:
    """Session-state key of the name typed for the next run."""
    return f"runs-{_slug(runs)}-next-name"


def run_name_input(runs: RunManager, disabled: bool = False) -> None:
    """Name field for the next run, shown above the Start button."""
    st.text_input(
        "Run name",
        key=run_name_key(runs),
        max_chars=MAX_NAME_LENGTH,
        placeholder=runs.default_name(),
        disabled=disabled,
        help="Every run is kept as its own result set. Earlier runs stay "
        "available; switch between them on the results pages and rename, "
        "download or delete them on the Download page.",
    )
