"""Total intensity: bars of the summed intensity of every run (sample) of a
comparison, coloured by condition, the median in the title.

Insight component: ``SeriesPlot`` (bars). Columns: ``sample``, ``total``,
``quantified`` (entries with a value) and ``relative`` (share of the median).
"""

from __future__ import annotations

import polars as pl

from src.viz.plumbing import median

COMPONENT = "SeriesPlot"
NO_CONDITION = "#9E9E9E"


def settings(frame: pl.DataFrame, colors: dict, conditions: dict, sample_noun: str = "Run", **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``; ``conditions``
    maps a sample to its condition, ``colors`` a condition to its colour."""
    middle = median([t for t in frame["total"].to_list() if t > 0])
    data = frame.with_columns(
        pl.col("sample").replace_strict(conditions, default="no condition").alias("condition"),
        pl.format(
            "{}: total {}, {} quantified, {}% of the median", "sample",
            pl.col("total").round_sig_figs(3), "quantified", (pl.col("relative").fill_null(0) * 100).round(0),
        ).alias("hover"),
    ).select("sample", "total", "condition", "hover")
    title = f"Total intensity per {sample_noun.lower()}"
    if middle is not None:
        title += f" (median {middle:.3g})"
    return dict(
        data=data, x_column="sample", y_column="total", series_column="condition",
        series_colors={**colors, "no condition": NO_CONDITION}, mode="bars", hover_column="hover",
        title=title, x_label=sample_noun, y_label="Summed intensity",
    ) | overrides
