"""The values imputation fills in against the measured ones: counts of
observed log2 abundances and of the filled-in values, so a reader sees where
imputation puts them.

Contract: the wide table before and after imputation (one row per entry, a
column per sample) and the list of sample columns.
"""

from __future__ import annotations

import pandas as pd

from src.viz.quantification.steps import histogram_lines, log2, plot_height
from src.viz.series import show_series


IMPUTED_SERIES = {"observed": "Observed", "imputed": "Filled in"}
IMPUTED_COLORS = {"observed": "#3498DB", "imputed": "#E74C3C"}


def imputed_value_preview(before: pd.DataFrame, after: pd.DataFrame, sample_cols: list[str]) -> pd.DataFrame:
    """Counts of observed log2 values and of the values imputation fills in, as x, y, series."""
    before_log = log2(before[sample_cols])
    after_log = log2(after[sample_cols])
    observed = before_log.stack()
    imputed = after_log.where(before_log.isna()).stack()
    return histogram_lines({"observed": observed, "imputed": imputed}, bins=60, density=False)


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
