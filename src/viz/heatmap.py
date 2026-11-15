"""Heatmaps of the most variable (or most significant) entries as z-scores per
row, clustered by rows and samples, samples marked by group.

Contract: a wide table with an id column and one column per sample (log
scale), and ``groups``, sample -> group.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl

from src.viz.pca import sample_metadata
from src.viz.plumbing import as_polars, fingerprint, group_colors


def zscores(matrix: pd.DataFrame, top: int | None = None) -> pd.DataFrame:
    """Row z-scores of ``matrix`` (rows: entries, columns: samples), of its
    ``top`` most variable rows when given; rows without a spread are dropped."""
    matrix = matrix.apply(pd.to_numeric, errors="coerce")
    if top is not None:
        matrix = matrix.loc[matrix.var(axis=1).sort_values(ascending=False).head(top).index]
    scores = matrix.sub(matrix.mean(axis=1), axis=0).div(matrix.std(axis=1), axis=0)
    return scores.replace([np.inf, -np.inf], np.nan).dropna()


def clustered_height(rows: int) -> int:
    """Room for the dendrograms and a readable label per row."""
    return max(600, min(1400, 300 + rows * 20))


def clustered_settings(groups: dict, id_column: str, samples=None, *, title: str,
                       x_label: str = "Samples", y_label: str = "Entries",
                       multi_select: dict | None = None) -> dict:
    """The ``ClusteredHeatmap`` arguments (besides data and cache)."""
    metadata = sample_metadata(groups, samples)
    settings = dict(
        id_col=id_column, metadata=metadata, row_cluster=True, col_cluster=True, title=title,
        x_label=x_label, y_label=y_label, intensity_label="Z-score",
        group_colors=group_colors(metadata["group"].to_list()),
    )
    if multi_select:
        settings["multi_select"] = multi_select
    return settings


def show_clustered_heatmap(data, groups: dict, id_column: str, name: str = "clustered-heatmap", *,
                           cache_path, key: str, state_manager=None, height: int | None = None,
                           help: str | None = None, toolbar_settings=None,  # pylint: disable=redefined-builtin
                           **settings):
    """Draw z-scores (``id_column`` and a column per sample) as a clustered heatmap."""
    from openms_insight import ClusteredHeatmap

    frame = as_polars(data)
    arguments = clustered_settings(groups, id_column, **settings)
    stamp = fingerprint(frame, arguments["metadata"].rows(), arguments["title"], arguments["y_label"],
                        sorted(arguments.get("multi_select", {}).items()))
    extra = {"toolbar_settings": toolbar_settings} if toolbar_settings else {}
    plot = ClusteredHeatmap(cache_id=f"{name}-{stamp}", cache_path=str(cache_path), data=frame.lazy(),
                            **arguments, **extra)
    plot(key=key, state_manager=state_manager, height=height or clustered_height(frame.height), help=help)
    return plot


def top_setting(identifier: str = "heatmap_top_n", label: str = "Entries shown (most variable first)",
                minimum: int = 20, maximum: int = 200, step: int = 10, default: int = 50) -> dict:
    """The toolbar slider for how many of the most variable entries a heatmap shows."""
    return {"identifier": identifier, "label": label, "kind": "range",
            "min": minimum, "max": maximum, "step": step, "default": default}


def zscore_long(matrix: pd.DataFrame, id_column: str, top: int | None = None, groups: dict | None = None,
                sample_column: str = "Sample", value_column: str = "Z_score") -> pd.DataFrame:
    """Row z-scores of ``matrix`` (index: entries, columns: samples) as a long
    table: ``id_column``, ``sample_column``, ``value_column`` and, with
    ``groups``, ``Group``."""
    scores = zscores(matrix, top=top)
    scores.index.name = id_column
    long = scores.reset_index().melt(id_vars=[id_column], var_name=sample_column, value_name=value_column)
    if groups:
        long["Group"] = long[sample_column].map(groups)
    return long


def heatmap_settings(id_column: str, *, title: str | None = None, x_label: str = "Samples",
                     y_label: str = "Entries", sample_column: str = "Sample",
                     value_column: str = "Z_score", toolbar_settings=None) -> dict:
    """The ``Heatmap`` arguments for z-scores (besides data and cache): in
    the input order, red above a row's mean, blue below."""
    settings = dict(
        x_column=sample_column, y_column=id_column, intensity_column=value_column,
        x_label=x_label, y_label=y_label, colorscale="RdBu", reversescale=True,
        # Z-scores are negative too
        log_scale=False, intensity_label="Z-score", category_column=None,
        # Every cell of the grid, never a sample of it
        min_points=10000,
    )
    if title:
        settings["title"] = title
    if toolbar_settings:
        settings["toolbar_settings"] = toolbar_settings
    return settings


def show_zscore_heatmap(matrix: pd.DataFrame, id_column: str, name: str = "zscore-heatmap", *,
                        cache_path, key: str, state_manager=None, top: int | dict | None = None,
                        groups: dict | None = None, height: int = 520,
                        help: str | None = None, **settings):  # pylint: disable=redefined-builtin
    """Draw the row z-scores of ``matrix`` (index: entries, columns: samples,
    log scale), unclustered. ``top`` is a number of the most variable rows, or
    a ``top_setting()`` whose toolbar slider picks it. Returns None (drawing
    nothing) when no row has a spread."""
    from openms_insight import Heatmap

    toolbar = None
    if isinstance(top, dict):
        try:
            from openms_insight.core.settings import setting_value  # pylint: disable=no-name-in-module
        except ImportError:  # an openms-insight without toolbar settings: the default count
            top = int(top.get("default", 50))
        else:
            toolbar = [top]
            top = int(setting_value(state_manager, top))
    long = zscore_long(matrix, id_column, top=top, groups=groups)
    if long.empty:
        return None
    arguments = heatmap_settings(id_column, toolbar_settings=toolbar, **settings)
    frame = pl.from_pandas(long)
    plot = Heatmap(cache_id=f"{name}-{fingerprint(frame, repr(sorted(arguments.items(), key=lambda kv: kv[0])))}",
                   cache_path=str(cache_path), data=frame.lazy(), **arguments)
    plot(key=key, state_manager=state_manager, height=height, help=help)
    return plot
