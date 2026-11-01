"""Sync tokens: the credential that links an offline workspace to an online one.

The online app issues a token for its current workspace; the offline app
presents it on every request. Only the sha256 of a token is stored, as
``<workspaces root>/.sync-tokens/<sha256>.json``, so the store works on the
shared NFS volume without Redis and a leaked directory listing grants
nothing. The dot-prefix keeps ``clean-up-workspaces.py`` from treating the
store as a workspace.

The workspace UUID alone is deliberately not a credential: workspace links
are shared freely, and a shared link should not grant upload access.
"""

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

TOKEN_DIR = ".sync-tokens"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _valid_workspace_name(name: str) -> bool:
    return bool(name) and "/" not in name and "\\" not in name and not name.startswith(".")


def issue(root: Path, workspace: str, ttl_hours: float) -> tuple[str, float]:
    """Create a token for ``workspace``; return (token, expiry as epoch seconds)."""
    if not _valid_workspace_name(workspace):
        raise ValueError(f"invalid workspace name: {workspace!r}")
    token = secrets.token_urlsafe(32)
    expires = time.time() + ttl_hours * 3600
    store = Path(root, TOKEN_DIR)
    store.mkdir(parents=True, exist_ok=True)
    Path(store, _hash(token) + ".json").write_text(
        json.dumps({"workspace": workspace, "expires": expires})
    )
    return token, expires


def resolve(root: Path, token: str) -> str | None:
    """Return the workspace a token belongs to, or None if unknown or expired."""
    if not token or len(token) > 256:
        return None
    entry = Path(root, TOKEN_DIR, _hash(token) + ".json")
    try:
        data = json.loads(entry.read_text())
    except (OSError, ValueError):
        return None
    if data.get("expires", 0) < time.time():
        entry.unlink(missing_ok=True)
        return None
    workspace = data.get("workspace", "")
    if not _valid_workspace_name(workspace) or not Path(root, workspace).is_dir():
        return None
    return workspace


def _entries(root: Path):
    store = Path(root, TOKEN_DIR)
    if not store.is_dir():
        return
    for entry in store.glob("*.json"):
        try:
            yield entry, json.loads(entry.read_text())
        except (OSError, ValueError):
            yield entry, {}


def active_count(root: Path, workspace: str) -> int:
    now = time.time()
    return sum(
        1 for _, d in _entries(root)
        if d.get("workspace") == workspace and d.get("expires", 0) >= now
    )


def revoke(root: Path, workspace: str) -> int:
    """Delete every token of ``workspace``; return how many were removed."""
    removed = 0
    for entry, data in list(_entries(root)):
        if data.get("workspace") == workspace:
            entry.unlink(missing_ok=True)
            removed += 1
    return removed


def prune(root: Path) -> int:
    """Delete expired or unreadable tokens; return how many were removed."""
    removed = 0
    now = time.time()
    for entry, data in list(_entries(root)):
        if data.get("expires", 0) < now:
            try:
                os.unlink(entry)
                removed += 1
            except OSError:
                pass
    return removed
