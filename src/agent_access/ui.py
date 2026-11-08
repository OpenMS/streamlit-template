"""The sidebar's **AI assistant** panel: connect an assistant to this workspace.

Online it creates a token for the MCP endpoint of the sync service
(``/sync/mcp``); in the local app it shows how to start the stdio server.
Either way it lists what assistants did here lately (``activity.py``).
"""

import json
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.sync import tokens

from . import activity, install, show
from .config import agent_settings

_ISSUED = "agent-access-issued"
FOLLOW = "agent-access-follow"
_SEEN = "agent-access-shown"
_NOTE = "agent-access-note"


def enabled() -> bool:
    """Whether this session shows the assistant (``developer_only``: after unlocking)."""
    settings = st.session_state.get("settings") or {}
    cfg = agent_settings(settings)
    if not cfg["enabled"]:
        return False
    from src.common.developer import is_developer
    return not cfg["developer_only"] or is_developer()


def _cfg() -> dict:
    return agent_settings(st.session_state.settings)


def _origin() -> str:
    try:
        url = st.context.url or ""
    except Exception:  # noqa: BLE001 - no browser context (tests)
        url = ""
    return "/".join(url.split("/")[:3]) if url.startswith("http") else ""


def _server_name(cfg: dict) -> str:
    return install.server_name(cfg["app_name"])


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
    """The install prompt for agents with a command line, and the JSON for the rest."""
    name = _server_name(cfg)
    entry = install.server_entry(workspace, Path("settings.json"), app_url)
    return {
        "Claude Code, Codex, Gemini CLI": install.install_prompt(cfg["app_name"], workspace.name, name, entry),
        "Claude Code": install.cli_commands(name, entry)["Claude Code"],
        "Other MCP clients (JSON)": install.mcp_json(name, entry),
    }


def _snippets(snippets: dict) -> None:
    for tab, (label, text) in zip(st.tabs(list(snippets)), snippets.items()):
        with tab:
            st.code(text, language="json" if text.startswith("{") else "bash", wrap_lines=True)


def _claude_desktop(cfg: dict, workspace: Path) -> None:
    """Write the server into Claude Desktop's configuration, after the person's OK."""
    name = _server_name(cfg)
    entry = install.server_entry(workspace, Path("settings.json"), _origin())
    path = install.desktop_config_path()
    if install.desktop_connected(name, entry, path):
        st.success(f"Claude Desktop is connected to the workspace **{workspace.name}**. "
                   "Restart Claude Desktop if it does not list the server yet.",
                   icon=":material/check_circle:")
        return
    st.markdown(f"Adds the server **{name}** to Claude Desktop's configuration "
                f"(`{path}`), next to the servers it has; the file as it was is kept as `.bak`.")
    with st.expander("What will be added"):
        st.code(install.mcp_json(name, entry), language="json", wrap_lines=True)
    if st.button("Connect Claude Desktop", type="primary", icon=":material/link:",
                 key="agent-access-desktop"):
        try:
            install.connect_claude_desktop(name, entry, path)
        except (OSError, ValueError) as e:
            st.error(str(e))
            return
        st.success("Done. Quit and reopen Claude Desktop, then ask it about your data.",
                   icon=":material/check_circle:")


# on_dismiss: the page reruns, so a connection created here starts follow().
@st.dialog("Connect an AI assistant", width="large", on_dismiss="rerun")
def _connect_dialog(workspace: Path) -> None:
    cfg = _cfg()
    workflows = ", ".join(cfg["workflows"]) or "none"
    st.markdown(
        "An AI assistant that speaks the Model Context Protocol (MCP) can work in this "
        "workspace for you: add input files, set up and start workflows, follow the runs "
        f"and read their results. Workflows it can run here: **{workflows}**."
    )
    if st.session_state.location == "online":
        issued = _issued(workspace)
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
            "Your assistant starts the connection itself, on this computer, and works in "
            f"the workspace **{workspace.name}**. It processes your data only with this "
            "app's workflows, and shows its answer as a view on the Results page."
        )
        desktop, cli, other = st.tabs(["Claude Desktop", "Claude Code, Codex, Gemini CLI",
                                       "Other MCP clients"])
        snippets = local_snippets(cfg, workspace, _origin())
        with desktop:
            _claude_desktop(cfg, workspace)
        with cli:
            st.caption("Paste this prompt into the agent; it connects itself.")
            st.code(snippets["Claude Code, Codex, Gemini CLI"], language=None, wrap_lines=True)
        with other:
            st.code(snippets["Other MCP clients (JSON)"], language="json", wrap_lines=True)
        st.caption("The connection uses this app's files on this computer; nothing leaves it.")


