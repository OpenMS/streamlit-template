"""Annotated spectrum: the measured spectrum of the picked PSM with the
fragment ions its sequence view matched marked and labelled. Built from the
sequence view with ``LinePlot.from_sequence_view``.

Insight component: ``LinePlot``. Columns: those of the sequence view's peaks.
"""

from __future__ import annotations

COMPONENT = "LinePlot"


def settings(styling=None, title: str = "Annotated Spectrum", **overrides) -> dict:
    """Arguments of ``LinePlot.from_sequence_view`` after the sequence view."""
    return dict(title=title, **({"styling": styling} if styling else {})) | overrides
