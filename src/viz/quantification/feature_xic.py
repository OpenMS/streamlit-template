"""Feature XIC: the extracted ion chromatogram of the picked feature over
retention time, the part inside the feature's retention time bounds drawn
apart from the trace around it.

Insight component: ``SeriesPlot``. Columns: ``feature`` (the filter), ``rt``
(min), ``intensity`` and ``series`` (``XIC`` for the trace, ``Feature`` for
the part inside the bounds).
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"

SERIES = {"XIC": "#D55E00", "Feature": "#0072B2"}


def settings(feature: str = "feature", **overrides) -> dict:
    """Constructor arguments, the data left out."""
    return dict(
        filters={feature: "feature"}, x_column="rt", y_column="intensity", series_column="series",
        series_names={name: name for name in SERIES}, series_colors=dict(SERIES), mode="lines",
        y_range_mode="nonnegative", title="Extracted ion chromatogram",
        x_label="Retention time (min)", y_label="Intensity", svg_filename="feature_xic",
    ) | overrides


def rows(feature, rt, intensity, start=None, end=None):
    """A polars frame of one feature's trace; the points between ``start`` and
    ``end`` are repeated as the ``Feature`` series."""
    import polars as pl

    rt = [float(v) for v in rt]
    intensity = [float(v) for v in intensity]
    trace = pl.DataFrame({"feature": [feature] * len(rt), "rt": rt, "intensity": intensity,
                          "series": ["XIC"] * len(rt)})
    if start is None or end is None:
        return trace
    inside = trace.filter(pl.col("rt").is_between(float(start), float(end))).with_columns(
        series=pl.lit("Feature"))
    return pl.concat([trace, inside])
