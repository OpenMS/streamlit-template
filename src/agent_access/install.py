"""Connect an AI assistant to the local app: the install prompt and Claude Desktop.

The assistant starts the stdio server itself (``stdio.py``). How it learns the
command depends on the assistant:

- Claude Desktop reads ``claude_desktop_config.json``; the AI assistant panel
  writes the server's entry there after the person's OK
  (``connect_claude_desktop``), keeping the person's other servers.
- Claude Science adds a connector in Settings > Connectors: the panel shows
  the fields of a **Local command** connector (``claude_science_local``), or
  online the link of a **Remote** one (``claude_science_remote``).
- An agent with a command line (Claude Code, Codex, Gemini CLI) gets one
  prompt (``install_prompt``) the person pastes into it; the prompt names the
  command for each of them, and the agent registers the server itself.

The working rules travel with the server, as the MCP ``instructions``
(``Tools.instructions``), so they reach every assistant the same way.
Streamlit-free.
"""

import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path


def server_name(app_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (app_name or "openms-app").lower()).strip("-") or "openms-app"


def server_entry(workspace: Path, settings_file: Path, app_url: str = "",
                 python: str = sys.executable) -> dict:
    """``{"command", "args", "env"}``: how an assistant starts the server for ``workspace``."""
    settings_file = Path(settings_file).resolve()
    workspace = Path(workspace).resolve()
    args = ["-m", "src.agent_access.stdio", "--settings", str(settings_file),
            "--workspaces-dir", str(workspace.parent), "--workspace", workspace.name]
    if app_url:
        args += ["--app-url", app_url]
    # The assistant starts the server in a folder of its own; PYTHONPATH lets
    # it find the app's src package from there.
    return {"command": python, "args": args, "env": {"PYTHONPATH": str(settings_file.parent)}}


def _command(entry: dict) -> str:
    return " ".join(shlex.quote(a) for a in [entry["command"], *entry["args"]])


def cli_commands(name: str, entry: dict) -> dict:
    """The command each agent with a command line registers the server with."""
    env = entry["env"]
    claude_env = " ".join(f"-e {shlex.quote(f'{k}={v}')}" for k, v in env.items())
    codex_env = " ".join(f"--env {shlex.quote(f'{k}={v}')}" for k, v in env.items())
    cmd = _command(entry)
    return {
        "Claude Code": f"claude mcp add --scope user {name} {claude_env} -- {cmd}",
        "Codex CLI": f"codex mcp add {name} {codex_env} -- {cmd}",
        # Its option parser would read the server's own --options as its own,
        # so Gemini CLI gets the entry in its settings file instead.
        "Gemini CLI": f"add this entry to \"mcpServers\" in ~/.gemini/settings.json "
                      f"(keep what is there): {json.dumps({name: entry})}",
    }


def claude_science_local(name: str, entry: dict) -> dict:
    """The fields of a Claude Science **Local command** connector, in its form's order."""
    return {
        "Name": name,
        "Command": entry["command"],
        "Arguments": " ".join(shlex.quote(a) for a in entry["args"]),
        "Environment variables": "\n".join(f"{k}={v}" for k, v in entry["env"].items()),
    }


def claude_science_remote(name: str, link: str) -> dict:
    """The fields of a Claude Science **Remote** connector: the token is in the link."""
    return {"Name": name, "URL": link, "Transport": "Streamable HTTP"}


def connector_steps(fields: dict, kind: str) -> str:
    """The fields as text to copy: where to go, then one ``Field: value`` per line."""
    lines = [f"Claude Science: Settings > Connectors > Add connector > {kind}"]
    for field, value in fields.items():
        if "\n" in value:
            lines.append(f"{field}:")
            lines += [f"  {v}" for v in value.splitlines()]
        else:
            lines.append(f"{field}: {value}")
    return "\n".join(lines)


def mcp_json(name: str, entry: dict) -> str:
    """The ``mcpServers`` entry most other MCP clients read."""
    return json.dumps({"mcpServers": {name: entry}}, indent=2)


def install_prompt(app_name: str, workspace: str, name: str, entry: dict) -> str:
    """The prompt the person pastes into Claude Code, Codex or Gemini CLI."""
    commands = cli_commands(name, entry)
    lines = [
        f"Connect yourself to {app_name or 'this OpenMS app'}, a mass spectrometry web app "
        f"running on this computer, through its MCP server, for the workspace \"{workspace}\".",
        "",
        "1. Register the MCP server the way the agent you are does it (do only that one):",
    ]
    lines += [f"   - {agent}: {command}" for agent, command in commands.items()]
    lines += [
        f"   - Any other MCP client: add this to its MCP configuration: {json.dumps({'mcpServers': {name: entry}})}",
        "2. If you can only use the server after a restart, tell me to restart you and stop here.",
        f"3. Otherwise call the server's get_app_info tool and tell me in two sentences what "
        f"{app_name or 'the app'} can analyze here. Its instructions hold the working rules: "
        "follow them for every question I ask about my data.",
    ]
    return "\n".join(lines)


def desktop_config_path() -> Path:
    """Where Claude Desktop keeps its configuration on this computer."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming",
                    "Claude", "claude_desktop_config.json")
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config",
                "Claude", "claude_desktop_config.json")


def desktop_connected(name: str, entry: dict, path: Path | None = None) -> bool:
    """Whether Claude Desktop's configuration has this server, as ``entry`` says."""
    try:
        data = json.loads(Path(path or desktop_config_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and (data.get("mcpServers") or {}).get(name) == entry


def connect_claude_desktop(name: str, entry: dict, path: Path | None = None) -> Path:
    """Add (or update) the server in Claude Desktop's configuration.

    The person's other servers and settings stay; the file as it was is kept
    next to it as ``.bak``. Raises ``ValueError`` for a file that is not a
    JSON object, which is left alone.
    """
    path = Path(path or desktop_config_path())
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError as e:
            raise ValueError(f"{path} is not valid JSON; fix or remove it first.") from e
        if not isinstance(data, dict):
            raise ValueError(f"{path} does not hold a JSON object; fix or remove it first.")
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[name] = entry
    data["mcpServers"] = servers
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path
