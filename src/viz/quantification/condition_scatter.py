"""Condition scatter: every entry's mean abundance in one condition against
another, a line where both are equal, unmodified and modified entries apart.
A click picks the entry.

Insight component: ``SeriesPlot`` (markers). Columns: ``entry`` (the entry),
``x`` (mean in the denominator condition), ``y`` (mean in the numerator
condition), ``series`` (``Unmodified``, ``Modified``, or ``Equal`` for the
line), ``label`` (the hover text) and ``contrast`` (the filter).
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"

SERIES = {"Unmodified": "#0072B2", "Modified": "#D55E00", "Equal": "#9CA3AF"}


def settings(numerator: str, denominator: str, log: bool = True, entry: str = "entry",
             contrast: str = "contrast", **overrides) -> dict:
    """Constructor arguments for ``numerator`` against ``denominator``; with
    ``log`` the means are log10 values (``rows(log=True)``)."""
    scale = "log10 mean" if log else "Mean"
    return dict(
        filters={contrast: "contrast"}, interactivity={entry: "entry"}, highlight={entry: "entry"},
        x_column="x", y_column="y", series_column="series",
        series_names={name: name for name in SERIES}, series_colors=dict(SERIES),
        mode="markers", series_modes={"Equal": "lines"}, hover_column="label",
        title=f"{numerator} vs {denominator}", x_label=f"{scale} {denominator}",
        y_label=f"{scale} {numerator}", svg_filename="condition_scatter",
    ) | overrides


def rows(entries: list[dict], contrast: str, log: bool = True):
    """A polars frame of ``entries`` (``entry``, ``x``, ``y``, ``modified``,
    optional ``label``), positive means only when ``log``, with the y = x line
    over their range."""
    import math

    import polars as pl

    records = []
    for item in entries:
        x, y = item.get("x"), item.get("y")
        if x is None or y is None or (log and (x <= 0 or y <= 0)):
            continue
        x, y = (math.log10(x), math.log10(y)) if log else (float(x), float(y))
        records.append({"entry": int(item["entry"]), "x": x, "y": y, "contrast": contrast,
                        "series": "Modified" if item.get("modified") else "Unmodified",
                        "label": str(item.get("label") or item["entry"])})
    if records:
        low = min(min(r["x"], r["y"]) for r in records)
        high = max(max(r["x"], r["y"]) for r in records)
        for point in (low, high):
            records.append({"entry": -1, "x": point, "y": point, "contrast": contrast,
                            "series": "Equal", "label": "Equal abundance"})
    schema = {"entry": pl.Int64, "x": pl.Float64, "y": pl.Float64, "contrast": pl.Utf8,
              "series": pl.Utf8, "label": pl.Utf8}
    return pl.DataFrame(records, schema=schema)
