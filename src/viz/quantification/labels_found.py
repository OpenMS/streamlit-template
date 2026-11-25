"""Labels found per spectrum: bars of the spectra carrying 0, 1 ... all
reporter ions of an isobaric labelling.

Insight component: ``SeriesPlot`` (bars). Columns: ``labels`` (how many) and
``spectra``.
"""

from __future__ import annotations

import polars as pl

COMPONENT = "SeriesPlot"


def settings(table: pl.DataFrame, plex: str, **overrides) -> dict:
    """Constructor arguments with the plot's table as ``data``."""
    total = int(table["spectra"].sum()) or 1
    data = table.select(
        pl.col("labels").cast(pl.Utf8), "spectra",
        pl.format("{} labels: {} spectra ({}%)", "labels", "spectra",
                  (pl.col("spectra") * 100.0 / total).round(0)).alias("hover"),
    )
    return dict(
        data=data, x_column="labels", y_column="spectra", mode="bars", hover_column="hover", show_legend=False,
        title=f"Reporter ions found per spectrum ({plex})", x_label="Labels with a reporter ion",
        y_label="Spectra",
    ) | overrides
