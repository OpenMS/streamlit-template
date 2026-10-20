"""
Server-side paginated tables.

Only the visible page leaves the server, the same idea as OpenMS-Insight's
``Table`` (and the reason the template discourages ``st.dataframe`` on large
frames). Frames are cached per file and modification time.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from pathlib import Path

import pandas as pd

_cache: "OrderedDict[tuple[str, float], pd.DataFrame]" = OrderedDict()
_CACHE_SIZE = 8


def load_frame(path: Path) -> pd.DataFrame:
    key = (str(path), path.stat().st_mtime)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    suffix = path.suffix.lower()
    if suffix in (".tsv", ".txt", ".tab"):
        df = pd.read_csv(path, sep="\t")
    elif suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix == ".json":
        df = pd.read_json(path)
    else:
        raise ValueError(f"Unsupported table format: {suffix}")
    _cache[key] = df
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return df


def _jsonable(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if hasattr(v, "item"):
        v = v.item()
        return _jsonable(v) if isinstance(v, float) else v
    return v


def _records(df: pd.DataFrame) -> list[list]:
    return [[_jsonable(v) for v in row] for row in df.itertuples(index=False, name=None)]


def read_table_page(path: Path, offset: int, limit: int, sort: str | None, desc: bool, q: str | None) -> dict:
    df = load_frame(path)
    view = df
    if q:
        mask = pd.Series(False, index=df.index)
        for col in df.columns:
            mask |= df[col].astype(str).str.contains(q, case=False, regex=False, na=False)
        view = df[mask]
    if sort and sort in view.columns:
        view = view.sort_values(sort, ascending=not desc, kind="stable")
    limit = max(1, min(limit, 1000))
    page = view.iloc[offset : offset + limit]
    return {
        "columns": [{"name": str(c), "numeric": bool(pd.api.types.is_numeric_dtype(df[c]))} for c in df.columns],
        "rows": _records(page),
        "row_ids": [int(i) for i in page.index],
        "total": int(len(view)),
        "unfiltered": int(len(df)),
        "offset": offset,
    }


def read_rows(path: Path, rows: list[int], columns: list[str] | None) -> dict:
    df = load_frame(path)
    sel = df.loc[[r for r in rows if r in df.index]]
    if columns:
        sel = sel[[c for c in columns if c in sel.columns]]
    return {"columns": [str(c) for c in sel.columns], "rows": _records(sel), "row_ids": [int(i) for i in sel.index]}
