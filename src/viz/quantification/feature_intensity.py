"""Feature intensity: a box per run of the log2 intensity of the features it
detected and of those matched into it from other runs; the picked feature is
marked in every run.

Insight component: ``SeriesPlot`` (boxes). Columns: ``RowIndex`` (the
feature), ``Run``, ``log2_intensity`` and ``Found`` (``detected``,
``matched``, ``missing``).
"""

from __future__ import annotations

import polars as pl

from src.viz.series import thin

COMPONENT = "SeriesPlot"

FOUND_COLORS = {"detected": "#3157e9", "matched": "#ff7501", "missing": "#9E9E9E"}


def settings(values: pl.DataFrame, samples: list, sample_noun: str = "Run", selection: str = "feature",
             **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``; the feature
    picked under ``selection`` is marked."""
    order = {s: i for i, s in enumerate(samples)}
    data = (
        values.filter(pl.col("Found").is_in(["detected", "matched"]))
        .select("RowIndex", "Run", "log2_intensity", "Found")
        .sort(pl.col("Run").replace_strict(order, default=len(order)))
    )
    return dict(
        highlight={selection: "RowIndex"}, highlight_data=data,
        data=thin(data.drop("RowIndex"), ["Run", "Found"], "log2_intensity"), x_column="Run",
        y_column="log2_intensity", series_column="Found", series_colors=FOUND_COLORS, mode="box",
        title=f"Feature intensity per {sample_noun.lower()}", x_label=sample_noun, y_label="log2 intensity",
        y_range_mode="normal",
    ) | overrides
