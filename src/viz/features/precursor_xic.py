"""Precursor XIC by charge: the precursor mass of the selected fragmentation
spectrum traced over the MS1 spectra, one line per charge and their sum.

Insight component: ``SeriesPlot``. Columns: ``rt``, ``intensity``,
``series`` (a charge, or "All charges"), ``scan_idx`` (the fragmentation
spectrum).
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"


def settings(spectrum: str = "scan", **overrides) -> dict:
    """Constructor arguments."""
    return dict(
        filters={spectrum: "scan_idx"},
        x_column="rt", y_column="intensity", series_column="series",
        series_names={"All charges": "All charges"}, mode="lines+markers",
        title="Precursor XIC by Charge", x_label="Retention time (s)", y_label="Intensity",
        svg_filename="precursor-xic",
    ) | overrides
