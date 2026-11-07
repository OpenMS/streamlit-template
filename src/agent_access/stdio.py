"""MCP over stdio, for an assistant on the same computer as the local app.

    python -m src.agent_access.stdio --workspace default

run from the app's folder (the AI assistant panel in the sidebar shows the
exact command and a config snippet). One JSON-RPC message per line on stdin,
one answer per line on stdout; everything else goes to stderr. No token: the
assistant already runs as the person, on their computer.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import protocol
from .config import agent_settings
from .tools import Tools


def _workspaces_dir(settings: dict) -> Path:
    if settings.get("online_deployment"):
        return Path(os.environ.get("WORKSPACES_DIR", "/workspaces-streamlit-template"))
    # As src.common.common.local_workspaces_dir, which needs Streamlit to import.
    if os.environ.get("LOCAL_WORKSPACES_DIR"):
        return Path(os.environ["LOCAL_WORKSPACES_DIR"])
    if settings.get("workspaces_dir"):
        return Path(settings["workspaces_dir"], "workspaces-" + settings["repository-name"])
    return Path("..")


def serve(tools: Tools, stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            answer = protocol._error(None, protocol.PARSE_ERROR, "not JSON")
        else:
            answer = protocol.handle(message, tools)
        if answer is not None:
            stdout.write(json.dumps(answer, default=str) + "\n")
            stdout.flush()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="default", help="The workspace to work in.")
    parser.add_argument("--settings", default="settings.json",
                        help="The app's settings.json; the app's folder is where it is.")
    parser.add_argument("--workspaces-dir", default="",
                        help="Where the app keeps its workspaces (default: as the app finds it).")
    parser.add_argument("--app-url", default="http://localhost:8501",
                        help="Where the app runs, for the links the tools return.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s agent-access %(message)s")
    settings_path = Path(args.settings).resolve()
    app_root = settings_path.parent
    os.chdir(app_root)
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    cfg = agent_settings(settings)
    if not cfg["enabled"]:
        print("agent_access is not enabled in settings.json", file=sys.stderr)
        return 1
    name = args.workspace
    if not name or "/" in name or "\\" in name or name.startswith("."):
        print(f"not a workspace name: {name!r}", file=sys.stderr)
        return 2
    workspace = Path(args.workspaces_dir or _workspaces_dir(settings), name)
    workspace.mkdir(parents=True, exist_ok=True)
    app_url = cfg["public_url"] or args.app_url
    serve(Tools(app_root, workspace, cfg, app_url=app_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
