"""
TOPP workflow framework: spec, input files, parameters, presets, runs and
results of one workflow in one workspace.

All routes live under ``/api/ws/{ws}/wf/{slug}``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from src.workflow.ParameterManager import InvalidParameterFileError, ParameterManager

from .. import params as P
from .. import runner
from ..core import human_size, is_safe_name, load_settings, safe_join, workspace_path
from ..tables import read_table_page
from ..workflow_spec import TOPP, Python, SelectFiles, Tab, Widget, WorkflowSpec
from ..workflows import WORKFLOWS, get_workflow

router = APIRouter()


def _ctx(ws: str, slug: str) -> tuple[WorkflowSpec, Path, ParameterManager]:
    spec = get_workflow(slug)
    workflow_dir = workspace_path(ws) / spec.slug
    workflow_dir.mkdir(parents=True, exist_ok=True)
    return spec, workflow_dir, ParameterManager(workflow_dir, workflow_name=spec.name)


def _strict(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except InvalidParameterFileError as e:
        raise HTTPException(
            409,
            f"{e} Nothing was written, so no stored parameters were lost. "
            "Repair the file, or reset to defaults to continue.",
        )


@router.get("/workflows")
def list_workflows() -> list[dict]:
    return [{"name": w.name, "slug": w.slug, "description": w.description} for w in WORKFLOWS]


@router.get("/ws/{ws}/wf/{slug}")
def workflow_spec(ws: str, slug: str) -> dict:
    spec, _, pm = _ctx(ws, slug)
    d = spec.to_dict()
    d["presets"] = [
        {"name": n, "description": pm.get_preset_description(n)} for n in pm.get_preset_names()
    ]
    return d


# ------------------------------------------------------------------- input files


def _upload_spec(spec: WorkflowSpec, key: str):
    for u in spec.upload:
        if u.key == key:
            return u
    raise HTTPException(404, f"No upload {key!r} in this workflow")


def _files_dir(workflow_dir: Path, key: str) -> Path:
    if not is_safe_name(key):
        raise HTTPException(400, "Invalid key")
    d = Path(workflow_dir, "input-files", key)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_files(files_dir: Path) -> list[dict]:
    out = []
    for f in sorted(files_dir.iterdir()):
        if f.name == "external_files.txt":
            continue
        size = sum(p.stat().st_size for p in f.rglob("*") if p.is_file()) if f.is_dir() else f.stat().st_size
        out.append({"name": f.name, "path": str(f), "size": human_size(size), "reference": False})
    ext = files_dir / "external_files.txt"
    if ext.exists():
        for line in ext.read_text().splitlines():
            line = line.strip()
            if line:
                exists = os.path.exists(line)
                out.append(
                    {
                        "name": Path(line).name,
                        "path": line,
                        "size": human_size(Path(line).stat().st_size) if exists and Path(line).is_file() else "",
                        "reference": True,
                        "missing": not exists,
                    }
                )
    return out


def _is_only_fallback(files_dir: Path, fallback: list[str]) -> bool:
    names = sorted(p.name for p in files_dir.iterdir())
    return bool(fallback) and names == sorted(Path(f).name for f in fallback)


@router.get("/ws/{ws}/wf/{slug}/files/{key}")
def list_input_files(ws: str, slug: str, key: str) -> dict:
    spec, wd, _ = _ctx(ws, slug)
    u = _upload_spec(spec, key)
    d = _files_dir(wd, key)
    # Same rule as upload_widget: with nothing uploaded, offer the example files
    if u.fallback and not any(d.iterdir()):
        for f in u.fallback:
            if Path(f).exists():
                shutil.copy(f, d / Path(f).name)
    return {"files": _list_files(d), "only_example": _is_only_fallback(d, u.fallback)}


def _accepts(name: str, file_types: list[str]) -> bool:
    return not file_types or any(name.lower().endswith("." + t.lower().lstrip(".")) for t in file_types)


@router.post("/ws/{ws}/wf/{slug}/files/{key}")
async def upload_input_files(ws: str, slug: str, key: str, files: list[UploadFile] = File(...)) -> dict:
    spec, wd, _ = _ctx(ws, slug)
    u = _upload_spec(spec, key)
    d = _files_dir(wd, key)
    if _is_only_fallback(d, u.fallback):
        shutil.rmtree(d)
        d.mkdir()
    added, skipped = [], []
    for up in files:
        name = Path(up.filename or "").name
        if not is_safe_name(name) or not _accepts(name, u.file_types):
            skipped.append(name)
            continue
        with open(d / name, "wb") as fh:
            while chunk := await up.read(1 << 20):
                fh.write(chunk)
        added.append(name)
    return {"added": added, "skipped": skipped, "files": _list_files(d)}


class LocalFiles(BaseModel):
    paths: list[str]
    copy_files: bool = True


@router.post("/ws/{ws}/wf/{slug}/files/{key}/local")
def add_local_files(ws: str, slug: str, key: str, body: LocalFiles) -> dict:
    """
    Add files (or a folder's matching files) from this machine, copied into
    the workspace or referenced in place via external_files.txt.
    """
    spec, wd, _ = _ctx(ws, slug)
    u = _upload_spec(spec, key)
    d = _files_dir(wd, key)
    if _is_only_fallback(d, u.fallback):
        shutil.rmtree(d)
        d.mkdir()
    picked: list[Path] = []
    for raw in body.paths:
        p = Path(raw).expanduser()
        if not p.exists():
            raise HTTPException(404, f"Not found: {p}")
        if p.is_dir() and not _accepts(p.name, u.file_types):
            picked += [c for c in sorted(p.iterdir()) if _accepts(c.name, u.file_types)]
        elif _accepts(p.name, u.file_types):
            picked.append(p)
    if not picked:
        raise HTTPException(400, f"No files of type {', '.join(u.file_types)} found.")
    ext = d / "external_files.txt"
    existing = set(ext.read_text().splitlines()) if ext.exists() else set()
    for p in picked:
        if body.copy_files:
            if p.is_dir():
                shutil.copytree(p, d / p.name, dirs_exist_ok=True)
            else:
                shutil.copy(p, d / p.name)
        elif str(p) not in existing:
            with open(ext, "a") as fh:
                fh.write(f"{p}\n")
    return {"added": [p.name for p in picked], "files": _list_files(d)}


@router.delete("/ws/{ws}/wf/{slug}/files/{key}")
def remove_input_files(ws: str, slug: str, key: str, name: str | None = None, path: str | None = None) -> dict:
    """Remove one file (by name, or a reference by path), or all with neither."""
    _, wd, _ = _ctx(ws, slug)
    d = _files_dir(wd, key)
    ext = d / "external_files.txt"
    if name is None and path is None:
        shutil.rmtree(d)
        d.mkdir()
    elif path is not None:
        if ext.exists():
            keep = [l for l in ext.read_text().splitlines() if l.strip() and l.strip() != path]
            ext.write_text("".join(f"{l}\n" for l in keep)) if keep else ext.unlink()
    else:
        target = safe_join(d, name)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    return {"files": _list_files(d)}


@router.get("/ws/{ws}/wf/{slug}/input-zip")
def input_zip(ws: str, slug: str) -> FileResponse:
    """Download all input files (the upload page's 'Download files' button)."""
    _, wd, _ = _ctx(ws, slug)
    src = Path(wd, "input-files")
    out = Path(wd, "downloads", "input-files.zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in src.rglob("*"):
            if f.is_file() and f.name != "external_files.txt":
                z.write(f, f.relative_to(src))
    return FileResponse(out, filename=f"{wd.name}-input-files.zip", media_type="application/zip")


# -------------------------------------------------------------------- parameters


def _render(items, wd: Path, pm: ParameterManager) -> list[dict]:
    out = []
    for it in items:
        if isinstance(it, Tab):
            out.append({"type": "tab", "label": it.label, "items": _render(it.items, wd, pm)})
            continue
        d = {k: v for k, v in it.__dict__.items()}
        if isinstance(it, TOPP):
            d["schema"] = _strict(P.topp_schema, pm, it)
        elif isinstance(it, Python):
            d["schema"] = P.python_schema(pm, it)
        elif isinstance(it, (SelectFiles, Widget)):
            d["state"] = P.widget_schema(pm, wd, it)
        out.append(d)
    return out


@router.get("/ws/{ws}/wf/{slug}/configure")
def configure(ws: str, slug: str) -> dict:
    """The configure page, resolved: every widget with its current value."""
    spec, wd, pm = _ctx(ws, slug)
    items = _render(spec.configure, wd, pm)
    # Store the defaults of widgets never touched, as rendering them does in
    # Streamlit: execution() reads self.params[key] and expects the key.
    missing: dict[str, Any] = {}
    stored = pm.get_parameters_from_json()

    def collect(rendered):
        for it in rendered:
            if it["type"] == "tab":
                collect(it["items"])
            elif it["type"] in ("widget", "select-files") and it["key"] not in stored:
                missing[it["key"]] = it["state"]["value"]

    collect(items)
    if missing:
        _strict(P.save_general, pm, missing)
        stored = pm.get_parameters_from_json()
    settings = load_settings()
    return {
        "items": items,
        "max_threads": stored.get("max_threads", settings.get("max_threads", {}).get("local", 4)),
        "values": {k: v for k, v in stored.items() if not isinstance(v, dict) and not k.startswith("_")},
    }


def _topp_item(spec: WorkflowSpec, instance: str) -> TOPP:
    for it in spec.iter_items("topp"):
        if it.instance == instance:
            return it
    raise HTTPException(404, f"No TOPP tool {instance!r} in this workflow")


class Values(BaseModel):
    values: dict[str, Any]


@router.put("/ws/{ws}/wf/{slug}/topp/{instance}")
def save_topp(ws: str, slug: str, instance: str, body: Values) -> dict:
    spec, _, pm = _ctx(ws, slug)
    return _strict(P.save_topp, pm, _topp_item(spec, instance), body.values)


@router.put("/ws/{ws}/wf/{slug}/params")
def save_params(ws: str, slug: str, body: Values) -> dict:
    """General widget, file selection, python-tool and max_threads values."""
    _, _, pm = _ctx(ws, slug)
    _strict(P.save_general, pm, body.values)
    return {"ok": True}


@router.post("/ws/{ws}/wf/{slug}/params/reset")
def reset_params(ws: str, slug: str) -> dict:
    _, _, pm = _ctx(ws, slug)
    backup = pm.reset_to_default_parameters()
    return {"backup": backup.name if backup else None}


@router.get("/ws/{ws}/wf/{slug}/params/export")
def export_params(ws: str, slug: str) -> FileResponse:
    _, _, pm = _ctx(ws, slug)
    if not pm.params_file.exists():
        pm.write_parameters({})
    return FileResponse(pm.params_file, filename="parameters.json", media_type="application/json")


@router.post("/ws/{ws}/wf/{slug}/params/import")
async def import_params(ws: str, slug: str, file: UploadFile = File(...)) -> dict:
    _, _, pm = _ctx(ws, slug)
    raw = (await file.read()).decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Not a parameter file: {e}")
    if not isinstance(data, dict):
        raise HTTPException(400, "Not a parameter file: expected a JSON object")
    pm.write_parameters(data)
    return {"ok": True}


@router.post("/ws/{ws}/wf/{slug}/presets/{name}")
def apply_preset(ws: str, slug: str, name: str) -> dict:
    _, _, pm = _ctx(ws, slug)
    if not pm.apply_preset(name):
        raise HTTPException(404, f"Could not apply preset {name!r}")
    return {"applied": name}


@router.get("/ws/{ws}/wf/{slug}/summary")
def param_summary(ws: str, slug: str) -> dict:
    _, _, pm = _ctx(ws, slug)
    return P.summary(pm.get_parameters_from_json())


@router.get("/ws/{ws}/wf/{slug}/method-summary", response_class=PlainTextResponse)
def method_summary(ws: str, slug: str) -> str:
    """Markdown method summary for publications (export_parameters_markdown)."""
    _, _, pm = _ctx(ws, slug)
    s = load_settings()
    url = f"https://github.com/{s['github-user']}/{s['repository-name']}"
    tools = sorted(p.stem for p in Path(pm.ini_dir).glob("*.ini"))
    tools_text = ", ".join(tools[:-1]) + " and " + tools[-1] if len(tools) > 1 else "".join(tools)
    version = ""
    try:
        r = subprocess.run(["FileFilter", "--help"], text=True, capture_output=True, timeout=20)
        if r.returncode == 0 and "Version: " in r.stderr:
            version = r.stderr.split("Version: ")[1].split("-")[0]
    except (OSError, subprocess.SubprocessError):
        pass
    summ = P.summary(pm.get_parameters_from_json())
    lines = [
        f"Data was processed using **{s['app-name']}** ([{url}]({url})), a web application based on the OpenMS WebApps framework [1].",
        "OpenMS ([https://www.openms.de](https://www.openms.de)) is a free and open-source software for LC-MS data analysis [2].",
        f"The workflow includes the **OpenMS {version}** TOPP tools {tools_text} as well as Python scripts. Non-default parameters are listed in the supplementary section below.",
        "",
        '[1] Müller, Tom David, et al. "OpenMS WebApps: Building User-Friendly Solutions for MS Analysis." (2025) [https://doi.org/10.1021/acs.jproteome.4c00872](https://doi.org/10.1021/acs.jproteome.4c00872).',
        "",
        '[2] Pfeuffer, Julianus, et al. "OpenMS 3 enables reproducible analysis of large-scale mass spectrometry data." (2024) [https://doi.org/10.1038/s41592-024-02197-7](https://doi.org/10.1038/s41592-024-02197-7).',
        "",
    ]
    for title, group in (("General", summ["general"]), ("OpenMS TOPP Tools", summ["topp"]), ("Python Scripts", summ["python"])):
        if not group:
            continue
        lines.append(f"**{title}**\n")
        for k, v in group.items():
            if isinstance(v, dict):
                lines.append(f"> **{k}**\n")
                lines += [f">> {kk}: **{vv}**\n" for kk, vv in v.items()]
            else:
                lines.append(f">> {k}: **{', '.join(map(str, v)) if isinstance(v, list) else v}**\n")
    return "\n".join(lines)


# --------------------------------------------------------------------- execution


@router.post("/ws/{ws}/wf/{slug}/run")
def run(ws: str, slug: str) -> dict:
    spec, wd, _ = _ctx(ws, slug)
    if not runner.start(spec, wd):
        raise HTTPException(409, "The workflow is already running")
    return runner.status(wd)


@router.post("/ws/{ws}/wf/{slug}/stop")
def stop(ws: str, slug: str) -> dict:
    _, wd, _ = _ctx(ws, slug)
    runner.stop(wd)
    return runner.status(wd)


@router.get("/ws/{ws}/wf/{slug}/status")
def status(ws: str, slug: str, level: str = "minimal", lines: int = 100) -> dict:
    _, wd, _ = _ctx(ws, slug)
    return runner.status(wd, level, lines or None)


# ----------------------------------------------------------------------- results


def _results_files(wd: Path, exclude: list[str]) -> list[Path]:
    results = Path(wd, "results")
    if not results.exists():
        return []
    return [
        p.relative_to(results)
        for p in sorted(results.rglob("*"))
        if p.is_file() and not any(fnmatch(part, pat) for part in p.relative_to(results).parts for pat in exclude)
    ]


@router.get("/ws/{ws}/wf/{slug}/results/files")
def results_files(ws: str, slug: str) -> dict:
    spec, wd, _ = _ctx(ws, slug)
    out = []
    for rel in _results_files(wd, spec.download_exclude):
        p = Path(wd, "results", rel)
        st = p.stat()
        out.append(
            {
                "path": str(rel),
                "folder": rel.parts[0] if len(rel.parts) > 1 else ".",
                "size": human_size(st.st_size),
                "bytes": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        )
    return {"files": out}


@router.get("/ws/{ws}/wf/{slug}/results/file")
def results_file(ws: str, slug: str, path: str) -> FileResponse:
    _, wd, _ = _ctx(ws, slug)
    target = safe_join(Path(wd, "results"), path)
    if not target.is_file():
        raise HTTPException(404, "No such result file")
    return FileResponse(target, filename=target.name)


class ZipRequest(BaseModel):
    folders: list[str] = []


@router.post("/ws/{ws}/wf/{slug}/results/zip")
def results_zip(ws: str, slug: str, body: ZipRequest) -> FileResponse:
    spec, wd, _ = _ctx(ws, slug)
    files = _results_files(wd, spec.download_exclude)
    if body.folders:
        files = [r for r in files if (r.parts[0] if len(r.parts) > 1 else ".") in body.folders]
    if not files:
        raise HTTPException(404, "No results to download yet. Run the workflow first.")
    out = Path(wd, "downloads", "results.zip")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            z.write(Path(wd, "results", rel), Path("results", rel))
    return FileResponse(out, filename=f"{wd.name}-results.zip", media_type="application/zip")


@router.get("/ws/{ws}/wf/{slug}/table")
def table(
    ws: str,
    slug: str,
    path: str,
    offset: int = 0,
    limit: int = 50,
    sort: str | None = None,
    desc: bool = False,
    q: str | None = None,
) -> dict:
    """One page of a tabular file in the workflow dir, sorted and filtered server-side."""
    _, wd, _ = _ctx(ws, slug)
    target = safe_join(wd, path)
    if not target.is_file():
        raise HTTPException(404, "File not found. Run the workflow first.")
    return read_table_page(target, offset, limit, sort, desc, q)


class RowsRequest(BaseModel):
    path: str
    rows: list[int]
    columns: list[str] | None = None


@router.post("/ws/{ws}/wf/{slug}/table/rows")
def table_rows(ws: str, slug: str, body: RowsRequest) -> dict:
    """Selected rows by original row index, e.g. to plot a selection."""
    from ..tables import read_rows

    _, wd, _ = _ctx(ws, slug)
    return read_rows(safe_join(wd, body.path), body.rows, body.columns)
