"""Variation between replicates: a box per condition of the coefficients of
variation of its entries, the median of each in the title; the picked entry's
CV marked on every box.

Insight component: ``SeriesPlot`` (boxes). Columns: ``condition``, ``cv`` (%)
and, for the mark, the entry's identifier column.
"""

from __future__ import annotations

import polars as pl

from src.viz.plumbing import median
from src.viz.series import thin

COMPONENT = "SeriesPlot"


def settings(frame: pl.DataFrame, colors: dict, selection: str = "entry", id_column: str = "ConsensusIndex",
             **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``; the entry
    picked under ``selection`` (its ``id_column``) is marked on the boxes."""
    medians = [
        f"{condition} {median(frame.filter(frame['condition'] == condition)['cv'].to_list()):.0f}%"
        for condition in sorted(set(frame["condition"].to_list()))
    ]
    marks = {}
    if id_column in frame.columns:
        marks = dict(highlight={selection: id_column}, highlight_data=frame.select(id_column, "condition", "cv"))
    return dict(
        **marks,
        data=thin(frame.select("condition", "cv").sort("condition"), ["condition"], "cv"),
        x_column="condition", y_column="cv", series_column="condition", series_colors=colors, mode="box",
        show_legend=False, title=f"Variation between replicates (CV), median {', '.join(medians)}",
        x_label="Condition", y_label="CV (%)", y_range_mode="nonnegative",
    ) | overrides
