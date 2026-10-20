"""
Settings, workspace resolution and path safety shared by every route.

Mirrors the local-mode branch of ``src/common/common.py:page_setup()`` without
importing it (that module pulls in Streamlit page code, captcha and analytics).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

# The repository root. Every relative path the template uses (settings.json,
# presets.json, src/python-tools, example-data) is resolved against it, so the
# server always runs with it as CWD.
ROOT = Path(__file__).resolve().parent.parent


def ensure_cwd() -> None:
    if Path.cwd() != ROOT:
        os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


@lru_cache(maxsize=1)
def load_settings() -> dict:
    with open(ROOT / "settings.json", "r", encoding="utf-8") as f:
        return json.load(f)


def workspaces_dir() -> Path:
    """
    Where workspaces live. Same rule as page_setup() in local mode, so the
    Streamlit app and the Svelte app share workspaces. ``SVELTE_WORKSPACES_DIR``
    overrides it (used by the tests).
    """
    override = os.environ.get("SVELTE_WORKSPACES_DIR")
    if override:
        path = Path(override)
    else:
        settings = load_settings()
        if settings.get("workspaces_dir"):
            path = Path(
                settings["workspaces_dir"],
                "workspaces-" + settings["repository-name"],
            )
        else:
            path = Path("..")
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_safe_name(name: str) -> bool:
    """Same check as common.is_safe_workspace_name, also used for file names."""
    if not name:
        return False
    return "/" not in name and "\\" not in name and name not in ("..", ".") and "\0" not in name


def workspace_path(name: str, create: bool = True) -> Path:
    if not is_safe_name(name):
        raise HTTPException(400, f"Invalid workspace name: {name!r}")
    path = workspaces_dir() / name
    if create:
        path.mkdir(parents=True, exist_ok=True)
        (path / "mzML-files").mkdir(parents=True, exist_ok=True)
    elif not path.exists():
        raise HTTPException(404, f"Workspace {name!r} not found")
    return path


def safe_join(base: Path, rel: str) -> Path:
    """Join a user supplied relative path under base, refusing traversal."""
    target = (base / rel).resolve()
    base_resolved = base.resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise HTTPException(400, "Path escapes its directory")
    return target


# ---------------------------------------------------------------- demo workspaces


def demo_source_dirs() -> list[Path]:
    config = load_settings().get("demo_workspaces", {})
    if not config.get("enabled", False):
        return []
    if "source_dirs" in config:
        dirs = config["source_dirs"]
        if isinstance(dirs, str):
            dirs = [dirs]
    elif "source_dir" in config:
        dirs = [config["source_dir"]]
    else:
        dirs = ["example-data/workspaces"]
    return [ROOT / d for d in dirs if (ROOT / d).exists()]


def available_demos() -> list[str]:
    seen: list[str] = []
    for source in demo_source_dirs():
        for p in sorted(source.iterdir()):
            if p.is_dir() and p.name not in seen:
                seen.append(p.name)
    return seen


def copy_demo(demo: str, target: Path) -> bool:
    """Copy a demo workspace; params.json and .ini are always real copies."""
    if not is_safe_name(demo):
        return False
    source = next((d / demo for d in demo_source_dirs() if (d / demo).is_dir()), None)
    if source is None:
        return False
    if target.exists():
        shutil.rmtree(target)

    def tree(src: Path, dst: Path) -> None:
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            out = dst / item.name
            if item.is_dir():
                tree(item, out)
            elif item.name == "params.json" or item.suffix == ".ini" or sys.platform != "linux":
                shutil.copy2(item, out)
            else:
                out.symlink_to(item.resolve())

    tree(source, target)
    return True


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
