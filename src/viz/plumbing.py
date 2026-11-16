"""What every panel of the library uses: content fingerprints for cache ids,
capability checks on the installed openms-insight, the zoom argument a view
keeps, a component loaded from its cache or built, and group colours.

openms_insight is imported where a component is built, never at module level:
it is a dependency of the apps, not of the template.
"""

from __future__ import annotations

import hashlib
import inspect
import threading
from pathlib import Path
from typing import Callable

import pandas as pd
import polars as pl

# Insight's own default colours for groups (PCA, clustered heatmap), in the
# order of the sorted group names, so every panel colours a group the same way
GROUP_PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def group_colors(groups) -> dict[str, str]:
    """group -> colour, by the sorted group names."""
    names = sorted({str(g) for g in groups if g is not None})
    return {g: GROUP_PALETTE[i % len(GROUP_PALETTE)] for i, g in enumerate(names)}


def as_polars(data) -> pl.DataFrame:
    """A polars frame of ``data`` (pandas, polars or a LazyFrame)."""
    if isinstance(data, pl.LazyFrame):
        return data.collect()
    if isinstance(data, pd.DataFrame):
        return pl.from_pandas(data)
    return data


def fingerprint(data, *parts) -> str:
    """A short hash of a table's content and of ``parts`` (settings)."""
    digest = hashlib.sha1(repr(parts).encode())
    if data is not None:
        frame = as_polars(data)
        digest.update(repr((frame.columns, frame.shape)).encode())
        if frame.height:
            # The row hashes in order: a sum would give tables with the same
            # rows in another order (a different plot) the same fingerprint
            digest.update(frame.hash_rows(seed=0).to_numpy().tobytes())
    return digest.hexdigest()[:16]


def accepts(cls, argument: str, method: str = "__init__") -> bool:
    """True when the installed openms-insight's ``cls.method`` takes ``argument``."""
    try:
        return argument in inspect.signature(getattr(cls, method)).parameters
    except (TypeError, ValueError, AttributeError):
        return False


def only_accepted(cls, **arguments) -> dict:
    """The ``arguments`` the installed openms-insight's ``cls`` takes; the rest
    (options of a newer release) are left out."""
    return {k: v for k, v in arguments.items() if accepts(cls, k)}


def zoom_args(cls, zoom: str | None) -> dict:
    """``zoom_identifier=zoom`` for a plot that keeps its zoom in the state,
    when its class takes one. The caller names the identifier (the layout
    manager's ``zoom_identifier(name)``): the library imports nothing above it."""
    if not zoom:
        return {}
    return {"zoom_identifier": zoom} if accepts(cls, "zoom_identifier") else {}


def _lock(cache_path, cache_id) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(f"{cache_path}/{cache_id}", threading.Lock())


def component(cls, cache_path, cache_id: str, build: Callable[[], dict], **fixed):
    """The Insight component ``cache_id``: loaded from its cache, or built with
    the keyword arguments ``build()`` returns (``fixed`` go to both).

    ``build`` is called only when the cache is missing, so a source whose
    tables are costly to read does it there and names its cache by what they
    are made from.
    """
    from openms_insight.core.cache import CacheMissError

    cache_path = str(Path(cache_path))
    try:
        return cls(cache_id=cache_id, cache_path=cache_path, **fixed)
    except CacheMissError:
        pass
    with _lock(cache_path, cache_id):
        # Another tab may have built it while this one waited
        try:
            return cls(cache_id=cache_id, cache_path=cache_path, **fixed)
        except CacheMissError:
            pass
        return cls(cache_id=cache_id, cache_path=cache_path, **fixed, **build())


def cache_name(name: str, data, *settings) -> str:
    """``<name>-<hash of data and settings>``: a cache id that changes with what is drawn."""
    return f"{name}-{fingerprint(data, *settings)}"


def median(values):
    """The median of ``values``, None for none."""
    values = sorted(values)
    n = len(values)
    if not n:
        return None
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
