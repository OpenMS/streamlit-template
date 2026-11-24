"""What the plots of a group comparison's steps share: one height for all of
them, log2 values with zeros treated as missing, and histograms over shared
bins. Streamlit-free."""

from __future__ import annotations

import numpy as np
import pandas as pd


def plot_height(samples) -> int:
    """One height for every plot of the steps: room for a box per sample in the
    normalization plot, so plots placed side by side line up."""
    return max(360, 44 * len(samples) + 140)


def log2(values: pd.DataFrame) -> pd.DataFrame:
    """log2 intensities with zeros and non-positive values treated as missing."""
    values = values.apply(pd.to_numeric, errors="coerce")
    return np.log2(values.where(values > 0))


def bin_centres(edges: np.ndarray) -> np.ndarray:
    return np.round((edges[:-1] + edges[1:]) / 2, 4)


def empty_lines() -> pd.DataFrame:
    return pd.DataFrame({"x": [], "y": [], "series": []})


def histogram_lines(values: dict[str, pd.Series], bins: int, density: bool) -> pd.DataFrame:
    """Per series, the counts (or density) of ``values`` over shared bins, as x, y, series."""
    finite = pd.concat(list(values.values())).replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return empty_lines()
    edges = np.histogram_bin_edges(finite.to_numpy(dtype=float), bins=bins)
    frames = []
    for name, series in values.items():
        data = series.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
        if not len(data):
            continue
        counts, _ = np.histogram(data, bins=edges, density=density)
        frames.append(pd.DataFrame({"x": bin_centres(edges), "y": counts, "series": name}))
    return pd.concat(frames, ignore_index=True) if frames else empty_lines()


def zscores(matrix: pd.DataFrame, top: int | None = None) -> pd.DataFrame:
    """Row z-scores of ``matrix`` (rows: entries, columns: samples), of its
    ``top`` most variable rows when given; rows without a spread are dropped."""
    matrix = matrix.apply(pd.to_numeric, errors="coerce")
    if top is not None:
        matrix = matrix.loc[matrix.var(axis=1).sort_values(ascending=False).head(top).index]
    scores = matrix.sub(matrix.mean(axis=1), axis=0).div(matrix.std(axis=1), axis=0)
    return scores.replace([np.inf, -np.inf], np.nan).dropna()


# Older names
_log2, _bin_centres, _empty_lines, _histogram_lines = log2, bin_centres, empty_lines, histogram_lines
