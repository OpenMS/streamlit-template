"""Chromatogram: total ion current, base peak and deconvolved intensity of
one MS level over retention time. A click selects the spectrum.

Insight component: ``SeriesPlot``. Columns: ``x`` (retention time, s), ``y``
(intensity), ``series`` (the trace), ``index`` (the spectrum).
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"

COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c"]


def settings(series: list[str], level: int = 1, spectrum: str = "scan", **overrides) -> dict:
    """Constructor arguments for the traces named ``series``, in this order."""
    return dict(
        interactivity={spectrum: "index"},
        x_column="x", y_column="y", series_column="series",
        series_names={name: name for name in series},
        series_colors=dict(zip(series, COLORS)),
        mode="lines", y_range_mode="nonnegative",
        title=f"Chromatogram (MS{level})", x_label="Retention time (s)",
        y_label="Intensity", svg_filename="chromatogram",
    ) | overrides
