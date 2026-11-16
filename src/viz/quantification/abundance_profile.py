"""Abundance of the picked entry in every sample: one point per sample,
samples side by side group by group, and a line at each group's mean across
its samples (the gap between two means is the fold change the volcano plot
shows). With several entries picked together, each of them as a series.

Contract: a long table, one row per entry and sample, with an id column, the
sample, its group and the value; ``hover_column`` (text shown on a point) and
``keep`` (columns such as a subtitle) are carried over.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.viz.plumbing import as_polars, fingerprint, group_colors, only_accepted, zoom_args

MEAN_SUFFIX = " mean"
SERIES = "series"


def profile_table(long, id_column: str, *, sample_column: str = "sample", group_column: str = "group",
                  value_column: str = "value", hover_column: str | None = None, keep=(),
                  log2: bool = False, means: bool = True, samples=None) -> pd.DataFrame:
    """Columns ``id_column``, ``x`` (the sample's place), ``y``, ``series``
    (its group, or ``<group> mean`` for a mean line), ``sample``, ``hover``
    and ``keep``.

    Samples are placed group by group (groups in sorted order, as their
    colours), within a group in the order of ``samples`` or of the table. With
    ``log2`` the values are log2 transformed and values of 0 or less left out;
    missing values are always left out.
    """
    frame = as_polars(long).to_pandas()
    keep = [c for c in keep if c in frame.columns and c not in (id_column, hover_column)]
    columns = [id_column, sample_column, group_column, value_column, *keep]
    if hover_column:
        columns.append(hover_column)
    frame = frame[list(dict.fromkeys(columns))].copy()
    frame[sample_column] = frame[sample_column].astype(str)
    frame[group_column] = frame[group_column].astype(str)
    group_of = dict(zip(frame[sample_column], frame[group_column]))
    order = [str(s) for s in samples if str(s) in group_of] if samples is not None else []
    order += [s for s in dict.fromkeys(frame[sample_column]) if s not in order]
    order = sorted(order, key=lambda s: (group_of[s], order.index(s)))
    place = {s: i + 1 for i, s in enumerate(order)}

    values = pd.to_numeric(frame[value_column], errors="coerce")
    if log2:
        frame = frame[values > 0]
        values = np.log2(values[values > 0].astype(float))
    else:
        frame = frame[values.notna()]
        values = values[values.notna()].astype(float)
    points = pd.DataFrame({
        id_column: frame[id_column].values,
        "x": frame[sample_column].map(place).astype(float).values,
        "y": values.values,
        SERIES: frame[group_column].values,
        "sample": frame[sample_column].values,
        "hover": (frame[hover_column] if hover_column else frame[sample_column]).astype(str).values,
    })
    for column in keep:
        points[column] = frame[column].values
    if points.empty or not means:
        return points.sort_values([id_column, SERIES, "x"]).reset_index(drop=True)

    span = {}
    for sample in order:
        first, last = span.get(group_of[sample], (place[sample], place[sample]))
        span[group_of[sample]] = (min(first, place[sample]), max(last, place[sample]))
    extra = {c: "first" for c in keep}
    mean = points.groupby([id_column, SERIES], as_index=False).agg(y=("y", "mean"), **{
        c: (c, how) for c, how in extra.items()})
    lines = pd.concat([mean.assign(x=mean[SERIES].map(lambda g, i=i: float(span[g][i]))) for i in (0, 1)])
    lines["sample"] = "mean of " + lines[SERIES]
    lines["hover"] = lines["sample"]
    lines[SERIES] = lines[SERIES] + MEAN_SUFFIX
    return (pd.concat([points, lines[points.columns]])
            .sort_values([id_column, SERIES, "x"]).reset_index(drop=True))


def profile_colors(groups) -> dict[str, str]:
    """A group and its mean line in the group's colour (``group_colors``)."""
    colors = group_colors(groups)
    return {**colors, **{f"{g}{MEAN_SUFFIX}": c for g, c in colors.items()}}


def picked_set(state_manager, identifier: str) -> list:
    """The entries picked together under ``identifier`` (a box, a lasso, check
    boxes), when there are several; else an empty list."""
    if state_manager is None or not identifier:
        return []
    picked = [p for p in (state_manager.get_selection(identifier) or []) if p is not None]
    return picked if len(picked) > 1 else []


def profile_settings(table: pd.DataFrame, id_column: str, filter_identifier: str, *,
                     several: bool = False, series_column: str | None = None,
                     empty_until_picked: bool = True, title: str | None = None,
                     x_label: str = "Sample", y_label: str = "Abundance",
                     subtitle_column: str | None = None, groups=None) -> dict:
    """The ``SeriesPlot`` arguments (besides data and cache).

    One entry: ``filter_identifier`` picks it, coloured by group with the
    group means as lines (``empty_until_picked`` draws nothing until one is
    picked). ``several``: ``filter_identifier`` is a set of entries, each
    drawn as a series (``series_column``, default the id column).
    ``groups`` names every group of the experiment, so a group whose values
    are all missing keeps its place in the colours (default: those in ``table``).
    """
    from openms_insight import SeriesPlot

    settings = dict(
        filters={filter_identifier: id_column}, x_column="x", y_column="y", mode="markers",
        hover_column="hover", y_range_mode="normal", x_label=x_label, y_label=y_label,
    )
    if title:
        settings["title"] = title
    if several:
        settings["series_column"] = series_column or id_column
        return settings
    if groups is None:
        groups = [g for g in dict.fromkeys(table[SERIES]) if not str(g).endswith(MEAN_SUFFIX)]
    groups = [str(g) for g in dict.fromkeys(groups)]
    settings.update(series_column=SERIES, series_colors=profile_colors(groups))
    if empty_until_picked:
        settings["filter_defaults"] = {filter_identifier: "__none__"}
    # Samples are points, not a sequence: only the group means are lines
    optional = {"series_modes": {f"{g}{MEAN_SUFFIX}": "lines" for g in groups}}
    if subtitle_column:
        optional["subtitle_column"] = subtitle_column
    settings.update(only_accepted(SeriesPlot, **optional))
    return settings


def show_profile(long, id_column: str, filter_identifier: str, name: str = "abundance-profile", *,
                 cache_path, key: str, state_manager=None, height: int = 560,
                 help: str | None = None, zoom: str | None = None,  # pylint: disable=redefined-builtin
                 several: bool = False, table_args: dict | None = None, **settings):
    """Draw ``long`` (see the module) as an abundance profile; ``table_args``
    go to ``profile_table``, ``settings`` to ``profile_settings``."""
    from openms_insight import SeriesPlot

    table_args = table_args or {}
    long = as_polars(long)
    table = profile_table(long, id_column, means=not several, **table_args)
    if not several and "groups" not in settings:
        settings["groups"] = long[table_args.get("group_column", "group")].cast(str).unique().sort().to_list()
    arguments = profile_settings(table, id_column, filter_identifier, several=several, **settings)
    frame = as_polars(table)
    plot = SeriesPlot(
        cache_id=f"{name}-{fingerprint(frame, sorted(arguments.items(), key=lambda kv: kv[0]))}",
        cache_path=str(cache_path), data=frame.lazy(), **zoom_args(SeriesPlot, zoom), **arguments,
    )
    plot(key=key, state_manager=state_manager, height=height, help=help)
    return plot
