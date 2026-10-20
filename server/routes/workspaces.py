"""Workspaces: list, create, delete, load demo data, settings, file browser."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import (
    available_demos,
    copy_demo,
    is_safe_name,
    load_settings,
    workspace_path,
    workspaces_dir,
)

router = APIRouter()


@router.get("/settings")
def settings() -> dict:
    s = load_settings()
    return {
        "app_name": s.get("app-name"),
        "version": s.get("version"),
        "github_user": s.get("github-user"),
        "repository_name": s.get("repository-name"),
        "legal_links": s.get("legal_links", {}),
        "enable_workspaces": s.get("enable_workspaces", True),
        "max_threads": s.get("max_threads", {}).get("local", 4),
        "cpu_count": os.cpu_count() or 1,
        # The Svelte app is the local deployment by construction: there is no
        # online mode, no captcha and no queue.
        "location": "local",
    }


@router.get("/system")
def system(workspace: str = "default") -> dict:
    """CPU, memory and disk of this machine, for the sidebar monitor."""
    import psutil

    vm = psutil.virtual_memory()
    du = shutil.disk_usage(workspace_path(workspace))
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram_used": vm.total - vm.available,
        "ram_total": vm.total,
        "disk_free": du.free,
        "disk_total": du.total,
    }


@router.get("/workspaces")
def list_workspaces() -> dict:
    root = workspaces_dir()
    names = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not names:
        workspace_path("default")
        names = ["default"]
    return {"workspaces": names, "demos": available_demos(), "root": str(root)}


class NewWorkspace(BaseModel):
    name: str


@router.post("/workspaces")
def create_workspace(body: NewWorkspace) -> dict:
    name = body.name.strip()
    if not is_safe_name(name):
        raise HTTPException(400, "Workspace names cannot contain '/' or '\\'")
    workspace_path(name)
    return {"name": name}


@router.delete("/workspaces/{name}")
def delete_workspace(name: str) -> dict:
    path = workspace_path(name, create=False)
    shutil.rmtree(path)
    return {"deleted": name}


class LoadDemo(BaseModel):
    demo: str


@router.post("/workspaces/{name}/load-demo")
def load_demo(name: str, body: LoadDemo) -> dict:
    """Replace the workspace's content with a demo (as the sidebar's Load Demo Data)."""
    target = workspace_path(name)
    if body.demo not in available_demos() or not copy_demo(body.demo, target):
        raise HTTPException(404, f"Demo {body.demo!r} not found")
    (target / "mzML-files").mkdir(exist_ok=True)
    return {"name": name, "demo": body.demo}


@router.get("/fs")
def browse(path: str = "", file_types: str = "") -> dict:
    """
    Server-side file browser for picking files on this machine. It replaces
    the tkinter dialogs of the Streamlit local mode: the browser cannot reveal
    a file's path, but the server runs on the same machine and can list it.
    """
    base = Path(path).expanduser() if path else Path.home()
    if not base.is_absolute():
        base = base.resolve()
    if not base.exists() or not base.is_dir():
        raise HTTPException(404, f"No such folder: {base}")
    types = [t.strip().lower().lstrip(".") for t in file_types.split(",") if t.strip()]
    entries = []
    try:
        children = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        raise HTTPException(403, f"Cannot read {base}")
    for p in children:
        if p.name.startswith("."):
            continue
        matches = not types or any(p.name.lower().endswith("." + t) for t in types)
        if p.is_dir():
            entries.append({"name": p.name, "path": str(p), "dir": True, "selectable": matches})
        elif matches:
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            entries.append({"name": p.name, "path": str(p), "dir": False, "size": size, "selectable": True})
    return {"path": str(base), "parent": str(base.parent) if base.parent != base else None, "entries": entries}
