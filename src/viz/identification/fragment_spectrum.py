"""Fragment spectrum: the peaks of the picked spectrum, those a search
assigned to a fragment ion labelled and coloured by their ion series (a, a-B,
b, c, d, w, x, y, z), the others grey. Clicking a peak, or a fragment in the
fragment table, picks it and draws it gold.

Insight component: ``LinePlot``. Columns: ``peak`` (the peak), ``spectrum``
(the filter), ``mz``, ``intensity`` (relative, %), ``matched`` (bool), ``ion``
(the label, empty when unassigned) and ``color``.
"""

from __future__ import annotations

import re

COMPONENT = "LinePlot"

# One colour per ion series; colour-blind safe (Okabe-Ito order)
ION_COLORS = {
    "a-B": "#0072B2", "a": "#56B4E9", "b": "#009E73", "c": "#E69F00", "d": "#CC79A7",
    "w": "#D55E00", "x": "#F0E442", "y": "#CC0000", "z": "#999999",
}
UNKNOWN_ION_COLOR = "#6B7280"

_BASE_LOSS = re.compile(r"^a(?:\d+)?-B")
_SERIES = re.compile(r"^([abcdwxyz])(?:\d|$|\^|[+-])")


def ion_series(ion: str | None) -> str | None:
    """The series of a fragment label (``a3-B`` is a-B, ``w2^2-`` is w)."""
    text = str(ion or "").strip()
    if not text:
        return None
    if _BASE_LOSS.match(text):
        return "a-B"
    found = _SERIES.match(text)
    return found.group(1) if found else None


def ion_color(ion: str | None) -> str:
    """The colour of a fragment label's series."""
    return ION_COLORS.get(ion_series(ion), UNKNOWN_ION_COLOR)


def settings(spectrum: str = "spectrum", peak: str = "peak", **overrides) -> dict:
    """Constructor arguments, the data left out."""
    return dict(
        filters={spectrum: "spectrum"}, interactivity={peak: "peak"},
        x_column="mz", y_column="intensity", highlight_column="matched",
        annotation_column="ion", color_column="color",
        title="Fragment spectrum", x_label="m/z", y_label="Relative intensity (%)",
    ) | overrides


def rows(peaks, spectrum, ions=None):
    """A polars frame of one spectrum's ``peaks`` (``(mz, intensity)`` pairs),
    intensities relative to the highest; ``ions`` maps a peak index to its
    fragment label."""
    import polars as pl

    peaks = list(peaks)
    ions = dict(ions or {})
    top = max((float(i) for _, i in peaks), default=0.0) or 1.0
    labels = [str(ions.get(index) or "") for index in range(len(peaks))]
    return pl.DataFrame({
        "peak": list(range(len(peaks))),
        "spectrum": [spectrum] * len(peaks),
        "mz": [float(mz) for mz, _ in peaks],
        "intensity": [100.0 * float(i) / top for _, i in peaks],
        "matched": [bool(label) for label in labels],
        "ion": labels,
        "color": [ion_color(label) if label else None for label in labels],
    }, schema={"peak": pl.Int64, "spectrum": pl.Utf8 if isinstance(spectrum, str) else pl.Int64,
               "mz": pl.Float64, "intensity": pl.Float64, "matched": pl.Boolean,
               "ion": pl.Utf8, "color": pl.Utf8})
