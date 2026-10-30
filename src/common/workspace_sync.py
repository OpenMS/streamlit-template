"""Sidebar panels for workspace sync (see ``src/sync``).

Online, "Link desktop app" issues a sync token for the current workspace.
Offline (the Electron app), "Sync with online workspace" links the local
workspace with that token, pushes inputs and parameters, and pulls results.

A push of several GB outlasts any script run, so transfers run in a
background thread registered per workspace; a fragment polls it while it
runs, which also keeps the transfer alive across page switches.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.sync import client, server, tokens


@dataclass
class _Job:
    action: str
    cancel: threading.Event = field(default_factory=threading.Event)
    done: int = 0
    total: int = 0
    current: str = ""
    phase: str = "Comparing files"
    report: client.SyncReport | None = None
    error: str = ""
    finished: bool = False


_JOBS: dict[str, _Job] = {}
_JOBS_LOCK = threading.Lock()


def _settings() -> dict:
    return server.sync_settings(st.session_state.settings)


def _start(workspace: Path, action: str, link: dict) -> None:
    job = _Job(action)
    with _JOBS_LOCK:
        running = _JOBS.get(str(workspace))
        if running and not running.finished:
            return
        _JOBS[str(workspace)] = job

    def progress(done, total, rel):
        job.phase, job.done, job.total, job.current = "Transferring", done, total, rel

    def run():
        try:
            c = client.SyncClient(link["url"], link["token"])
            fn = c.push if action == "push" else c.pull
            job.report = fn(workspace, progress=progress, cancel=job.cancel)
        except client.Cancelled:
            job.error = "Cancelled. Starting again continues where it stopped."
        except Exception as exc:  # surfaced in the panel, never lost in a thread
            job.error = str(exc)
        finally:
            job.finished = True

    threading.Thread(target=run, daemon=True, name=f"workspace-sync-{action}").start()


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


_VERBS = {"push": ("Pushing inputs", "Pushed"), "pull": ("Pulling results", "Pulled")}


@st.fragment(run_every=1.0)
def _job_progress(workspace: Path) -> None:
    """Poll a running transfer; rerun the whole page once it has finished."""
    job = _JOBS.get(str(workspace))
    if job is None or job.finished:
        st.rerun()
        return
    verb = _VERBS[job.action][0]
    if job.total:
        st.progress(job.done / job.total,
                    text=f"{verb}: {_size(job.done)} of {_size(job.total)}")
    else:
        st.progress(0.0, text=f"{verb}: {job.phase.lower()}…")
    if job.current:
        st.caption(job.current)
    if st.button("Cancel", key="sync-cancel"):
        job.cancel.set()


def _job_result(job: _Job) -> None:
    if job.error:
        st.error(job.error)
    elif job.report is not None:
        r = job.report
        if r.transferred:
            st.success(f"{_VERBS[job.action][1]} {len(r.transferred)} file(s), "
                       f"{_size(r.bytes)}; {r.unchanged} already up to date.")
        else:
            st.info(f"Everything is up to date ({r.unchanged} file(s)).")


def _offline_panel(workspace: Path) -> None:
    cfg = _settings()
    with st.expander("☁️ **Sync with online workspace**"):
        link = client.read_link(workspace)
        if not link:
            st.caption(
                "Send this workspace's input files and parameters to an online "
                "workspace and fetch the results back. Create a sync token in "
                "the online app under **Link desktop app**."
            )
            url = st.text_input("Server URL", value=cfg["public_url"], key="sync-url",
                                placeholder="https://example.org/sync")
            token = st.text_input("Sync token", type="password", key="sync-token")
            if st.button("Link workspace", disabled=not (url and token)):
                try:
                    name = client.SyncClient(url, token, retries=0, timeout=20).check()
                except client.SyncError as exc:
                    st.error(str(exc))
                else:
                    client.write_link(workspace, {"url": url.strip(), "token": token.strip(),
                                                  "workspace": name, "uploads": {}})
                    st.rerun()
            return

        st.markdown(f"Linked to online workspace `{link.get('workspace', '?')}`")
        st.caption(link["url"])
        job = _JOBS.get(str(workspace))
        busy = job is not None and not job.finished
        col1, col2 = st.columns(2)
        if col1.button("⬆️ Push inputs", disabled=busy, use_container_width=True,
                       help="Upload input files and parameters the online workspace does not have yet."):
            _start(workspace, "push", link)
            st.rerun()
        if col2.button("⬇️ Pull results", disabled=busy, use_container_width=True,
                       help="Download results the online workspace produced."):
            _start(workspace, "pull", link)
            st.rerun()
        if busy:
            _job_progress(workspace)
        elif job is not None:
            _job_result(job)
        if st.button("Unlink", disabled=busy, key="sync-unlink"):
            client.unlink_workspace(workspace)
            st.rerun()


def _public_url(cfg: dict) -> str:
    if cfg["public_url"]:
        return cfg["public_url"].rstrip("/")
    try:
        app_url = st.context.url
    except Exception:
        app_url = ""
    origin = "/".join(app_url.split("/")[:3]) if app_url else ""
    return f"{origin}/sync"


def _online_panel(workspace: Path) -> None:
    cfg = _settings()
    root = workspace.parent
    with st.expander("🔗 **Link desktop app**"):
        st.caption(
            "Let the desktop app send large files (raw files, Bruker .d folders) "
            "straight into this workspace and fetch results back. Paste the "
            "server URL and token into **Sync with online workspace** there."
        )
        issued = st.session_state.get("sync-issued")
        if issued and issued["workspace"] == workspace.name:
            st.text("Server URL")
            st.code(issued["url"], language=None)
            st.text("Sync token")
            st.code(issued["token"], language=None)
            st.caption(
                "Valid until "
                f"{datetime.fromtimestamp(issued['expires']).strftime('%Y-%m-%d %H:%M')}. "
                "Anyone with this token can add files to this workspace."
            )
        if st.button("Create sync token", key="sync-issue"):
            token, expires = tokens.issue(root, workspace.name, cfg["token_ttl_hours"])
            st.session_state["sync-issued"] = {
                "workspace": workspace.name, "token": token,
                "expires": expires, "url": _public_url(cfg),
            }
            st.rerun()
        active = tokens.active_count(root, workspace.name)
        if active and st.button(f"Revoke {active} active token(s)", key="sync-revoke"):
            tokens.revoke(root, workspace.name)
            st.session_state.pop("sync-issued", None)
            st.rerun()


def render_workspace_sync() -> None:
    """Render the sync panel that fits the current deployment, if enabled."""
    if not _settings()["enabled"] or not st.session_state.settings.get("enable_workspaces"):
        return
    workspace = Path(st.session_state.workspace)
    if st.session_state.location == "online":
        _online_panel(workspace)
    else:
        _offline_panel(workspace)
