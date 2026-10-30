"""The Workspace Sync page (see ``src/sync``).

Online, it issues sync tokens for the current workspace. Offline (the
Electron app), it links the local workspace with such a token and lists
every input and every result with its state on both sides; the user pushes
or pulls the items they select.

A transfer of several GB outlasts any script run, so it runs in a background
thread registered per workspace, and a fragment polls it while it runs. The
thread survives page switches; leaving the page and coming back shows the
running transfer again.

Inputs (the files a user uploads) and results are grouped per workflow,
and the user chooses per workflow whether its inputs go up and its results
come down. "Keep in sync" runs a background loop that transfers whatever is
new in those directions. Each workflow the server allows can also be run
online from here ("Run on cloud": upload its inputs, then queue it with this
workspace's parameters), followed live and stopped.

The sidebar of every page shows the link's state in short (pending items,
a running transfer) and offers a one-click Sync in the chosen directions.
It never waits on the network; states older than a minute are refreshed in
a background thread.
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
    auto: bool = False             # started by Keep in sync
    workflow: str = ""             # "run": the workflow queued online


_JOBS: dict[str, _Job] = {}
_JOBS_LOCK = threading.Lock()
_VERBS = {"push": ("Pushing", "Pushed"), "pull": ("Pulling", "Pulled"),
          "sync": ("Syncing", "Synced"), "run": ("Uploading inputs for", "Started")}

_RUN_ACTIVE = ("queued", "started", "deferred")

# Item states per workspace, shared by the page and the sidebar of every
# session; the threads that refresh them have no session state.
_STATUS: dict[str, dict] = {}
_REFRESHING: set[str] = set()
_STATUS_LOCK = threading.Lock()
_STATUS_MAX_AGE = 60

_PUSH_PENDING = {client.NOT_ON_SERVER, client.CHANGED_LOCALLY}
_PULL_PENDING = {client.NOT_DOWNLOADED, client.CHANGED_ON_SERVER}

# Keep in sync: one loop per workspace, ended by clearing the box or unlinking.
_WATCHERS: dict[str, threading.Thread] = {}
_WATCH_INTERVAL = 30


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
    try:
        status["runs"] = c.runs() if not status["error"] else {}
    except client.SyncError:
        status["runs"] = {}         # a server without run control
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


def _chosen(status: dict, prefs: dict, pending_only: bool = False
            ) -> tuple[list[client.Item], list[client.Item]]:
    """The inputs and results in the directions chosen for their workflow."""
    up = [i for i in status["inputs"] if client.direction_on(prefs, i.workflow, "push")]
    down = [i for i in status["results"] if client.direction_on(prefs, i.workflow, "pull")]
    if pending_only:
        up, down = _pending(up, _PUSH_PENDING), _pending(down, _PULL_PENDING)
    return up, down


def _start(workspace: Path, action: str, keys: list[str] | None, link: dict) -> None:
    # Built here: the thread below has no session state to read settings from.
    _launch(workspace, action, keys, _client(link))


def _launch(workspace: Path, action: str, keys: list[str] | None, c: client.SyncClient,
            auto: bool = False, workflow: str = "") -> bool:
    """Run a transfer in a background thread; False if one is running already.

    ``sync`` pushes, then pulls; its keys hold input and result keys together
    (push and pull each ignore the other's). ``run`` pushes the keys, then
    queues ``workflow`` online.
    """
    job = _Job(action, keys or [], auto=auto, workflow=workflow)
    with _JOBS_LOCK:
        running = _JOBS.get(str(workspace))
        if running and not running.finished:
            return False
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
                up = c.push(workspace, keys, progress=progress, cancel=job.cancel)
                down = c.pull(workspace, keys, progress=progress, cancel=job.cancel)
                job.report = client.SyncReport(up.transferred + down.transferred,
                                               up.unchanged + down.unchanged,
                                               up.bytes + down.bytes)
            elif action == "run":
                job.report = c.push(workspace, keys, progress=progress, cancel=job.cancel)
                c.start_run(workspace, workflow)
            else:
                fn = c.push if action == "push" else c.pull
                job.report = fn(workspace, keys, progress=progress, cancel=job.cancel)
        except client.Cancelled:
            job.error = "Cancelled. Pushing or pulling the same items again continues where it stopped."
        except Exception as exc:  # shown on the page, never lost in a thread
            if action == "run" and job.report is not None:
                job.error = f"The cloud run of {workflow} was not started: {exc}"
            else:
                job.error = f"{exc}. Pushing or pulling again continues where it stopped."
        finally:
            job.ended = time.time()
            job.finished = True
            with _STATUS_LOCK:
                _STATUS.pop(str(workspace), None)

    threading.Thread(target=run, daemon=True, name=f"workspace-sync-{action}").start()
    return True


def _watch(workspace: Path, chunk_size: int) -> None:
    """Keep in sync: every half minute, transfer what is new in the chosen
    directions. Ends when the box is cleared or the workspace unlinked."""
    while True:
        prefs, link = client.read_prefs(workspace), client.read_link(workspace)
        if not (prefs["keep_in_sync"] and link):
            return
        job = _JOBS.get(str(workspace))
        if job is None or job.finished:
            check = client.SyncClient(link["url"], link["token"], chunk_size=chunk_size,
                                      give_up_after=10, timeout=30)
            status = _compute_status(workspace, check)
            if not status["error"]:
                up, down = _chosen(status, prefs, pending_only=True)
                if up or down:
                    c = client.SyncClient(link["url"], link["token"], chunk_size=chunk_size)
                    _launch(workspace, "sync", [i.key for i in up + down], c, auto=True)
        time.sleep(_WATCH_INTERVAL)


def _ensure_watcher(workspace: Path) -> None:
    if not client.read_prefs(workspace)["keep_in_sync"]:
        return
    chunk_size = int(_settings()["chunk_mb"] * 1024 * 1024)
    with _JOBS_LOCK:
        running = _WATCHERS.get(str(workspace))
        if running is not None and running.is_alive():
            return
        thread = threading.Thread(target=_watch, args=(workspace, chunk_size), daemon=True,
                                  name="workspace-sync-keep")
        _WATCHERS[str(workspace)] = thread
    thread.start()


@st.fragment(run_every=1.0)
def _job_progress(workspace: Path) -> None:
    """Poll a running transfer; rerun the whole page once it has finished."""
    job = _JOBS.get(str(workspace))
    if job is None or job.finished:
        st.session_state.pop("sync-status", None)
        st.rerun()
        return
    verb = _VERBS[job.action][0]
    what = {"sync": "workspace", "run": job.workflow}.get(job.action, f"{len(job.keys)} item(s)")
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
    elif job.action == "run" and job.report is not None:
        st.success(f"Started a cloud run of {job.workflow}"
                   + (f" after uploading {len(job.report.transferred)} file(s), "
                      f"{_size(job.report.bytes)}." if job.report.transferred else "."))
    elif job.report is not None:
        r = job.report
        if r.transferred:
            st.success(f"{_VERBS[job.action][1]} {len(r.transferred)} file(s), {_size(r.bytes)}"
                       + (f"; {r.unchanged} already up to date." if r.unchanged else "."))
        elif job.action == "sync":
            st.info("Everything chosen was already up to date.")
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
        "Location": [str(Path(i.key).parent) if i.kind != "parameters" else "params.json"
                     for i in items],
        "Files": [len(i.files) for i in items],
        "Size": [_size(i.size) for i in items],
        "State": [i.state for i in items],
    })
    event = st.dataframe(df, hide_index=True, width="stretch", key=key,
                         on_select="rerun", selection_mode="multi-row")
    return [items[r] for r in event.selection.rows]


def _transfer_buttons(workspace, link, items, selected, action, busy, pending_states, suffix):
    verb = "Push" if action == "push" else "Pull"
    pending = _pending(items, pending_states)
    col1, col2, _ = st.columns([1, 1, 2])
    if col1.button(f"{verb} selected ({len(selected)})", disabled=busy or not selected,
                   key=f"sync-{action}-selected-{suffix}", width="stretch"):
        _start(workspace, action, [i.key for i in selected], link)
        st.rerun()
    label = "new and changed" if action == "push" else "new and updated"
    if col2.button(f"{verb} all {label} ({len(pending)})", disabled=busy or not pending,
                   key=f"sync-{action}-pending-{suffix}", width="stretch"):
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


def _set_pref(workspace: Path, workflow: str | None, field_: str, key: str) -> None:
    """Widget callback: store a checkbox in the workspace's sync choices."""
    prefs = client.read_prefs(workspace)
    if workflow is None:
        prefs[field_] = bool(st.session_state[key])
    else:
        prefs["workflows"].setdefault(workflow, {})[field_] = bool(st.session_state[key])
    client.write_prefs(workspace, prefs)
    if prefs["keep_in_sync"]:
        _ensure_watcher(workspace)


def _summary(items: list[client.Item], pending_states: set[str], verb: str) -> str:
    if not items:
        return "none yet"
    waiting = len(_pending(items, pending_states))
    return (f"{len(items)} item(s), {_size(sum(i.size for i in items))}"
            + (f", {waiting} to {verb}" if waiting else ", all in sync"))


def _run_label(run: dict) -> str:
    state = run["status"]
    if state == "queued":
        pos = run.get("queue_position")
        return f"⏳ Queued{f' (position {pos})' if pos else ''}"
    if state == "started":
        step = f": {run['current_step']}" if run.get("current_step") else ""
        return f"⚙️ Running{step}"
    return {"idle": "Not run yet", "finished": "✅ Finished", "canceled": "⏹️ Cancelled",
            "failed": "❌ Failed" + (f": {run['error']}" if run.get("error") else "")
            }.get(state, state)


def _run_view(workspace: Path, link: dict, workflow: str, run: dict, inputs, busy) -> None:
    """One workflow's run in the online workspace, with Run and Stop."""
    active = run["status"] in _RUN_ACTIVE
    col1, col2, col3 = st.columns([3, 1, 1])
    col1.markdown(f"☁️ **Cloud run:** {_run_label(run)}")
    if run["status"] == "started" and run.get("progress"):
        col1.progress(min(float(run["progress"]), 1.0))
    suffix = f"{workspace.name}-{workflow}"
    if col2.button("▶️ Run on cloud", key=f"sync-run-{suffix}", width="stretch",
                   disabled=active or busy,
                   help="Upload this workflow's inputs, then run it in the online workspace "
                        "with the parameters set here."):
        _start_run(workspace, link, workflow, inputs)
        st.rerun()
    if col3.button("⏹️ Stop", key=f"sync-stop-{suffix}", width="stretch", disabled=not active):
        try:
            _client(link, give_up_after=10, timeout=30).stop_run(workflow)
        except client.SyncError as exc:
            st.error(str(exc))
        _invalidate(workspace)
        st.rerun(scope="app")
    if run.get("log"):
        with st.expander("Cloud log"):
            st.code("\n".join(run["log"]), language=None)


def _start_run(workspace: Path, link: dict, workflow: str, inputs) -> None:
    _launch(workspace, "run", [i.key for i in inputs], _client(link), workflow=workflow)


@st.fragment(run_every=3.0)
def _run_live(workspace: Path, link: dict, workflow: str, inputs, busy) -> None:
    """Follow an active run; rerun the page once it has ended."""
    try:
        run = _client(link, give_up_after=5, timeout=15).runs()[workflow]
    except (client.SyncError, KeyError):
        st.caption("☁️ Cloud run: state unknown, retrying…")
        return
    if run["status"] not in _RUN_ACTIVE:
        _invalidate(workspace)
        st.rerun(scope="app")
        return
    _run_view(workspace, link, workflow, run, inputs, busy)


def _workflow_box(workspace, link, prefs, workflow, inputs, results, busy, run=None) -> None:
    label = f"`{workflow}`" if workflow else "Workspace files (outside any workflow)"
    suffix = f"{workspace.name}-{workflow or '_'}"
    with st.container(border=True):
        st.markdown(f"**{label}**")
        col1, col2 = st.columns(2)
        key = f"sync-push-{suffix}"
        col1.checkbox(f"⬆️ Upload inputs ({_summary(inputs, _PUSH_PENDING, 'push')})",
                      value=client.direction_on(prefs, workflow, "push"), key=key,
                      on_change=_set_pref, args=(workspace, workflow, "push", key))
        if workflow:
            key = f"sync-pull-{suffix}"
            col2.checkbox(f"⬇️ Download results ({_summary(results, _PULL_PENDING, 'pull')})",
                          value=client.direction_on(prefs, workflow, "pull"), key=key,
                          on_change=_set_pref, args=(workspace, workflow, "pull", key))
        if run is not None:
            if run["status"] in _RUN_ACTIVE:
                _run_live(workspace, link, workflow, inputs, busy)
            else:
                _run_view(workspace, link, workflow, run, inputs, busy)
        with st.expander("Individual files"):
            if inputs:
                st.markdown("Inputs")
                selected = _item_table(inputs, f"sync-inputs-{suffix}")
                _transfer_buttons(workspace, link, inputs, selected, "push", busy,
                                  _PUSH_PENDING, suffix)
            if results:
                st.markdown("Results")
                selected = _item_table(results, f"sync-results-{suffix}")
                _transfer_buttons(workspace, link, results, selected, "pull", busy,
                                  _PULL_PENDING, suffix)
            if not (inputs or results):
                st.caption("No files yet.")


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

    prefs = client.read_prefs(workspace)
    _ensure_watcher(workspace)
    if busy:
        _job_progress(workspace)
    elif job is not None:
        _job_result(job)

    status = _load_status(workspace, link)
    if status["error"]:
        st.error(f"The online workspace cannot be reached: {status['error']}")
        return

    up, down = _chosen(status, prefs, pending_only=True)
    col1, col2, _ = st.columns([1, 2, 1])
    if col1.button(f"🔄 Sync now ({len(up) + len(down)})", type="primary", width="stretch",
                   disabled=busy or not (up or down), key="sync-now"):
        _start(workspace, "sync", [i.key for i in up + down], link)
        st.rerun()
    key = f"sync-keep-{workspace.name}"
    col2.checkbox("Keep in sync", value=prefs["keep_in_sync"], key=key,
                  on_change=_set_pref, args=(workspace, None, "keep_in_sync", key),
                  help=f"Every {_WATCH_INTERVAL} s while the app is open, push new or changed "
                       "inputs and pull new or updated results, in the directions ticked below.")
    st.caption(f"States as of {datetime.fromtimestamp(status['at']).strftime('%H:%M:%S')}. "
               "Large files go up in verified chunks; an interrupted transfer continues "
               "where it stopped, also after closing the app.")

    runs = status.get("runs", {})
    workflows = sorted({i.workflow for i in status["inputs"] + status["results"]} | set(runs))
    if not workflows:
        st.info("Nothing to sync yet. Add input files on a workflow's upload page, "
                "or run a workflow online, then refresh.")
    for workflow in workflows:
        _workflow_box(workspace, link, prefs, workflow,
                      [i for i in status["inputs"] if i.workflow == workflow],
                      [i for i in status["results"] if i.workflow == workflow], busy,
                      runs.get(workflow))


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


@st.fragment(run_every=5.0)
def _sidebar_watch(workspace: Path, shown_at: float, follow_run: bool) -> None:
    """Rerun the app when Keep in sync starts a transfer or has fresh
    states, or, while a cloud run is active, when its state is 10 s old, so
    the sidebar follows without a click."""
    job = _JOBS.get(str(workspace))
    with _STATUS_LOCK:
        status = _STATUS.get(str(workspace))
    if ((job is not None and not job.finished) or (status and status["at"] != shown_at)
            or (follow_run and time.time() - shown_at > 10)):
        st.rerun()


def _sidebar_summary(workspace: Path, link: dict, status: dict | None, prefs: dict) -> None:
    job = _JOBS.get(str(workspace))
    if status is None:
        st.caption("Checking the online workspace…")
    elif status["error"]:
        st.caption("⚠️ The online workspace cannot be reached.")
    else:
        up, down = (len(x) for x in _chosen(status, prefs, pending_only=True))
        if up or down:
            st.markdown(f"⬆️ {up} to push · ⬇️ {down} to pull")
        else:
            st.markdown("✅ Up to date")
        for workflow, run in status.get("runs", {}).items():
            if run["status"] in _RUN_ACTIVE:
                st.caption(f"☁️ `{workflow}`: {_run_label(run)}")
        st.caption(f"Checked {datetime.fromtimestamp(status['at']).strftime('%H:%M')}")
    if job is not None and job.error:
        st.caption(f"⚠️ Last transfer stopped: {job.error.split('. ')[0]}.")
    elif job is not None and job.report is not None and job.report.transferred:
        st.caption(f"Last: {_VERBS[job.action][1].lower()} {len(job.report.transferred)} "
                   f"file(s), {_size(job.report.bytes)}"
                   + (" (kept in sync)" if job.auto else ""))
    if prefs["keep_in_sync"]:
        st.caption(f"🔁 Keeping in sync every {_WATCH_INTERVAL} s")
    ready = status is not None and not status["error"]
    if st.button("🔄 Sync", key="sync-sidebar-sync", type="primary", width="stretch",
                 help="Push new or changed inputs and pull new or updated results, "
                      "for the workflows and directions chosen on the sync page.",
                 disabled=not ready):
        up, down = _chosen(status, prefs)
        _start(workspace, "sync", [i.key for i in up + down], link)
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
        prefs = client.read_prefs(workspace)
        _ensure_watcher(workspace)
        job = _JOBS.get(str(workspace))
        if job is not None and not job.finished:
            _sidebar_live(workspace)
        else:
            with _STATUS_LOCK:
                status = _STATUS.get(str(workspace))
            # Follow a cloud run more closely than the files.
            running = status is not None and any(
                r["status"] in _RUN_ACTIVE for r in status.get("runs", {}).values())
            max_age = 10 if running else _STATUS_MAX_AGE
            stale = status is None or time.time() - status["at"] > max_age
            if stale:
                _refresh_in_background(workspace, link)
            _sidebar_summary(workspace, link, status, prefs)
            if stale:
                # Shows the fresh states as soon as they are in.
                _sidebar_live(workspace)
            elif prefs["keep_in_sync"] or running:
                _sidebar_watch(workspace, status["at"], running)
        st.page_link(_PAGE, label="Open sync", icon="📋")
