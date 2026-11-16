"""Reporter ion plot: the reporter ions of the selected spectrum, one per
label, each label named at its m/z.

Insight component: ``LinePlot``. Columns: ``scan_idx``, ``mz``,
``intensity``, ``label``. With an Insight whose ``LinePlot`` takes
``x_markers``, each label is a marker (a guide with its name and a dot on its
reporter ion), so a label without signal keeps its name; older releases label
the sticks.
"""

from __future__ import annotations

COMPONENT = "LinePlot"

# Reporter ions of neighbouring TMT channels are 0.0063 m/z apart
TOLERANCE = 0.003


def settings(spectrum: str = "scan", **overrides) -> dict:
    """Constructor arguments, the data left out."""
    return dict(
        filters={spectrum: "scan_idx"}, x_column="mz", y_column="intensity",
        title="Reporter ions of the selected spectrum", x_label="m/z", y_label="Intensity",
    ) | overrides


def plot_args(channels, mzs, markers: bool):
    """How the plot shows its labels: a function giving the data arguments from
    the reporter frame, and the arguments to pass when drawing.

    ``markers`` says whether the installed ``LinePlot`` takes ``x_markers``.
    """
    if not markers:
        return (lambda data: dict(data=data, annotation_column="label")), {}

    def data_args(data):
        import polars as pl
        # The unlabelled points at the edges stay: they keep the range
        return dict(data=data.filter((pl.col("intensity") > 0) | (pl.col("label") == "")))

    marked = {c: mz for c, mz in zip(channels, mzs) if mz}
    return data_args, {"x_markers": marked, "x_marker_tolerance": TOLERANCE}
