"""Heatmap of row z-scores in the input order (the most variable or most
significant entries first): red above an entry's mean, blue below, with a
toolbar slider for how many entries it shows.

Contract: a wide table of abundances on a log scale (index: entries,
columns: samples) and, optionally, ``groups``, sample -> group.
"""

from __future__ import annotations

import pandas as pd
import polars as pl

from src.viz.plumbing import fingerprint
from src.viz.quantification.steps import zscores


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
    long = zscore_long(matrix, id_column, top=top, groups=groups,
                       sample_column=settings.get("sample_column", "Sample"),
                       value_column=settings.get("value_column", "Z_score"))
    if long.empty:
        return None
    arguments = heatmap_settings(id_column, toolbar_settings=toolbar, **settings)
    frame = pl.from_pandas(long)
    plot = Heatmap(cache_id=f"{name}-{fingerprint(frame, repr(sorted(arguments.items(), key=lambda kv: kv[0])))}",
                   cache_path=str(cache_path), data=frame.lazy(), **arguments)
    plot(key=key, state_manager=state_manager, height=height, help=help)
    return plot