def _when(t: float) -> str:
    then = datetime.fromtimestamp(t)
    return then.strftime("%H:%M") if then.date() == datetime.now().date() else then.strftime("%d %b")


_LABELS = {
    "get_app_info": "looked at the app", "describe_workflow": "read the settings",
    "list_files": "listed the files", "upload_file": "uploaded a file",
    "import_from_link": "imported from a link", "get_import_status": "checked the import",
    "delete_file": "deleted a file", "update_settings": "changed settings",
    "start_run": "started a run", "follow_up": "started a follow-up run", "get_run_status": "checked the run",
    "get_run_log": "read the log", "stop_run": "stopped the run", "list_runs": "listed the runs",
    "list_results": "listed results", "read_result": "read a result",
    "get_processing_report": "read the processing report", "get_app_link": "linked here",
    "show_in_app": "showed you a page", "save_view": "saved a view for you",
    "delete_view": "deleted a view it saved", "list_result_views": "listed the result views",
    "look_at_results": "looked at the results",
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
        if recent or connected:
            # A key of its own: widget state does not survive a page switch.
            st.toggle("Follow the assistant", key=f"{FOLLOW}-toggle",
                      value=st.session_state.get(FOLLOW, True),
                      on_change=lambda: st.session_state.update(
                          {FOLLOW: st.session_state[f"{FOLLOW}-toggle"]}),
                      help="Open the pages and runs the assistant shows you, as it shows them.")
        if st.button("Connect an AI assistant", key="agent-access-connect",
                     icon=":material/add_link:", width="stretch"):
            _connect_dialog(workspace)
        if connected and st.button("Disconnect", key="agent-access-revoke",
                                   icon=":material/link_off:", width="stretch",
                                   help="End every assistant connection of this workspace."):
            tokens.revoke(workspace.parent, workspace.name, tokens.AGENT)
            st.session_state.pop(_ISSUED, None)
            st.rerun()


def follow() -> None:
    """Open what the assistant shows (``show_in_app``), on every page of the session.

    Called by ``page_setup()`` in the page's main area. The note of the
    request that opened this page is shown first; then, while the person
    follows, a fragment checks for a new request every two seconds. It draws
    nothing, so a check that fires during a page switch sends no elements
    to the page being left (see ``_resource_panels`` in common.py).
    """
    if not enabled() or "workspace" not in st.session_state:
        return
    note = st.session_state.pop(_NOTE, None)
    if note:
        st.toast(note, icon=":material/smart_toy:")
    workspace = Path(st.session_state.workspace)
    if _SEEN not in st.session_state:
        # What was shown before this session opened is not news.
        st.session_state[_SEEN] = (show.latest(workspace) or {}).get("id")
    if st.session_state.get(FOLLOW, True) and _assistant_may_show(workspace):
        _watch(str(workspace))


def _issued(workspace: Path) -> dict | None:
    """The connection this session made, or None once it has expired or was
    disconnected (in any session)."""
    issued = st.session_state.get(_ISSUED)
    if issued and (issued.get("expires", 0) <= time.time()
                   or tokens.resolve(workspace.parent, issued.get("token", ""),
                                     tokens.AGENT) != issued.get("workspace")):
        st.session_state.pop(_ISSUED, None)
        return None
    return issued


def _assistant_may_show(workspace: Path) -> bool:
    """Online, only a workspace with a live assistant connection is watched;
    locally an assistant starts its own connection, so every one is."""
    if st.session_state.get("location") != "online":
        return True
    issued = _issued(workspace) or {}
    return (issued.get("workspace") == workspace.name
            or tokens.active_count(workspace.parent, workspace.name, tokens.AGENT) > 0)


@st.fragment(run_every=2.0)
def _watch(workspace: str) -> None:
    # The connection can expire or be disconnected while this fragment reruns.
    if not _assistant_may_show(Path(workspace)):
        return
    request = show.latest(Path(workspace))
    if not request or request["id"] == st.session_state.get(_SEEN):
        return
    st.session_state[_SEEN] = request["id"]
    open_request(Path(workspace), request)


def open_request(workspace: Path, request: dict) -> None:
    """Pick the request's run, keep its note for the page, and open the page."""
    from src.workflow import run_widgets
    from src.workflow.RunManager import RunManager

    workflow = str(request.get("workflow") or "")
    if request.get("run_id") and workflow in _cfg()["workflows"]:
        run_widgets.set_selected_run(RunManager(Path(workspace, workflow)), request["run_id"])
    st.session_state[_NOTE] = request.get("note") or "The assistant opened this page."
    page = request.get("page_file")
    if page and Path(page).is_file():
        st.switch_page(page)
    st.rerun(scope="app")
