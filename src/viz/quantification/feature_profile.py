"""Picked feature per run: the consensus feature picked in a comparison in
every run, detected, matched or missing, with its intensity.

Insight component: ``Table``. Columns: ``ValueIndex``, ``RowIndex`` (the
feature), ``Run``, ``Found``, ``intensity`` and ``log2_intensity``.
"""

from __future__ import annotations

import polars as pl

from src.viz.columns import fixed

COMPONENT = "Table"
SCIENTIFIC = {"formatter": "scientific", "formatterParams": {"precision": 3}}


def rows(values: pl.DataFrame) -> pl.DataFrame:
    """``values`` (one row per feature and run) with the intensity and a row index."""
    return (
        values.with_columns((2 ** pl.col("log2_intensity")).alias("intensity"))
        .with_row_index("ValueIndex").with_columns(pl.col("ValueIndex").cast(pl.Int64))
    )


def settings(sample_noun: str = "Run", selection: str = "feature", **overrides) -> dict:
    """Constructor arguments, the data left out."""
    return dict(
        column_definitions=[
            {"title": sample_noun, "field": "Run", "sorter": "string"},
            {"title": "Found", "field": "Found", "sorter": "string"},
            {"title": "Intensity", "field": "intensity", "sorter": "number", **SCIENTIFIC},
            {"title": "log2 intensity", "field": "log2_intensity", "sorter": "number", **fixed(2)},
        ],
        index_field="ValueIndex", title=f"Selected feature per {sample_noun.lower()}",
        filters={selection: "RowIndex"}, pagination=False, default_row_selects=False,
    ) | overrides
