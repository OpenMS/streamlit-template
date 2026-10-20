"""
The "pyOpenMS Workflow" and "Others" sections: workspace mzML files, the raw
data viewer, the example mzML workflow, the simple workflow, the subprocess
example, workspace parameters (default-parameters.json) and documentation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import zipfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyopenms as poms
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core import ROOT, human_size, is_safe_name, safe_join, workspace_path

router = APIRouter()


def _mzml_dir(ws: str) -> Path:
    d = workspace_path(ws) / "mzML-files"
    d.mkdir(exist_ok=True)
    return d


def _mzml_files(ws: str) -> list[dict]:
    d = _mzml_dir(ws)
    out = [
        {"name": f.stem, "path": str(f), "size": human_size(f.stat().st_size), "reference": False}
        for f in sorted(d.glob("*.mzML"))
    ]
    ext = d / "external_files.txt"
    if ext.exists():
        for line in ext.read_text().splitlines():
            line = line.strip()
            if line and os.path.exists(line):
                out.append({"name": Path(line).stem, "path": line, "size": human_size(Path(line).stat().st_size), "reference": True})
    return out


def _resolve_mzml(ws: str, name: str) -> Path:
    for f in _mzml_files(ws):
        if f["name"] == name:
            return Path(f["path"])
    raise HTTPException(404, f"No mzML file {name!r} in this workspace")


# ------------------------------------------------------------- workspace params


@router.get("/ws/{ws}/params")
def get_params(ws: str) -> dict:
    path = workspace_path(ws) / "params.json"
    source = path if path.exists() else ROOT / "default-parameters.json"
    with open(source, encoding="utf-8") as f:
        return json.load(f)


class Params(BaseModel):
    values: dict[str, Any]


@router.put("/ws/{ws}/params")
def put_params(ws: str, body: Params) -> dict:
    """Same rule as save_params(): only keys of default-parameters.json are kept."""
    params = get_params(ws)
    for k, v in body.values.items():
        if k in params:
            params[k] = v
    with open(workspace_path(ws) / "params.json", "w", encoding="utf-8") as f:
        json.dump(params, f, indent=4)
    return params


# ------------------------------------------------------------------- mzML files


@router.get("/ws/{ws}/mzml")
def list_mzml(ws: str) -> dict:
    return {"files": _mzml_files(ws)}


@router.post("/ws/{ws}/mzml")
async def upload_mzml(ws: str, files: list[UploadFile] = File(...)) -> dict:
    d = _mzml_dir(ws)
    added = []
    for up in files:
        name = Path(up.filename or "").name
        if not is_safe_name(name) or not name.endswith(".mzML"):
            continue
        with open(d / name, "wb") as fh:
            while chunk := await up.read(1 << 20):
                fh.write(chunk)
        added.append(name)
    return {"added": added, "files": _mzml_files(ws)}


class LocalPaths(BaseModel):
    paths: list[str]
    copy_files: bool = True


@router.post("/ws/{ws}/mzml/local")
def add_local_mzml(ws: str, body: LocalPaths) -> dict:
    d = _mzml_dir(ws)
    picked: list[Path] = []
    for raw in body.paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            picked += sorted(p.glob("*.mzML"))
        elif p.suffix == ".mzML" and p.exists():
            picked.append(p)
    if not picked:
        raise HTTPException(400, "No mzML files found.")
    for p in picked:
        if body.copy_files:
            shutil.copy(p, d / p.name)
        else:
            with open(d / "external_files.txt", "a") as fh:
                fh.write(f"{p}\n")
    return {"added": [p.name for p in picked], "files": _mzml_files(ws)}


@router.post("/ws/{ws}/mzml/example")
def load_example_mzml(ws: str) -> dict:
    d = _mzml_dir(ws)
    for f in sorted((ROOT / "example-data" / "mzML").glob("*.mzML")):
        shutil.copy(f, d / f.name)
    return {"files": _mzml_files(ws)}


@router.delete("/ws/{ws}/mzml")
def delete_mzml(ws: str, name: str | None = None) -> dict:
    d = _mzml_dir(ws)
    if name is None:
        shutil.rmtree(d)
        d.mkdir()
    else:
        target = safe_join(d, f"{name}.mzML")
        if target.exists():
            target.unlink()
        ext = d / "external_files.txt"
        if ext.exists():
            keep = [l for l in ext.read_text().splitlines() if l.strip() and Path(l.strip()).stem != name]
            ext.write_text("".join(f"{l}\n" for l in keep)) if keep else ext.unlink()
    return {"files": _mzml_files(ws)}


# --------------------------------------------------------------------- viewer

_exp_cache: "OrderedDict[tuple[str, float], poms.MSExperiment]" = OrderedDict()


def _experiment(path: Path) -> poms.MSExperiment:
    key = (str(path), path.stat().st_mtime)
    if key not in _exp_cache:
        exp = poms.MSExperiment()
        poms.MzMLFile().load(str(path), exp)
        exp.sortSpectra(True)
        _exp_cache[key] = exp
        while len(_exp_cache) > 4:
            _exp_cache.popitem(last=False)
    _exp_cache.move_to_end(key)
    return _exp_cache[key]


def _f(x) -> float | None:
    x = float(x)
    return None if np.isnan(x) else x


@router.get("/ws/{ws}/mzml/{name}/overview")
def mzml_overview(ws: str, name: str) -> dict:
    """Spectrum table and TIC/BPC per MS level (as view_bpc_tic and view_spectrum)."""
    exp = _experiment(_resolve_mzml(ws, name))
    spectra, chrom = [], {}
    for i, spec in enumerate(exp):
        mz, inty = spec.get_peaks()
        if len(mz) == 0:
            continue
        level = spec.getMSLevel()
        precs = spec.getPrecursors()
        apex = int(np.argmax(inty))
        spectra.append(
            {
                "index": i,
                "RT": round(spec.getRT(), 4),
                "MS level": level,
                "precursor m/z": round(precs[0].getMZ(), 4) if precs else None,
                "max intensity m/z": round(float(mz[apex]), 4),
                "peaks": int(len(mz)),
                "TIC": _f(inty.sum()),
            }
        )
        c = chrom.setdefault(level, {"rt": [], "tic": [], "bpc": []})
        c["rt"].append(spec.getRT())
        c["tic"].append(_f(inty.sum()))
        c["bpc"].append(_f(inty.max()))
    return {"spectra": spectra, "chromatograms": {str(k): v for k, v in chrom.items()}}


@router.get("/ws/{ws}/mzml/{name}/spectrum/{index}")
def mzml_spectrum(ws: str, name: str, index: int) -> dict:
    exp = _experiment(_resolve_mzml(ws, name))
    if not 0 <= index < exp.size():
        raise HTTPException(404, "No such spectrum")
    spec = exp[index]
    mz, inty = spec.get_peaks()
    precs = spec.getPrecursors()
    return {
        "index": index,
        "rt": spec.getRT(),
        "ms_level": spec.getMSLevel(),
        "precursor_mz": precs[0].getMZ() if precs else None,
        "mz": mz.astype(float).tolist(),
        "intensity": inty.astype(float).tolist(),
    }


@router.get("/ws/{ws}/mzml/{name}/peakmap")
def mzml_peakmap(
    ws: str,
    name: str,
    ms_level: int = 1,
    rt_min: float | None = None,
    rt_max: float | None = None,
    mz_min: float | None = None,
    mz_max: float | None = None,
    intensity_cutoff: float = 0,
    rt_bins: int = 400,
    mz_bins: int = 400,
) -> dict:
    """
    Peak map binned server-side to at most rt_bins x mz_bins points (max
    intensity per bin), so a full LC-MS run never ships every peak.
    """
    exp = _experiment(_resolve_mzml(ws, name))
    rts, mzs, ints = [], [], []
    for spec in exp:
        if spec.getMSLevel() != ms_level:
            continue
        rt = spec.getRT()
        if (rt_min is not None and rt < rt_min) or (rt_max is not None and rt > rt_max):
            continue
        mz, inty = spec.get_peaks()
        mask = inty >= intensity_cutoff
        if mz_min is not None:
            mask &= mz >= mz_min
        if mz_max is not None:
            mask &= mz <= mz_max
        n = int(mask.sum())
        if n:
            rts.append(np.full(n, rt))
            mzs.append(mz[mask])
            ints.append(inty[mask])
    if not rts:
        return {"rt": [], "mz": [], "intensity": [], "total_peaks": 0}
    rt = np.concatenate(rts)
    mz = np.concatenate(mzs).astype(float)
    inty = np.concatenate(ints).astype(float)
    total = len(rt)
    rt_edges = np.linspace(rt.min(), rt.max() + 1e-9, rt_bins + 1)
    mz_edges = np.linspace(mz.min(), mz.max() + 1e-9, mz_bins + 1)
    ri = np.clip(np.digitize(rt, rt_edges) - 1, 0, rt_bins - 1)
    mi = np.clip(np.digitize(mz, mz_edges) - 1, 0, mz_bins - 1)
    df = pd.DataFrame({"bin": ri * mz_bins + mi, "rt": rt, "mz": mz, "intensity": inty})
    top = df.loc[df.groupby("bin")["intensity"].idxmax()].sort_values("intensity")
    return {
        "rt": top["rt"].round(4).tolist(),
        "mz": top["mz"].round(5).tolist(),
        "intensity": top["intensity"].tolist(),
        "total_peaks": int(total),
    }


# -------------------------------------------------- example mzML workflow


class ExampleRun(BaseModel):
    files: list[str]


@router.post("/ws/{ws}/example-workflow")
def run_example_workflow(ws: str, body: ExampleRun) -> dict:
    """content/run_example_workflow.py: number of spectra per selected file."""
    if not body.files:
        raise HTTPException(400, "Select some mzML files.")
    put_params(ws, Params(values={"example-workflow-selected-mzML-files": body.files}))
    result_dir = workspace_path(ws) / "mzML-workflow-results" / datetime.now().strftime("%Y-%m-%d %H_%M_%S")
    result_dir.mkdir(parents=True, exist_ok=True)
    counts = []
    for name in body.files:
        exp = poms.MSExperiment()
        poms.MzMLFile().load(str(_resolve_mzml(ws, name)), exp)
        counts.append(exp.size())
    pd.DataFrame({"filenames": body.files, "number of spectra": counts}).to_csv(
        result_dir / "result.tsv", sep="\t", index=False
    )
    return {"run": result_dir.name}


def _results_root(ws: str) -> Path:
    return workspace_path(ws) / "mzML-workflow-results"


@router.get("/ws/{ws}/example-workflow/results")
def example_results(ws: str) -> dict:
    root = _results_root(ws)
    runs = sorted((d.name for d in root.iterdir() if d.is_dir()), reverse=True) if root.exists() else []
    return {"runs": runs}


@router.get("/ws/{ws}/example-workflow/results/{run}")
def example_result(ws: str, run: str) -> dict:
    path = safe_join(_results_root(ws), run) / "result.tsv"
    if not path.exists():
        raise HTTPException(404, "No such result")
    df = pd.read_csv(path, sep="\t")
    return {"columns": list(df.columns), "rows": df.values.tolist()}


@router.get("/ws/{ws}/example-workflow/results/{run}/zip")
def example_result_zip(ws: str, run: str) -> FileResponse:
    d = safe_join(_results_root(ws), run)
    if not d.is_dir():
        raise HTTPException(404, "No such result")
    out = d / "output.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in d.iterdir():
            if f.name != "output.zip" and f.is_file():
                z.write(f, f.name)
    return FileResponse(out, filename=f"{run}.zip", media_type="application/zip")


@router.delete("/ws/{ws}/example-workflow/results/{run}")
def delete_example_result(ws: str, run: str) -> dict:
    d = safe_join(_results_root(ws), run)
    if d.is_dir():
        shutil.rmtree(d)
    return example_results(ws)


# --------------------------------------------------------------- others


@router.get("/simple-workflow")
def simple_workflow(x: int = 10, y: int = 5) -> dict:
    """content/simple_workflow.py: a random x by y table."""
    if not (1 <= x <= 20 and 1 <= y <= 20):
        raise HTTPException(400, "Dimensions must be between 1 and 20")
    df = pd.DataFrame(np.random.randn(x, y))
    return {"columns": [str(c) for c in df.columns], "rows": df.values.tolist()}


@router.post("/ws/{ws}/extract-ids/{name}")
def extract_ids(ws: str, name: str) -> dict:
    """content/run_subprocess.py: grep idRef from an mzML file as a subprocess."""
    path = _resolve_mzml(ws, name)
    args = ["findstr", "idRef", str(path)] if os.name == "nt" else ["grep", "idRef", str(path)]
    start = time.time()
    r = subprocess.run(args, capture_output=True, text=True)
    return {
        "command": " ".join(args),
        "success": r.returncode in (0, 1),
        "log": r.stdout[-200_000:] + r.stderr,
        "seconds": round(time.time() - start, 2),
    }


DOCS = [
    ("User Guide", "user_guide.md"),
    ("Installation", "installation.md"),
    ("Developers Guide: How to build app based on this template", "build_app.md"),
    ("Developer Guide: Windows Executables", "win_exe_with_embed_py.md"),
    ("Developers Guide: From Notebook to Web App", "notebook_to_webapp.md"),
    ("Developers Guide: Deployment", "deployment.md"),
    ("Developers Guide: Kubernetes Deployment", "kubernetes-deployment.md"),
    ("Svelte App: Local Web App", "svelte_app.md"),
]


@router.get("/docs")
def docs() -> list[dict]:
    return [{"title": t, "file": f} for t, f in DOCS if (ROOT / "docs" / f).exists()]


@router.get("/docs/{file}")
def doc(file: str) -> dict:
    if file not in {f for _, f in DOCS}:
        raise HTTPException(404, "No such document")
    return {"markdown": (ROOT / "docs" / file).read_text(encoding="utf-8")}
