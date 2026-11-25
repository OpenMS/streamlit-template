"""A small table drawn as an openms-insight ``SeriesPlot`` (lines, markers,
bars or boxes), cached by its content and settings: a rerun reuses the plot,
a new table or setting builds it again.

Contract: a tidy table (pandas or polars) with a position column, a value
column and, where several series are drawn, a series column; their names go
to ``SeriesPlot`` as ``x_column``, ``y_column`` and ``series_column``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from src.viz.plumbing import as_polars, fingerprint, only_accepted, zoom_args

# Rows kept per box: evenly spaced values of the sorted ones, which draw the same box
BOX_POINTS = 201


def thin(frame: pl.DataFrame, by: list[str], value: str, points: int = BOX_POINTS) -> pl.DataFrame:
    """At most ``points`` evenly spaced values of ``value`` per group of ``by``."""
    frame = frame.filter(pl.col(value).is_not_null() & pl.col(value).is_finite())
    parts = []
    for _, part in frame.group_by(by, maintain_order=True):
        if part.height > points:
            rows = np.unique(np.round(np.linspace(0, part.height - 1, points)).astype(int))
            part = part.sort(value)[rows.tolist()]
        parts.append(part)
    return pl.concat(parts) if parts else frame


def show_series(data, name: str, *, cache_path, key: str, state_manager=None, height: int | None = None,
                help: str | None = None, zoom: str | None = None, **plot_kwargs):  # pylint: disable=redefined-builtin
    """Draw ``data`` as a ``SeriesPlot``; ``plot_kwargs`` go to it.

    ``highlight_data`` may be a table too. Options the installed
    openms-insight does not take (``series_modes``, ``subtitle_column``) are
    left out.
    """
    from openms_insight import SeriesPlot

    frame = as_polars(data)
    marks = plot_kwargs.pop("highlight_data", None)
    settings = dict(plot_kwargs)
    if marks is not None:
        marks = as_polars(marks)
        settings["highlight_data"] = fingerprint(marks)
        plot_kwargs["highlight_data"] = marks.lazy()
    optional = {k: plot_kwargs.pop(k) for k in ("series_modes", "subtitle_column") if k in plot_kwargs}
    plot = SeriesPlot(
        cache_id=f"{name}-{fingerprint(frame, sorted(settings.items(), key=lambda kv: kv[0]))}",
        cache_path=str(Path(cache_path, "series")), data=frame.lazy(),
        **zoom_args(SeriesPlot, zoom), **only_accepted(SeriesPlot, **optional), **plot_kwargs,
    )
    plot(key=key, state_manager=state_manager, height=height or 400, help=help)
    return plot
