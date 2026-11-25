"""Identification QC: small plots of a run's identifications: PrSMs per
minute over retention time, sequence coverage and the median fragment mass
error over retention time.

Insight component: ``SeriesPlot``, one per plot. Columns: ``x``, ``y``,
``series``.
"""

from __future__ import annotations

from src.viz.features.run_qc import plot_settings

COMPONENT = "SeriesPlot"

# name: (title, x label, y label, mode, y range)
PLOTS = {
    "qc_identifications": ("Identifications over Time", "Retention time (s)", "PrSMs per minute",
                           "lines+markers", "nonnegative"),
    "qc_coverage": ("Sequence Coverage", "Sequence coverage (%)", "PrSMs", "lines+markers", "nonnegative"),
    "qc_fragment_error": ("Fragment Mass Error over Time", "Retention time (s)", "Median error (ppm)",
                          "markers", "normal"),
}


def settings(name: str, series_count: int = 1, **overrides) -> dict:
    """Constructor arguments of the identification QC plot ``name``."""
    return plot_settings(*PLOTS[name], series_count=series_count, name=name, **overrides)
