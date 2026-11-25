"""Match between runs: a box per run of the match scores of the values matched
into it from other runs, those also identified there and the rejected matches
apart.

Insight component: ``SeriesPlot`` (boxes). Columns: ``sample``, ``score`` and
``outcome`` (``matched, identified``, ``matched``, ``not matched``).
"""

from __future__ import annotations

import polars as pl

from src.viz.series import thin

COMPONENT = "SeriesPlot"

OUTCOME_COLORS = {"matched, identified": "#7f9cf5", "matched": "#ff7501", "not matched": "#9E9E9E"}


def settings(frame: pl.DataFrame, samples: list, sample_noun: str = "Run", **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``, the runs in
    the order of ``samples``."""
    order = {s: i for i, s in enumerate(samples)}
    data = frame.select("sample", "score", "outcome").sort(
        pl.col("sample").replace_strict(order, default=len(order)))
    return dict(
        data=thin(data, ["sample", "outcome"], "score"), x_column="sample", y_column="score",
        series_column="outcome", series_colors=OUTCOME_COLORS, mode="box", title="Match between runs: match score",
        x_label=sample_noun, y_label="Match score", y_range_mode="normal",
    ) | overrides
