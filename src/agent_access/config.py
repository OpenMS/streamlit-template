"""``agent_access`` in settings.json, with defaults filled in."""

import re

DEFAULTS = {
    "enabled": False,
    # Only a session in developer mode (Settings -> Developer password) sees
    # the AI assistant panel and follows the assistant.
    "developer_only": True,
    # How long a token from the sidebar works.
    "token_ttl_hours": 24,
    # Tool calls per token and minute (per sync service replica).
    "calls_per_minute": 120,
    # One upload_file call; larger files are sent in parts (append=true).
    "max_upload_mb": 64,
    # A file imported from a link.
    "max_import_gb": 20,
    # The address people open the app at, for the links tools return. Empty:
    # derived from the request (online) or http://localhost:<port> (local).
    "public_url": "",
    # Workflows an assistant may run: workflow directory -> "module:Class",
    # or {"class": "module:Class", "configure_page": ..., "run_page": ...,
    # "results_page": ...}. Empty: those of workspace_sync.workflows.
    "workflows": {},
}

_WORKFLOW_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def agent_settings(settings: dict) -> dict:
    cfg = {**DEFAULTS, **(settings.get("agent_access") or {})}
    workflows = cfg.get("workflows") or (settings.get("workspace_sync") or {}).get("workflows") or {}
    cfg["workflows"] = {
        name: _workflow_entry(entry) for name, entry in workflows.items()
        if _WORKFLOW_NAME.match(name) and _workflow_entry(entry)["class"]
    }
    cfg["app_name"] = settings.get("app-name", "")
    cfg["version"] = settings.get("version", "")
    cfg["online"] = bool(settings.get("online_deployment"))
    return cfg


def _workflow_entry(entry) -> dict:
    if isinstance(entry, str):
        entry = {"class": entry}
    if not isinstance(entry, dict):
        entry = {}
    return {
        "class": str(entry.get("class") or ""),
        "configure_page": str(entry.get("configure_page") or ""),
        "run_page": str(entry.get("run_page") or ""),
        "results_page": str(entry.get("results_page") or ""),
        "description": str(entry.get("description") or ""),
    }
