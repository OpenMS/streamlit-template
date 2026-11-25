"""Intensity distributions before and after normalization: a box per sample
and stage. Well-normalized samples have aligned medians; a sample that stays
offset is worth checking.

Contract: the wide table before and after normalization (one row per entry,
a column per sample), the list of sample columns and whether the table after
normalization is already on a log scale.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.viz.quantification.steps import log2, plot_height
from src.viz.series import show_series


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
            values = log2(values)
        for sample in sample_cols:
            column = values[sample].replace([np.inf, -np.inf], np.nan).dropna()
            if column.empty:
                continue
            kept = column.to_numpy(dtype=float) if len(column) <= points else column.quantile(quantiles).to_numpy()
            frames.append(pd.DataFrame({"Sample": sample, "Intensity": kept, "Stage": stage}))
    if not frames:
        return pd.DataFrame({"Sample": [], "Intensity": [], "Stage": []})
    return pd.concat(frames, ignore_index=True)


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
