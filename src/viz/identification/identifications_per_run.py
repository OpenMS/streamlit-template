"""Identifications per run: bars of the entities (proteins, proteoforms,
peptides) each run of a comparison identified and those matched into it from
other runs, side by side.

Insight component: ``SeriesPlot`` (bars). Columns: ``sample``, ``status``
(``detected``, ``matched, identified``, ``matched``) and ``count``.
"""

from __future__ import annotations

import polars as pl

COMPONENT = "SeriesPlot"

# Detected by the run, matched with and without an identification of the run
HOW_COLORS = {"detected": "#3157e9", "matched, identified": "#7f9cf5", "matched": "#ff7501"}


def settings(counts: pl.DataFrame, noun: str, sample_noun: str = "Run", **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``."""
    shown = [how for how in HOW_COLORS
             if how == "detected" or counts.filter(counts["status"] == how)["count"].sum()]
    data = (
        counts.filter(pl.col("status").is_in(shown)).select("sample", "status", "count")
        .with_columns(pl.format("{}: {} {}", "status", "count", pl.lit(noun)).alias("hover"))
    )
    return dict(
        data=data, x_column="sample", y_column="count", series_column="status", series_colors=HOW_COLORS,
        mode="bars", hover_column="hover", title=f"{noun.capitalize()} per {sample_noun.lower()}",
        x_label=sample_noun, y_label=noun.capitalize(),
    ) | overrides
