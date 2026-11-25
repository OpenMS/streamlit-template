"""Reporter ion ratios: a box per isobaric label of the log2 ratio of its
reporter ion to the reference label's in the same spectrum (0 is equal
intensity).

Insight component: ``SeriesPlot`` (boxes). Input: ``ratios`` (``channel``,
``log2_ratio``) and the labels as (channel, sample) pairs.
"""

from __future__ import annotations

import polars as pl

from src.viz.series import thin

COMPONENT = "SeriesPlot"
_SCHEMA = {"label": pl.Utf8, "log2_ratio": pl.Float64}


def settings(ratios: pl.DataFrame, reference: str, samples, **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``."""
    parts = [
        pl.DataFrame({"label": f"{channel} ({sample})", "log2_ratio": values}, schema=_SCHEMA)
        for channel, sample in samples
        if len(values := ratios.filter(ratios["channel"] == channel)["log2_ratio"].drop_nulls())
    ]
    data = pl.concat(parts) if parts else pl.DataFrame(schema=_SCHEMA)
    return dict(
        data=thin(data, ["label"], "log2_ratio"), x_column="label", y_column="log2_ratio", mode="box",
        series_colors=None, show_legend=False, title=f"Ratio to label {reference} in the same spectrum",
        x_label="Label (sample)", y_label=f"log2 (label / {reference})", y_range_mode="normal",
    ) | overrides
