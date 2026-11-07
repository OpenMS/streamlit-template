"""The sidebar's **AI assistant** panel: connect an assistant to this workspace.

Online it creates a token for the MCP endpoint of the sync service
(``/sync/mcp``); in the local app it shows how to start the stdio server.
Either way it lists what assistants did here lately (``activity.py``).
"""

import json
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.sync import tokens

from . import activity
from .config import agent_settings

_ISSUED = "agent-access-issued"


def enabled() -> bool:
    settings = st.session_state.get("settings") or {}
    return bool(agent_settings(settings)["enabled"])


def _cfg() -> dict:
    return agent_settings(st.session_state.settings)


def _origin() -> str:
    try:
        url = st.context.url or ""
    except Exception:  # noqa: BLE001 - no browser context (tests)
        url = ""
    return "/".join(url.split("/")[:3]) if url.startswith("http") else ""


def _server_name(cfg: dict) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (cfg["app_name"] or "openms-app").lower()).strip("-")


def online_snippets(cfg: dict, url: str, token: str) -> dict:
    name = _server_name(cfg)
    return {
        "Claude Code": f"claude mcp add --transport http {name} {url} "
                       f"--header \"Authorization: Bearer {token}\"",
        "Other MCP clients (JSON)": json.dumps({"mcpServers": {name: {
            "type": "http", "url": url,
            "headers": {"Authorization": f"Bearer {token}"}}}}, indent=2),
    }


def local_snippets(cfg: dict, workspace: Path, app_url: str) -> dict:
    name = _server_name(cfg)
    settings = str(Path("settings.json").resolve())
    app_root = str(Path(settings).parent)
    # The client starts the server in a folder of its own; PYTHONPATH lets
    # it find the app's src package from there.
    args = ["-m", "src.agent_access.stdio", "--settings", settings,
            "--workspaces-dir", str(workspace.parent.resolve()), "--workspace", workspace.name]
    if app_url:
        args += ["--app-url", app_url]
    return {
        "Claude Code": f"claude mcp add {name} -e {shlex.quote('PYTHONPATH=' + app_root)} -- "
                       + " ".join(shlex.quote(a) for a in [sys.executable, *args]),
        "Other MCP clients (JSON)": json.dumps(
            {"mcpServers": {name: {"command": sys.executable, "args": args,
                                   "env": {"PYTHONPATH": app_root}}}}, indent=2),
    }


def _snippets(snippets: dict) -> None:
    for tab, (label, text) in zip(st.tabs(list(snippets)), snippets.items()):
        with tab:
            st.code(text, language="json" if text.startswith("{") else "bash", wrap_lines=True)


@st.dialog("Connect an AI assistant", width="large")
def _connect_dialog(workspace: Path) -> None:
    cfg = _cfg()
    workflows = ", ".join(cfg["workflows"]) or "none"
    st.markdown(
        "An AI assistant that speaks the Model Context Protocol (MCP) can work in this "
        "workspace for you: add input files, set up and start workflows, follow the runs "
        f"and read their results. Workflows it can run here: **{workflows}**."
    )
    if st.session_state.location == "online":
        issued = st.session_state.get(_ISSUED)
        if not issued or issued["workspace"] != workspace.name:
            st.markdown("Create a connection for this workspace, then add it to your assistant.")
            if st.button("Create connection", type="primary", icon=":material/link:"):
                token, expires = tokens.issue(workspace.parent, workspace.name,
                                              cfg["token_ttl_hours"], kind=tokens.AGENT)
                st.session_state[_ISSUED] = {"workspace": workspace.name, "token": token,
                                             "expires": expires,
                                             "url": f"{_origin()}/sync/mcp"}
                st.rerun(scope="fragment")
            return
        st.text("Server address")
        st.code(issued["url"], language=None)
        st.text("Add it to your assistant")
        _snippets(online_snippets(cfg, issued["url"], issued["token"]))
        until = datetime.fromtimestamp(issued["expires"]).strftime("%Y-%m-%d %H:%M")
        st.caption(
            f"Works until {until}. Anyone with this connection can add files to this "
            "workspace, run its workflows and read its results, so keep it to yourself. "
            "**Disconnect** in the sidebar ends every connection of this workspace."
        )
    else:
        st.markdown(
            "Your assistant starts the connection itself, on this computer. Add it with "
            "the command or the configuration below; it works in the workspace "
            f"**{workspace.name}**."
        )
        _snippets(local_snippets(cfg, workspace, _origin()))
        st.caption("The connection uses this app's files on this computer; nothing leaves it.")


def _when(t: float) -> str:
    then = datetime.fromtimestamp(t)
    return then.strftime("%H:%M") if then.date() == datetime.now().date() else then.strftime("%d %b")


_LABELS = {
    "get_app_info": "looked at the app", "describe_workflow": "read the settings",
    "list_files": "listed the files", "upload_file": "uploaded a file",
    "import_from_link": "imported from a link", "get_import_status": "checked the import",
    "delete_file": "deleted a file", "update_settings": "changed settings",
    "start_run": "started a run", "get_run_status": "checked the run",
    "get_run_log": "read the log", "stop_run": "stopped the run", "list_runs": "listed the runs",
    "list_results": "listed results", "read_result": "read a result",
    "get_processing_report": "read the processing report", "get_app_link": "linked here",
}


# No run_every: a timer firing during a page switch crashes the frontend
# (see _resource_panels in common.py).
@st.fragment
def _activity(workspace: Path) -> None:
    seen = set()
    shown = 0
    for entry in activity.recent(workspace, 20):
        label = _LABELS.get(entry.get("tool"), entry.get("tool", ""))
        if label in seen:
            continue
        seen.add(label)
        mark = "⚠️" if entry.get("error") else "·"
        where = f" in `{entry['workflow']}`" if entry.get("workflow") else ""
        st.caption(f"{_when(entry['t'])} {mark} {label}{where}")
        shown += 1
        if shown >= 3:
            break


def render_sidebar() -> None:
    """The panel, for every session (online and local)."""
    if not enabled():
        return
    workspace = Path(st.session_state.workspace)
    online = st.session_state.location == "online"
    connected = tokens.active_count(workspace.parent, workspace.name, tokens.AGENT) if online else 0
    recent = activity.recent(workspace, 1)
    with st.expander("**AI assistant**", icon=":material/smart_toy:",
                     expanded=bool(connected or recent)):
        if connected:
            st.caption(f"🔗 {connected} assistant connection{'s' if connected > 1 else ''} to this workspace")
        elif not recent:
            st.caption("Let an AI assistant run this app's workflows in this workspace.")
        if recent:
            _activity(workspace)
        if st.button("Connect an AI assistant", key="agent-access-connect",
                     icon=":material/add_link:", width="stretch"):
            _connect_dialog(workspace)
        if connected and st.button("Disconnect", key="agent-access-revoke",
                                   icon=":material/link_off:", width="stretch",
                                   help="End every assistant connection of this workspace."):
            tokens.revoke(workspace.parent, workspace.name, tokens.AGENT)
            st.session_state.pop(_ISSUED, None)
            st.rerun()
