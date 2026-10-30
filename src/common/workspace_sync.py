"""The Workspace Sync page (see ``src/sync``).

Online, it issues sync tokens for the current workspace. Offline (the
Electron app), it links the local workspace with such a token and lists
every input and every result with its state on both sides; the user pushes
or pulls the items they select.

A transfer of several GB outlasts any script run, so it runs in a background
thread registered per workspace, and a fragment polls it while it runs. The
thread survives page switches; leaving the page and coming back shows the
running transfer again.

The sidebar of every page shows the link's state in short (pending items,
a running transfer) and offers a one-click Sync: push everything new or
changed, then pull every new or updated result. It never waits on the
network; states older than a minute are refreshed in a background thread.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.sync import client, server, tokens


@dataclass
class _Job:
    action: str
    keys: list[str]
    cancel: threading.Event = field(default_factory=threading.Event)
    done: int = 0
    total: int = 0
    current: str = ""
    notice: str = ""
    report: client.SyncReport | None = None
    error: str = ""
    finished: bool = False
    ended: float = 0.0


_JOBS: dict[str, _Job] = {}
_JOBS_LOCK = threading.Lock()
_VERBS = {"push": ("Pushing", "Pushed"), "pull": ("Pulling", "Pulled"),
          "sync": ("Syncing", "Synced")}

# Item states per workspace, shared by the page and the sidebar of every
# session; the threads that refresh them have no session state.
_STATUS: dict[str, dict] = {}
_REFRESHING: set[str] = set()
_STATUS_LOCK = threading.Lock()
_STATUS_MAX_AGE = 60

_PUSH_PENDING = {client.NOT_ON_SERVER, client.CHANGED_LOCALLY}
_PULL_PENDING = {client.NOT_DOWNLOADED, client.CHANGED_ON_SERVER}


def sync_enabled() -> bool:
    settings = st.session_state.settings
    return bool(server.sync_settings(settings)["enabled"] and settings.get("enable_workspaces"))


def _settings() -> dict:
    return server.sync_settings(st.session_state.settings)


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _client(link: dict, **kw) -> client.SyncClient:
    return client.SyncClient(link["url"], link["token"],
                             chunk_size=int(_settings()["chunk_mb"] * 1024 * 1024), **kw)


def _compute_status(workspace: Path, c: client.SyncClient) -> dict:
    started = time.time()
    try:
        status = {"inputs": c.input_items(workspace), "results": c.result_items(workspace),
                  "error": ""}
    except client.SyncError as exc:
        status = {"inputs": [], "results": [], "error": str(exc)}
    status.update(workspace=str(workspace), at=time.time())
    job = _JOBS.get(str(workspace))
    with _STATUS_LOCK:
        # States compared while a transfer ran are stale by the time it ends.
        if job is None or (job.finished and job.ended < started):
            _STATUS[str(workspace)] = status
    return status


def _invalidate(workspace: Path) -> None:
    st.session_state.pop("sync-status", None)
    with _STATUS_LOCK:
        _STATUS.pop(str(workspace), None)


def _refresh_in_background(workspace: Path, link: dict) -> None:
    """Refresh the states without blocking the page that asked."""
    c = _client(link, give_up_after=10, timeout=30)
    with _STATUS_LOCK:
        if str(workspace) in _REFRESHING:
            return
        _REFRESHING.add(str(workspace))

    def run():
        try:
            _compute_status(workspace, c)
        finally:
            with _STATUS_LOCK:
                _REFRESHING.discard(str(workspace))

    threading.Thread(target=run, daemon=True, name="workspace-sync-status").start()


def _pending(items: list[client.Item], states: set[str]) -> list[client.Item]:
    return [i for i in items if i.state in states or i.state.startswith("Paused")]


def _start(workspace: Path, action: str, keys: list[str], link: dict) -> None:
    job = _Job(action, keys)
    # Built here: the thread below has no session state to read settings from.
    c = _client(link)
    with _JOBS_LOCK:
        running = _JOBS.get(str(workspace))
        if running and not running.finished:
            return
        _JOBS[str(workspace)] = job

    def progress(done, total, rel):
        job.done, job.total, job.current = done, total, rel

    def notice(msg):
        job.notice = msg

    def run():
        try:
            c.notice = notice
            if action == "sync":
                # Inputs first: a result pulled now may come from them later.
                up = c.push(workspace, None, progress=progress, cancel=job.cancel)
                down = c.pull(workspace, None, progress=progress, cancel=job.cancel)
                job.report = client.SyncReport(up.transferred + down.transferred,
                                               up.unchanged + down.unchanged,
                                               up.bytes + down.bytes)
            else:
                fn = c.push if action == "push" else c.pull
                job.report = fn(workspace, keys, progress=progress, cancel=job.cancel)
        except client.Cancelled:
            job.error = "Cancelled. Pushing or pulling the same items again continues where it stopped."
        except Exception as exc:  # shown on the page, never lost in a thread
            job.error = f"{exc}. Pushing or pulling again continues where it stopped."
        finally:
            job.ended = time.time()
            job.finished = True
            with _STATUS_LOCK:
                _STATUS.pop(str(workspace), None)

    threading.Thread(target=run, daemon=True, name=f"workspace-sync-{action}").start()


@st.fragment(run_every=1.0)
def _job_progress(workspace: Path) -> None:
    """Poll a running transfer; rerun the whole page once it has finished."""
    job = _JOBS.get(str(workspace))
    if job is None or job.finished:
        st.session_state.pop("sync-status", None)
        st.rerun()
        return
    verb = _VERBS[job.action][0]
    what = f"{len(job.keys)} item(s)" if job.keys else "workspace"
    if job.total:
        st.progress(min(job.done / job.total, 1.0),
                    text=f"{verb} {what}: {_size(job.done)} of {_size(job.total)}")
    else:
        st.progress(0.0, text=f"{verb} {what}: comparing files…")
    if job.current:
        st.caption(job.current)
    if job.notice:
        st.warning(job.notice, icon="📡")
    if st.button("Cancel transfer", key="sync-cancel"):
        job.cancel.set()


def _job_result(job: _Job) -> None:
    if job.error:
        st.error(job.error)
    elif job.report is not None:
        r = job.report
        if r.transferred:
            st.success(f"{_VERBS[job.action][1]} {len(r.transferred)} file(s), {_size(r.bytes)}"
                       + (f"; {r.unchanged} already up to date." if r.unchanged else "."))
        elif job.action == "sync":
            st.info("Everything was already up to date.")
        else:
            st.info("Everything selected was already up to date.")


def _load_status(workspace: Path, link: dict) -> dict:
    status = st.session_state.get("sync-status")
    if status and status["workspace"] == str(workspace):
        return status
    c = _client(link, give_up_after=10, timeout=30)
    with st.spinner("Comparing this workspace with the online workspace…"):
        status = _compute_status(workspace, c)
    # The page keeps its own copy: a refresh from the sidebar must not
    # reorder the rows under a selection.
    st.session_state["sync-status"] = status
    return status


def _item_table(items: list[client.Item], key: str) -> list[client.Item]:
    """Show items with a selection column; return the selected ones."""
    df = pd.DataFrame({
        "Name": [i.name for i in items],
        "Location": [str(Path(i.key).parent) if i.kind != "parameters" else "params.json files"
                     for i in items],
        "Files": [len(i.files) for i in items],
        "Size": [_size(i.size) for i in items],
        "State": [i.state for i in items],
    })
    event = st.dataframe(df, hide_index=True, width="stretch", key=key,
                         on_select="rerun", selection_mode="multi-row")
    return [items[r] for r in event.selection.rows]


def _transfer_buttons(workspace, link, items, selected, action, busy, pending_states):
    verb = "Push" if action == "push" else "Pull"
    pending = _pending(items, pending_states)
    col1, col2, _ = st.columns([1, 1, 2])
    if col1.button(f"{verb} selected ({len(selected)})", disabled=busy or not selected,
                   key=f"sync-{action}-selected", width="stretch", type="primary"):
        _start(workspace, action, [i.key for i in selected], link)
        st.rerun()
    label = "new and changed" if action == "push" else "new and updated"
    if col2.button(f"{verb} all {label} ({len(pending)})", disabled=busy or not pending,
                   key=f"sync-{action}-pending", width="stretch"):
        _start(workspace, action, [i.key for i in pending], link)
        st.rerun()


def _link_form(workspace: Path) -> None:
    st.markdown(
        "Link this workspace to an online workspace to send it input files "
        "too large for the browser (raw files, Bruker `.d` folders) and to "
        "fetch the results back. In the online app, open **Workspace Sync** "
        "and create a sync token."
    )
    with st.form("sync-link"):
        url = st.text_input("Server URL", value=_settings()["public_url"],
                            placeholder="https://example.org/sync")
        token = st.text_input("Sync token", type="password")
        if st.form_submit_button("Link workspace", type="primary"):
            if not (url and token):
                st.error("Enter both the server URL and the sync token.")
                return
            try:
                name = client.SyncClient(url, token, give_up_after=0, timeout=20).check()
            except client.SyncError as exc:
                st.error(str(exc))
                return
            client.write_link(workspace, {"url": url.strip(), "token": token.strip(),
                                          "workspace": name, "uploads": {}})
            _invalidate(workspace)
            st.rerun()


def _offline_page(workspace: Path) -> None:
    link = client.read_link(workspace)
    if not link:
        _link_form(workspace)
        return

    job = _JOBS.get(str(workspace))
    busy = job is not None and not job.finished
    head, refresh, unlink = st.columns([4, 1, 1])
    head.markdown(f"This workspace is linked to online workspace `{link.get('workspace', '?')}` "
                  f"at {link['url']}.")
    if refresh.button("🔄 Refresh", disabled=busy, width="stretch"):
        _invalidate(workspace)
        st.rerun()
    if unlink.button("Unlink", disabled=busy, width="stretch"):
        client.unlink_workspace(workspace)
        _invalidate(workspace)
        st.rerun()

    if busy:
        _job_progress(workspace)
    elif job is not None:
        _job_result(job)

    status = _load_status(workspace, link)
    if status["error"]:
        st.error(f"The online workspace cannot be reached: {status['error']}")
        return
    st.caption(f"States as of {datetime.fromtimestamp(status['at']).strftime('%H:%M:%S')}. "
               "Large files go up in verified chunks; an interrupted transfer continues "
               "where it stopped, also after closing the app.")

    # A segmented control, not st.tabs: selecting a row reruns the page, and
    # the chosen view must survive that rerun.
    view = st.segmented_control("View", ["⬆️ Inputs", "⬇️ Results"], default="⬆️ Inputs",
                                key="sync-view", label_visibility="collapsed")
    if view != "⬇️ Results":
        if not status["inputs"]:
            st.info("This workspace has no input files yet. Add them on the workflow's upload page.")
        else:
            selected = _item_table(status["inputs"], "sync-inputs-table")
            _transfer_buttons(workspace, link, status["inputs"], selected, "push", busy,
                              _PUSH_PENDING)
    else:
        if not status["results"]:
            st.info("The online workspace has no results yet. Run the workflow there, then refresh.")
        else:
            selected = _item_table(status["results"], "sync-results-table")
            _transfer_buttons(workspace, link, status["results"], selected, "pull", busy,
                              _PULL_PENDING)


def _public_url(cfg: dict) -> str:
    if cfg["public_url"]:
        return cfg["public_url"].rstrip("/")
    try:
        app_url = st.context.url
    except Exception:
        app_url = ""
    origin = "/".join(app_url.split("/")[:3]) if app_url else ""
    return f"{origin}/sync"


def _online_page(workspace: Path) -> None:
    cfg = _settings()
    root = workspace.parent
    st.markdown(
        "Use the desktop app to send large input files (raw files, Bruker `.d` "
        "folders) straight into this workspace and fetch results back. Create "
        "a sync token here, then paste the server URL and the token on the "
        "desktop app's **Workspace Sync** page."
    )
    issued = st.session_state.get("sync-issued")
    if issued and issued["workspace"] == workspace.name:
        col1, col2 = st.columns(2)
        with col1:
            st.text("Server URL")
            st.code(issued["url"], language=None)
        with col2:
            st.text("Sync token")
            st.code(issued["token"], language=None)
        st.caption(
            f"Valid until {datetime.fromtimestamp(issued['expires']).strftime('%Y-%m-%d %H:%M')}. "
            "Anyone with this token can add files to this workspace and download its results."
        )
    col1, col2, _ = st.columns([1, 1, 2])
    if col1.button("Create sync token", type="primary", width="stretch"):
        token, expires = tokens.issue(root, workspace.name, cfg["token_ttl_hours"])
        st.session_state["sync-issued"] = {
            "workspace": workspace.name, "token": token,
            "expires": expires, "url": _public_url(cfg),
        }
        st.rerun()
    active = tokens.active_count(root, workspace.name)
    if col2.button(f"Revoke all tokens ({active})", disabled=not active, width="stretch"):
        tokens.revoke(root, workspace.name)
        st.session_state.pop("sync-issued", None)
        st.rerun()


def render_sync_page() -> None:
    st.title("🔄 Workspace Sync")
    if not sync_enabled():
        st.info("Workspace sync is not enabled for this app.")
        return
    workspace = Path(st.session_state.workspace)
    if st.session_state.location == "online":
        _online_page(workspace)
    else:
        _offline_page(workspace)


_PAGE = "content/workspace_sync.py"


@st.fragment(run_every=2.0)
def _sidebar_live(workspace: Path) -> None:
    """Poll a transfer or a state refresh; rerun the app once it is over."""
    job = _JOBS.get(str(workspace))
    if job is not None and not job.finished:
        verb = _VERBS[job.action][0]
        if job.total:
            st.progress(min(job.done / job.total, 1.0),
                        text=f"{verb}: {_size(job.done)} of {_size(job.total)}")
        else:
            st.progress(0.0, text=f"{verb}: comparing files…")
        if job.notice:
            st.caption(f"📡 {job.notice}")
        elif job.current:
            st.caption(Path(job.current).name)
        if st.button("Cancel", key="sync-sidebar-cancel", width="stretch"):
            job.cancel.set()
        return
    with _STATUS_LOCK:
        waiting = str(workspace) in _REFRESHING
    if waiting:
        st.caption("Checking the online workspace…")
        return
    st.rerun()


def _sidebar_summary(workspace: Path, link: dict, status: dict | None) -> None:
    job = _JOBS.get(str(workspace))
    if status is None:
        st.caption("Checking the online workspace…")
    elif status["error"]:
        st.caption("⚠️ The online workspace cannot be reached.")
    else:
        up = len(_pending(status["inputs"], _PUSH_PENDING))
        down = len(_pending(status["results"], _PULL_PENDING))
        if up or down:
            st.markdown(f"⬆️ {up} to push · ⬇️ {down} to pull")
        else:
            st.markdown("✅ Up to date")
        st.caption(f"Checked {datetime.fromtimestamp(status['at']).strftime('%H:%M')}")
    if job is not None and job.error:
        st.caption(f"⚠️ Last transfer stopped: {job.error.split('. ')[0]}.")
    elif job is not None and job.report is not None and job.report.transferred:
        st.caption(f"Last: {_VERBS[job.action][1].lower()} {len(job.report.transferred)} "
                   f"file(s), {_size(job.report.bytes)}")
    if st.button("🔄 Sync", key="sync-sidebar-sync", type="primary", width="stretch",
                 help="Push every new or changed input, then pull every new or updated result.",
                 disabled=status is not None and bool(status["error"])):
        _start(workspace, "sync", [], link)
        st.rerun()


@st.fragment(run_every=2.0)
def _sidebar_incoming(workspace: Path) -> None:
    """Online: follow the uploads the desktop app is sending; rerun when done."""
    active = [u for u in server.incoming(workspace.parent, workspace.name) if u["active"]]
    if not active:
        st.rerun()
        return
    done = sum(u["offset"] for u in active)
    total = sum(u["length"] for u in active)
    st.progress(min(done / total, 1.0) if total else 0.0,
                text=f"Receiving: {_size(done)} of {_size(total)}")
    st.caption(", ".join(Path(u["path"]).name for u in active))


def _online_sidebar(workspace: Path) -> None:
    uploads = server.incoming(workspace.parent, workspace.name)
    linked = tokens.active_count(workspace.parent, workspace.name)
    with st.expander("🔄 **Workspace Sync**", expanded=bool(linked or uploads)):
        if any(u["active"] for u in uploads):
            _sidebar_incoming(workspace)
        elif linked:
            st.caption(f"🔗 Desktop app linked ({linked} token{'s' if linked > 1 else ''})")
        else:
            st.caption("Send large files from the desktop app and fetch the results there.")
        paused = sum(not u["active"] for u in uploads)
        if paused:
            st.caption(f"⏸️ {paused} upload(s) paused until the desktop app continues them.")
        st.page_link(_PAGE, label="Open sync" if linked or uploads else "Link desktop app",
                     icon="🔄" if linked or uploads else "🔗")


def render_sync_sidebar() -> None:
    """The sidebar's sync status and its entry to the Workspace Sync page."""
    if not sync_enabled():
        return
    workspace = Path(st.session_state.workspace)
    if st.session_state.location == "online":
        _online_sidebar(workspace)
        return
    link = client.read_link(workspace)
    with st.expander("🔄 **Workspace Sync**", expanded=True):
        if not link:
            st.caption("Not linked to an online workspace.")
            st.page_link(_PAGE, label="Link workspace", icon="🔗")
            return
        # Online workspace names are UUIDs; the start tells them apart.
        st.caption(f"🔗 Linked to `{link.get('workspace', '?')[:8]}`")
        job = _JOBS.get(str(workspace))
        if job is not None and not job.finished:
            _sidebar_live(workspace)
        else:
            with _STATUS_LOCK:
                status = _STATUS.get(str(workspace))
            stale = status is None or time.time() - status["at"] > _STATUS_MAX_AGE
            if stale:
                _refresh_in_background(workspace, link)
            _sidebar_summary(workspace, link, status)
            if stale:
                # Shows the fresh states as soon as they are in.
                _sidebar_live(workspace)
        st.page_link(_PAGE, label="Open sync", icon="📋")
