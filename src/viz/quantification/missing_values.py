"""Where missing values occur: the density of the mean log2 abundance of
complete entries and of entries with gaps. Gaps among low abundances point to
values below the detection limit (MNAR), gaps spread over every abundance to
random dropout (MAR).

Contract: a wide table with one row per entry and a column of abundances per
sample, and the list of sample columns.
"""

from __future__ import annotations

import pandas as pd

from src.viz.quantification.steps import histogram_lines, log2, plot_height
from src.viz.series import show_series


MISSING_SERIES = {"complete": "Complete", "missing": "With missing values"}
MISSING_COLORS = {"complete": "#3498DB", "missing": "#E67E22"}


def missingness_vs_intensity(df: pd.DataFrame, sample_cols: list[str]) -> tuple[pd.DataFrame, int]:
    """Density of the mean log2 intensity of entries with and without missing values.

    If entries with missing values sit clearly lower than complete ones,
    values are missing because they fall below the detection limit (MNAR);
    overlapping distributions point to random dropout (MAR). Returns the
    table (x, y, series) and the number of entries with a gap.
    """
    log_values = log2(df[sample_cols])
    has_missing = log_values.isna().any(axis=1)
    means = log_values.mean(axis=1)
    table = histogram_lines(
        {"complete": means[~has_missing], "missing": means[has_missing]}, bins=40, density=True
    )
    return table, int(has_missing.sum())


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
