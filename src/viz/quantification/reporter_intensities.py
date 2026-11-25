"""Reporter ion intensity: a box per isobaric label of the log2 intensity of
its reporter ions over the labelled spectra, coloured by the condition of its
sample; the share of spectra carrying the ion is part of the label.

Insight component: ``SeriesPlot`` (boxes). Input: ``presence`` (``channel``,
``sample``, ``present`` in %) and ``ions`` (``channel``, ``intensity``).
"""

from __future__ import annotations

import polars as pl

from src.viz.series import thin

COMPONENT = "SeriesPlot"
NO_CONDITION = "#9E9E9E"
_SCHEMA = {"label": pl.Utf8, "log2_intensity": pl.Float64, "condition": pl.Utf8}


def settings(presence: pl.DataFrame, ions: pl.DataFrame, colors: dict, conditions: dict, **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``."""
    parts = []
    for row in presence.iter_rows(named=True):
        channel, sample = row["channel"], row["sample"] or row["channel"]
        values = ions.filter(ions["channel"] == channel)["intensity"].drop_nulls()
        values = values.filter(values > 0)
        parts.append(pl.DataFrame({
            "label": f"{channel} ({sample}) · {row['present']:.0f}%",
            "log2_intensity": values.log(2),
            "condition": conditions.get(sample, "no condition"),
        }, schema=_SCHEMA))
    data = pl.concat(parts) if parts else pl.DataFrame(schema=_SCHEMA)
    return dict(
        data=thin(data, ["label"], "log2_intensity"), x_column="label", y_column="log2_intensity",
        series_column="condition", series_colors={**colors, "no condition": NO_CONDITION}, mode="box",
        title="Reporter ion intensity per label (share of spectra with the ion)",
        x_label="Label (sample)", y_label="log2 intensity", y_range_mode="normal",
    ) | overrides
