"""Counts per sample: one horizontal bar per sample of a chosen count
(identifications, quantified entries, ...), coloured by condition.

Insight component: ``SeriesPlot`` (bars). Columns: ``Sample``, ``Condition``
and the count shown, named by ``metric``.
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"


def settings(metric: str, sample: str = "Sample", condition: str = "Condition", **overrides) -> dict:
    """Constructor arguments for bars of ``metric`` per sample."""
    return dict(
        x_column=sample, y_column=metric, series_column=condition, mode="bars", orientation="h",
        x_label=sample, y_label=metric, y_range_mode="nonnegative",
    ) | overrides
