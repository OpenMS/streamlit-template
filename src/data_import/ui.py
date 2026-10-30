"""The "Import from a link" section of a workflow's upload page."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Dict

import pandas as pd
import streamlit as st

from . import job
from .net import BlockedURL, make_session
from .sources import resolve

LISTING_KEY = "data-import-listing"
DEFAULT_ONLINE_LIMIT_GB = 50
UNPACK = "Unpack and sort by type"
SKIP = "Skip"


def settings() -> dict:
    return st.session_state.get("settings", {}).get("data_import", {}) or {}


def enabled() -> bool:
    return bool(settings().get("enabled", False))


def _online() -> bool:
    return st.session_state.get("location") == "online"


def _limit_bytes():
    if not _online():
        return None
    limit = settings().get("max_download_gb_online", DEFAULT_ONLINE_LIMIT_GB)
    return int(float(limit) * 1e9) if limit else None


def _format_size(n_bytes) -> str:
    if n_bytes is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1000:
            return f"{int(n_bytes)} B" if unit == "B" else f"{n_bytes:.1f} {unit}"
        n_bytes /= 1000
    return f"{n_bytes:.1f} TB"


def _session():
    return make_session(guard=_online(), allowed_hosts=settings().get("allowed_hosts") or None)


def _lookup(link: str, targets: Dict[str, dict], state_key: str) -> None:
    if not link.strip():
        st.error("Enter a link first.")
        return
    try:
        with st.spinner("Looking up the link..."):
            listing = resolve(_session(), link)
    except (LookupError, BlockedURL) as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"Could not read this link: {e}")
        return
    st.session_state[state_key] = {
        "title": listing.title, "url": listing.url, "notes": listing.notes,
        "items": job.build_items(listing.files, targets),
    }


def _selection(listing: dict, targets: Dict[str, dict], job_dir: Path, settings_: dict) -> None:
    st.markdown(f"**{listing['title']}**")
    for note in listing["notes"]:
        st.caption(note)
    names = {key: target["name"] for key, target in targets.items()}
    by_name = {name: key for key, name in names.items()}
    items = listing["items"]

    def goes_to(item):
        if item["kind"] == "archive":
            return UNPACK
        return names.get(item["target"], SKIP)

    table = pd.DataFrame({
        "Import": [goes_to(i) != SKIP for i in items],
        "File": [i["path"] for i in items],
        "Size": [_format_size(i["size"]) for i in items],
        "Goes to": [goes_to(i) for i in items],
    })
    edited = st.data_editor(
        table, hide_index=True, use_container_width=True, disabled=["File", "Size"],
        key=f"{LISTING_KEY}-editor-{job._item_id(listing['url'])}",
        column_config={
            "Import": st.column_config.CheckboxColumn(width="small"),
            "Goes to": st.column_config.SelectboxColumn(
                options=list(names.values()) + [UNPACK, SKIP], required=True,
                help="The upload this file is added to. Archives that could not be opened "
                     "here are downloaded whole, unpacked, and their files sorted by type."),
        },
    )
    chosen = []
    for item, (_, row) in zip(items, edited.iterrows()):
        if not row["Import"] or row["Goes to"] == SKIP:
            continue
        if row["Goes to"] == UNPACK:
            if item["kind"] != "archive":
                continue
            target = "*"
        else:
            target = by_name[row["Goes to"]]
        chosen.append({**item, "target": target})

    total = sum(int(i["size"] or 0) for i in chosen)
    needed = sum(int(i["size"] or 0) * (2 if i["kind"] == "archive" else 1) for i in chosen)
    limit = _limit_bytes()
    label = f"Import {len(chosen)} file(s), {_format_size(total)}" if chosen else "Import"
    problem = ""
    if limit is not None and total > limit:
        problem = (f"The selection is {_format_size(total)}; this server imports at most "
                   f"{_format_size(limit)} at a time.")
    elif needed > shutil.disk_usage(job_dir.parent).free:
        problem = f"There is not enough free disk space for {_format_size(needed)}."
    if problem:
        st.error(problem)
    if st.button(label, type="primary", use_container_width=True, disabled=not chosen or bool(problem),
                 key=f"{LISTING_KEY}-start"):
        job.start_import(
            job_dir, chosen, targets, guard=_online(),
            allowed_hosts=settings_.get("allowed_hosts") or None, max_bytes=limit,
            parallel=int(settings_.get("parallel_downloads", 4)),
        )
        st.rerun()


@st.fragment(run_every=2)
def _progress(job_dir: Path) -> None:
    status = job.read_status(job_dir)
    if not job.is_running(status):
        st.rerun(scope="app")
    done, total = status.get("bytes_done", 0), status.get("bytes_total", 0)
    active = ", ".join(status.get("active", {}).values())
    text = (f"Importing {min(status.get('done_items', 0) + 1, status.get('total_items', 0))} of "
            f"{status.get('total_items', 0)}: {_format_size(done)} of {_format_size(total)}")
    st.progress(min(done / total, 1.0) if total else 0.0, text=text)
    if active:
        st.caption(f"Downloading {active}")
    if status.get("retry"):
        st.warning(status["retry"])
    if st.button("Cancel import", key=f"{LISTING_KEY}-cancel"):
        job.request_cancel(job_dir)
        st.toast("Stopping the import...")


def _result(status: dict) -> None:
    state = status.get("state")
    imported, errors = status.get("imported", []), status.get("errors", [])
    skipped = status.get("skipped", [])
    message = f"{len(imported)} file(s) imported" + (f", {len(errors)} failed" if errors else "")
    if state == "cancelled":
        st.warning(f"Import cancelled: {message}. Importing the same files again continues "
                   "where it stopped.")
    elif state == "failed":
        st.error(f"Import failed: {message}.")
    else:
        st.success(f"Import finished: {message}.")
    if errors or skipped:
        with st.expander("Details"):
            for error in errors:
                st.markdown(f"- :red[{error}]")
            if skipped:
                st.markdown("Not imported, because no upload here takes their file type:")
                for name in skipped[:200]:
                    st.markdown(f"- {name}")


def link_import_section(workflow_dir, targets: Dict[str, dict]) -> None:
    """Paste a link, choose files, import them into the upload folders in ``targets``.

    ``targets`` maps an upload key to its display ``name``, ``file_types``,
    folder (``dir``) and the names of its example (``fallback``) files.
    """
    if not targets:
        return
    job_dir = Path(workflow_dir, "link-import")
    state_key = f"{LISTING_KEY}-{Path(workflow_dir).name}"
    st.markdown("---")
    st.markdown("**🔗 Import from a link**")
    st.caption(
        "Paste a link to a file, an archive (.tar, .zip, .tar.gz), a public S3 or Swift folder "
        "(e.g. CSC Allas), a OneDrive or SharePoint sharing link, a Zenodo record or a Figshare article. Presigned links to private "
        "objects work too. Files are added to the matching upload above."
    )
    status = job.read_status(job_dir)
    if job.is_running(status):
        _progress(job_dir)
        return
    if job.is_interrupted(status):
        st.warning("The last import stopped before it finished.")
        if st.button("Continue that import", key=f"{LISTING_KEY}-restart"):
            job.restart_import(job_dir)
            time.sleep(0.5)
            st.rerun()

    with st.form(f"{LISTING_KEY}-form", border=False):
        c1, c2 = st.columns([4, 1])
        link = c1.text_input("Link", placeholder="https://a3s.fi/swift/v1/<bucket>/data.tar",
                             label_visibility="collapsed")
        looked_up = c2.form_submit_button("Look up", use_container_width=True)
    if looked_up:
        _lookup(link, targets, state_key)

    listing = st.session_state.get(state_key)
    if listing:
        _selection(listing, targets, job_dir, settings())

    if status.get("state") in ("done", "failed", "cancelled"):
        _result(status)
