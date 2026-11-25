"""Annotated spectrum: the measured spectrum of the picked PSM with the
fragment ions its sequence view matched marked and labelled. Built from the
sequence view with ``LinePlot.from_sequence_view``.

Insight component: ``LinePlot``. Columns: those of the sequence view's peaks.
"""

from __future__ import annotations

import math

from src.viz.plumbing import accepts

COMPONENT = "LinePlot"


def settings(styling=None, title: str = "Annotated Spectrum", **overrides) -> dict:
    """Arguments of ``LinePlot.from_sequence_view`` after the sequence view."""
    return dict(title=title, **({"styling": styling} if styling else {})) | overrides


def precursor_marker(cls, mz, charge=None) -> dict:
    """Arguments for the spectrum plot ``cls`` that mark the precursor m/z: a
    dotted guide labelled with its charge ("precursor 2+"), drawn whether or
    not a peak is there and kept in the image download.

    ``{}`` without a usable m/z, or when the installed Insight ``cls`` has no
    ``x_markers``. ``predicted_spectrum`` uses the same for its MirrorPlot.
    """
    try:
        mz = float(mz)
    except (TypeError, ValueError):
        return {}
    if not math.isfinite(mz) or mz <= 0 or not accepts(cls, "x_markers"):
        return {}
    try:
        label = f"precursor {int(charge)}+" if int(charge) > 0 else "precursor"
    except (TypeError, ValueError):
        label = "precursor"
    return {"x_markers": [{"x": mz, "label": label}]}
