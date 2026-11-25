"""Identification frequency: grouped bars of the entities found in 1, 2 ...
all runs of a comparison, detected by the run alone and detected or matched.

Insight component: ``SeriesPlot`` (bars). Columns: ``runs`` (how many runs),
``detected`` and ``found`` (counts).
"""

from __future__ import annotations

import polars as pl

from src.viz.identification.identifications_per_run import HOW_COLORS

COMPONENT = "SeriesPlot"


def settings(table: pl.DataFrame, noun: str, sample_noun: str = "Run", **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``."""
    data = (
        table.select(pl.col("runs").cast(pl.Utf8), "detected", "found")
        .unpivot(index="runs", variable_name="how", value_name="count")
    )
    return dict(
        data=data, x_column="runs", y_column="count", series_column="how",
        series_names={"detected": "detected", "found": "detected or matched"},
        series_colors={"detected": HOW_COLORS["detected"], "found": HOW_COLORS["matched"]},
        mode="bars", title=f"{noun.capitalize()} found in how many {sample_noun.lower()}s",
        x_label=f"{sample_noun}s", y_label=noun.capitalize(),
    ) | overrides
