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

from src.workflow.report_ui import report_buttons

from src.workflow.RunManager import (
    CANCELLED,
    FAILED,
    FINISHED,
    MAX_NAME_LENGTH,
    RUNNING,
    RunImportError,
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
    it still exists and finished, otherwise the newest finished run. A run
    that added files to an experiment stands for the experiment: its first run
    is returned, and ``runs.experiment()`` lists all of them.
    """
    run_id = st.session_state.get(selected_run_key(runs))
    run = runs.get(run_id)
    if run is None or run.get("status") != FINISHED:
        run_id = runs.latest(FINISHED)
    return runs.experiment_root(run_id) if run_id else run_id


def set_selected_run(runs: RunManager, run_id: Optional[str]) -> None:
    st.session_state[selected_run_key(runs)] = run_id


def run_label(run: dict, added: int = 0) -> str:
    """A run's name and start; ``added`` runs that added files to its experiment."""
    label = f"{run.get('name', run['id'])} · {format_time(run.get('created'))}"
    if added:
        label += f" · files added by {added} more {'run' if added == 1 else 'runs'}"
    return label


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
    # A run that added files is shown with the experiment it added them to
    finished = runs.experiments(FINISHED)
    options = [r["id"] for r in finished]
    labels = {r["id"]: run_label(r, len(runs.added_runs(r["id"]))) for r in finished}
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
        "rename, download, delete or import runs on the Download page.",
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
    run_import(runs)
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
        root = runs.experiment_root(run_id)
        adds = (f" · adds files to **{(runs.get(root) or {}).get('name', root)}**"
                if root and root != run_id else "")
        c_name.markdown(
            f"**{run.get('name', run_id)}**{shown}  \n"
            f":gray[Started {format_time(run.get('created'))}]{adds}"
        )
        c_status.write(STATUS_LABELS.get(status, status))

        b_show, b_rename, b_report, b_download, b_delete = c_actions.columns(5, gap="small")

        if b_show.button(
            "👁️", key=f"runs-{slug}-show-{run_id}", help="Show this run on the results pages",
            disabled=status != FINISHED or runs.experiment_root(run_id) == selected, width="stretch",
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

        with b_report.popover("📄", help="Processing report: how each input file was processed",
                              width="stretch", disabled=status == RUNNING):
            report_buttons(runs.workflow_dir, run_id, key=f"runs-{slug}-report-{run_id}", compact=True)

        prepared = f"_runs-{slug}-zip-{run_id}"
        zip_path = Path(runs.workflow_dir, "downloads", f"{run_id}.zip")
        archive = None
        if st.session_state.get(prepared):
            try:
                # Another session may remove or replace a prepared archive.
                # Bind the download to one complete read, not an earlier check.
                archive = zip_path.read_bytes()
            except FileNotFoundError:
                st.session_state[prepared] = False
                row.info("The prepared ZIP is no longer available. Prepare it again to download this run.")
            except OSError as error:
                st.session_state[prepared] = False
                row.error(f"Could not read this run's ZIP: {error} Try preparing it again.")
        if archive is not None:
            b_download.download_button(
                "⬇️", data=archive, file_name=f"{run.get('name', run_id)}.zip",
                mime="application/zip", key=f"runs-{slug}-dl-{run_id}",
                help="Download the ZIP", width="stretch", type="primary",
            )
        elif b_download.button(
            "📦", key=f"runs-{slug}-zip-{run_id}", width="stretch",
            help="Pack results, parameters and logs of this run into a ZIP",
            disabled=status == RUNNING,
        ):
            try:
                with st.spinner("Compressing..."):
                    runs.zip(run_id, exclude=exclude)
            except OSError as error:
                st.session_state[prepared] = False
                row.error(f"Could not prepare this run's ZIP: {error} Refresh the run list or try again.")
            else:
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


def show_import_notice(runs: RunManager) -> None:
    """
    The message left by run_import() for the rerun after an import. Shown
    once: run_import() and the results pages both call this, whichever runs
    first takes it.
    """
    done = st.session_state.pop(f"_runs-{_slug(runs)}-imported", None)
    if not done:
        return
    if isinstance(done, dict):
        name, shown = done.get("name", ""), done.get("shown", False)
    else:
        name, shown = done, True
    if shown:
        st.success(f"Imported **{name}**. It is shown on the results pages.")
    else:
        st.warning(
            f"Imported **{name}**. Its run did not finish, so the results "
            "pages do not show it; it is listed on the Download page."
        )


def run_import(runs: RunManager, expanded: bool = False) -> None:
    """
    Upload a run's ZIP (as the download button of run_manager_section() makes
    it) and add it as a run: its results, parameters and logs, under its name.
    The imported run is shown on the results pages.
    """
    slug = _slug(runs)
    counter = f"_runs-{slug}-import-n"
    n = st.session_state.get(counter, 0)
    show_import_notice(runs)
    with st.expander("📥 Open a run from a ZIP", expanded=expanded):
        st.caption(
            "A run downloaded from this page, here or in another workspace or "
            "installation: results, parameters and logs are added as a new run. "
            f"Up to {st.get_option('server.maxUploadSize')} MB "
            "(`server.maxUploadSize` in `.streamlit/config.toml`)."
        )
        upload = st.file_uploader(
            "Run ZIP", type=["zip"], key=f"runs-{slug}-import-{n}",
            label_visibility="collapsed",
        )
        if upload is not None and st.button(
            "Import run", key=f"runs-{slug}-import-go-{n}", type="primary",
        ):
            try:
                with st.spinner("Unpacking..."):
                    run_id = runs.import_zip(upload)
            except RunImportError as e:
                st.error(f"**{upload.name}** was not imported. {e}")
                return
            run = runs.get(run_id)
            shown = run.get("status") == FINISHED
            if shown:
                set_selected_run(runs, run_id)
            # A fresh uploader, and the message after the rerun
            st.session_state[counter] = n + 1
            st.session_state[f"_runs-{slug}-imported"] = {
                "name": run.get("name", run_id), "shown": shown,
            }
            st.rerun()


def run_name_key(runs: RunManager) -> str:
    """Widget key of the name typed for the next run."""
    return f"runs-{_slug(runs)}-next-name"


def _run_name_draft_key(runs: RunManager) -> str:
    """A non-widget draft survives page changes and belongs to one workspace."""
    return f"_runs-{runs.workflow_dir.resolve()}-next-name-draft"


def pending_run_name(runs: RunManager) -> str:
    """Read the current draft without consuming it before a run exists."""
    widget = run_name_key(runs)
    owner = st.session_state.get(f"_{widget}-owner")
    if owner is None or owner == str(runs.workflow_dir.resolve()):
        return st.session_state.get(widget, st.session_state.get(_run_name_draft_key(runs), ""))
    return st.session_state.get(_run_name_draft_key(runs), "")


def clear_run_name(runs: RunManager) -> None:
    """Clear the consumed draft only after RunManager accepted the new run."""
    st.session_state.pop(_run_name_draft_key(runs), None)
    widget = run_name_key(runs)
    if st.session_state.get(f"_{widget}-owner") in (None, str(runs.workflow_dir.resolve())):
        st.session_state.pop(widget, None)


def run_name_input(runs: RunManager, disabled: bool = False) -> None:
    """Name field for the next run, shown above the Start button."""
    widget, draft = run_name_key(runs), _run_name_draft_key(runs)
    owner_key = f"_{widget}-owner"
    owner = str(runs.workflow_dir.resolve())
    previous_owner = st.session_state.get(owner_key)
    if widget not in st.session_state or previous_owner not in (None, owner):
        st.session_state[widget] = st.session_state.get(draft, "")
    st.session_state[owner_key] = owner

    def keep_draft():
        st.session_state[draft] = st.session_state[widget]

    st.text_input(
        "Run name",
        key=widget,
        max_chars=MAX_NAME_LENGTH,
        placeholder=runs.default_name(),
        disabled=disabled,
        on_change=keep_draft,
        help="Every run is kept as its own result set. Earlier runs stay "
        "available; switch between them on the results pages and rename, "
        "download or delete them on the Download page.",
    )
    keep_draft()
