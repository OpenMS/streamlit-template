"""Precursor mass error: how many target matches (PSMs) after the FDR filter
have each precursor mass error, isotope errors removed. A peak off 0 points to
a calibration offset; a wide one to a precursor tolerance wider than needed.

Insight component: ``SeriesPlot``. Columns: ``x`` (error, ppm), ``y`` (count).
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"


def settings(noun: str = "PSMs", **overrides) -> dict:
    return dict(
        x_column="x", y_column="y", mode="lines", series_colors=None, show_legend=False,
        y_range_mode="nonnegative", title="Precursor mass error",
        x_label="Precursor error (ppm)", y_label=noun, svg_filename="precursor-mass-error",
    ) | overrides
