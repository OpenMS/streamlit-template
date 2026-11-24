"""Consensus feature table: every consensus feature of a comparison with its
mass, retention time, charges, how many runs detected it, matched it or miss
it, and its proteoform. A click picks the feature.

Insight component: ``Table``. Columns: ``RowIndex``, ``label`` (else ``id``),
``mass``, ``rt``, ``MinCharge``/``MaxCharge``, ``Detected``, ``Matched``,
``Missing`` and ``proteoform``.
"""

from __future__ import annotations

import polars as pl

from src.viz.columns import RECLICK, fixed

COMPONENT = "Table"


def columns(sample_noun: str = "Run") -> list[dict]:
    """The column definitions."""
    return [
        {"title": "Feature", "field": "label", "sorter": "string"},
        {"title": "Mass (Da)", "field": "mass", "sorter": "number", **fixed(2)},
        {"title": "RT (min)", "field": "rt", "sorter": "number", **fixed(2)},
        {"title": "Charges", "field": "charges", "sorter": "string"},
        {"title": "Detected", "field": "Detected", "sorter": "number",
         "headerTooltip": f"{sample_noun}s that detected it themselves."},
        {"title": "Matched", "field": "Matched", "sorter": "number",
         "headerTooltip": f"{sample_noun}s it was matched into (match between runs)."},
        {"title": "Missing", "field": "Missing", "sorter": "number"},
        {"title": "Proteoform", "field": "proteoform", "sorter": "string"},
    ]


def rows(frame: pl.DataFrame) -> pl.DataFrame:
    """``frame`` with the ``charges`` (``2`` or ``2–5``) and ``label`` columns
    the table shows."""
    if "MinCharge" in frame.columns and "MaxCharge" in frame.columns:
        frame = frame.with_columns(
            pl.when(pl.col("MinCharge") == pl.col("MaxCharge")).then(pl.col("MinCharge").cast(pl.Utf8))
            .otherwise(pl.col("MinCharge").cast(pl.Utf8) + "–" + pl.col("MaxCharge").cast(pl.Utf8))
            .alias("charges"),
        )
    else:
        frame = frame.with_columns(pl.lit(None, pl.Utf8).alias("charges"))
    if "label" not in frame.columns:
        frame = frame.with_columns(pl.col("id").alias("label"))
    return frame


def settings(sample_noun: str = "Run", selection: str = "feature", **overrides) -> dict:
    """Constructor arguments, the data left out."""
    return dict(
        column_definitions=columns(sample_noun), index_field="RowIndex", title="Consensus features",
        go_to_fields=["label"], interactivity={selection: "RowIndex"}, reclick=RECLICK, reset_sort=True,
    ) | overrides
