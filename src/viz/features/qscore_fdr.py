"""Score distribution of the masses: the density of the quality scores of
target and decoy masses, from which the mass-level FDR is estimated.

Insight component: ``SeriesPlot``. Columns: ``x`` (QScore), ``y`` (density),
``kind`` (target or decoy).
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"


def settings(**overrides) -> dict:
    """Constructor arguments."""
    return dict(
        x_column="x", y_column="y", series_column="kind",
        series_names={"target": "Target QScores", "decoy": "Decoy QScores"},
        series_colors={"target": "green", "decoy": "red"},
        mode="lines+markers", title="FDR Plot", x_label="QScore", y_label="Density",
        fixed_y_range=True, svg_filename="FDR-plot",
        font={"family": "Arial"}, float_precision="float64",
    ) | overrides
