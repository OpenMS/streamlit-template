"""The plots behind the steps of a group comparison: where values are missing,
the values imputation fills in, each sample before and after normalization,
and the p-values of the test.

Contract: a wide table with one row per entry (protein, proteoform, feature)
and one column of abundances per sample, given with the list of sample
columns; for the p-values, a table with a ``p-value`` column. Each step has
a data function (a tidy table for a ``SeriesPlot``, Streamlit-free) and a
``show_*`` panel that draws it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.viz.series import show_series


def plot_height(samples) -> int:
    """One height for every plot of the steps: room for a box per sample in the
    normalization plot, so plots placed side by side line up."""
    return max(360, 44 * len(samples) + 140)


def _log2(values: pd.DataFrame) -> pd.DataFrame:
    """log2 intensities with zeros and non-positive values treated as missing."""
    values = values.apply(pd.to_numeric, errors="coerce")
    return np.log2(values.where(values > 0))


def _bin_centres(edges: np.ndarray) -> np.ndarray:
    return np.round((edges[:-1] + edges[1:]) / 2, 4)


def _empty_lines() -> pd.DataFrame:
    return pd.DataFrame({"x": [], "y": [], "series": []})


def _histogram_lines(values: dict[str, pd.Series], bins: int, density: bool) -> pd.DataFrame:
    """Per series, the counts (or density) of ``values`` over shared bins, as x, y, series."""
    finite = pd.concat(list(values.values())).replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return _empty_lines()
    edges = np.histogram_bin_edges(finite.to_numpy(dtype=float), bins=bins)
    frames = []
    for name, series in values.items():
        data = series.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
        if not len(data):
            continue
        counts, _ = np.histogram(data, bins=edges, density=density)
        frames.append(pd.DataFrame({"x": _bin_centres(edges), "y": counts, "series": name}))
    return pd.concat(frames, ignore_index=True) if frames else _empty_lines()


MISSING_SERIES = {"complete": "Complete", "missing": "With missing values"}
MISSING_COLORS = {"complete": "#3498DB", "missing": "#E67E22"}


def missingness_vs_intensity(df: pd.DataFrame, sample_cols: list[str]) -> tuple[pd.DataFrame, int]:
    """Density of the mean log2 intensity of entries with and without missing values.

    If entries with missing values sit clearly lower than complete ones,
    values are missing because they fall below the detection limit (MNAR);
    overlapping distributions point to random dropout (MAR). Returns the
    table (x, y, series) and the number of entries with a gap.
    """
    log_values = _log2(df[sample_cols])
    has_missing = log_values.isna().any(axis=1)
    means = log_values.mean(axis=1)
    table = _histogram_lines(
        {"complete": means[~has_missing], "missing": means[has_missing]}, bins=40, density=True
    )
    return table, int(has_missing.sum())


IMPUTED_SERIES = {"observed": "Observed", "imputed": "Filled in"}
IMPUTED_COLORS = {"observed": "#3498DB", "imputed": "#E74C3C"}


def imputed_value_preview(before: pd.DataFrame, after: pd.DataFrame, sample_cols: list[str]) -> pd.DataFrame:
    """Counts of observed log2 values and of the values imputation fills in, as x, y, series."""
    before_log = _log2(before[sample_cols])
    after_log = _log2(after[sample_cols])
    observed = before_log.stack()
    imputed = after_log.where(before_log.isna()).stack()
    return _histogram_lines({"observed": observed, "imputed": imputed}, bins=60, density=False)


STAGE_SERIES = {"before": "Before", "after": "After"}
STAGE_COLORS = {"before": "#95A5A6", "after": "#3498DB"}


def sample_distributions(
    before: pd.DataFrame,
    after: pd.DataFrame,
    sample_cols: list[str],
    after_is_log: bool,
    points: int = 201,
) -> pd.DataFrame:
    """Per sample, log2 intensities before and after normalization, as Sample, Intensity, Stage.

    Well-normalized samples have aligned medians; a sample that stays offset
    after normalization is worth checking. Untransformed tables are shown on
    a log2 scale. Each sample and stage keeps ``points`` evenly spaced
    quantiles of its values, which draw the same box as all of them.
    """
    frames = []
    quantiles = np.linspace(0, 1, points)
    for stage, table, is_log in [("before", before, False), ("after", after, after_is_log)]:
        values = table[sample_cols].apply(pd.to_numeric, errors="coerce")
        if not is_log:
            values = _log2(values)
        for sample in sample_cols:
            column = values[sample].replace([np.inf, -np.inf], np.nan).dropna()
            if column.empty:
                continue
            kept = column.to_numpy(dtype=float) if len(column) <= points else column.quantile(quantiles).to_numpy()
            frames.append(pd.DataFrame({"Sample": sample, "Intensity": kept, "Stage": stage}))
    if not frames:
        return pd.DataFrame({"Sample": [], "Intensity": [], "Stage": []})
    return pd.concat(frames, ignore_index=True)


def pvalue_histogram(statistics_df: pd.DataFrame, bins: int = 20, noun: str = "Entries",
                     column: str = "p-value") -> tuple[pd.DataFrame, float]:
    """Entries per p-value bin (``p-value`` = bin centre, ``noun`` = entries) and
    the count expected per bin.

    A flat histogram with a peak near 0 is what a sound test looks like. A
    U-shape or a peak near 1 suggests the input scale or the chosen test does
    not fit the data. The expected count is what each bin holds when no
    entry changes.
    """
    pvalues = pd.to_numeric(statistics_df[column], errors="coerce").dropna()
    edges = np.linspace(0, 1, bins + 1)
    counts, _ = np.histogram(pvalues.clip(0, 1).to_numpy(dtype=float), bins=edges)
    table = pd.DataFrame({"p-value": _bin_centres(edges), noun: counts})
    return table, len(pvalues) / bins


# -- panels --------------------------------------------------------------------
# Each takes the cache folder, the widget key, the experiment's state, the
# height and the info text; ``title`` replaces the default title.


def show_missing_values(table: pd.DataFrame, samples: list[str], name: str = "comparison-missing-values", *,
                        cache_path, key: str, state_manager=None, height: int | None = None,
                        help: str | None = None, title: str | None = None,  # pylint: disable=redefined-builtin
                        x_label: str = "Mean log2 abundance"):
    """Density of the mean abundance of complete entries and of entries with gaps."""
    data, gaps = missingness_vs_intensity(table, samples)
    if title is None:
        title = f"Where missing values occur ({gaps} of {len(table)} have gaps)"
    return show_series(
        data, name, cache_path=cache_path, key=key, state_manager=state_manager,
        height=height or plot_height(samples), help=help, title=title,
        x_column="x", y_column="y", series_column="series", series_names=MISSING_SERIES,
        series_colors=MISSING_COLORS, x_label=x_label, y_label="Density", y_range_mode="nonnegative",
    )


def show_imputed_values(before: pd.DataFrame, after: pd.DataFrame, samples: list[str],
                        name: str = "comparison-imputed-values", *, cache_path, key: str, state_manager=None,
                        height: int | None = None, help: str | None = None,  # pylint: disable=redefined-builtin
                        title: str | None = "Observed values and the values imputation fills in",
                        x_label: str = "log2 abundance"):
    """The values imputation fills in against the measured ones."""
    return show_series(
        imputed_value_preview(before, after, samples), name, cache_path=cache_path, key=key,
        state_manager=state_manager, height=height or plot_height(samples), help=help, title=title,
        x_column="x", y_column="y", series_column="series", series_names=IMPUTED_SERIES,
        series_colors=IMPUTED_COLORS, x_label=x_label, y_label="Values", y_range_mode="nonnegative",
    )


def show_normalization(before: pd.DataFrame, after: pd.DataFrame, samples: list[str], after_is_log: bool,
                       name: str = "comparison-normalization", *, cache_path, key: str, state_manager=None,
                       height: int | None = None, help: str | None = None,  # pylint: disable=redefined-builtin
                       title: str | None = "Intensity distributions before and after normalization",
                       sample_label: str = "Sample", labels: dict | None = None,
                       y_label: str = "log2 abundance"):
    """A box per sample, before and after normalization; ``labels`` shortens the sample names."""
    data = sample_distributions(before, after, samples, after_is_log)
    if labels:
        data["Sample"] = data["Sample"].map(lambda s: labels.get(s, s))
    return show_series(
        data, name, cache_path=cache_path, key=key, state_manager=state_manager,
        height=max(height or 0, plot_height(samples)), help=help, title=title,
        x_column="Sample", y_column="Intensity", series_column="Stage", series_names=STAGE_SERIES,
        series_colors=STAGE_COLORS, mode="box", orientation="h", x_label=sample_label, y_label=y_label,
        y_range_mode="normal",
    )


def show_pvalues(statistics_df: pd.DataFrame, name: str = "comparison-p-values", *, cache_path, key: str,
                 noun: str = "Entries", state_manager=None, height: int | None = None,
                 help: str | None = None, title: str | None = None,  # pylint: disable=redefined-builtin
                 column: str = "p-value"):
    """Entries per p-value bin; ``noun`` names them (``Proteins``)."""
    data, expected = pvalue_histogram(statistics_df, noun=noun, column=column)
    if title is None:
        title = f"p-value distribution ({expected:.0f} per bin if nothing changes)"
    return show_series(
        data, name, cache_path=cache_path, key=key, state_manager=state_manager, height=height or 360,
        help=help, title=title, x_column="p-value", y_column=noun, mode="bars", x_label="p-value",
        y_label=noun, show_legend=False, y_range_mode="nonnegative",
    )
