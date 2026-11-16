"""The p-value distribution of a group comparison: entries per p-value bin
with the count expected when nothing changes. A flat histogram with a peak
near 0 is what a sound test looks like; a U-shape or a peak near 1 suggests
the input scale or the test does not fit the data.

Contract: a table with a ``p-value`` column (or the column named).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.viz.quantification.steps import bin_centres
from src.viz.series import show_series


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
    table = pd.DataFrame({"p-value": bin_centres(edges), noun: counts})
    return table, len(pvalues) / bins


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
