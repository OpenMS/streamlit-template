"""Consensus feature map: every consensus feature of a comparison by
retention time and mass, coloured by the number of runs that detected it. A
click picks the feature.

Insight component: ``Heatmap``. Columns: ``RowIndex``, ``rt`` (min), ``mass``
(Da) and ``Detected`` (runs).
"""

from __future__ import annotations

COMPONENT = "Heatmap"


def settings(sample_noun: str = "Run", selection: str = "feature", **overrides) -> dict:
    """Constructor arguments, the data left out."""
    runs = f"{sample_noun.lower()}s"
    return dict(
        x_column="rt", y_column="mass", intensity_column="Detected", log_scale=False,
        interactivity={selection: "RowIndex"}, highlight={selection: "RowIndex"},
        title=f"Consensus features (colour: {runs} that detected them)",
        x_label="Retention time (min)", y_label="Monoisotopic mass (Da)",
        intensity_label=f"Detected in ({runs})", colorscale="Viridis",
    ) | overrides


def rows(overview):
    """The features that have both a mass and a retention time."""
    import polars as pl
    return overview.filter(pl.col("rt").is_not_null() & pl.col("mass").is_not_null())
