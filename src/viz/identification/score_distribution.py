"""Identification scores: the score distribution of the identified
proteoforms, targets and, when the search kept them, decoys.

Insight component: ``SeriesPlot``. Columns: ``x`` (score), ``y`` (density),
``kind`` (``target`` or ``decoy``).
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"


def settings(kinds: int = 1, **overrides) -> dict:
    """Constructor arguments; a legend only when decoys are there too
    (``kinds`` > 1)."""
    return dict(
        x_column="x", y_column="y", series_column="kind",
        series_names={"target": "Targets", "decoy": "Decoys"},
        series_colors={"target": "green", "decoy": "red"},
        mode="lines", title="Identification Scores", x_label="Score", y_label="Density",
        show_legend=kinds > 1, fixed_y_range=True, svg_filename="identification-scores",
        float_precision="float64",
    ) | overrides
