"""Filter threshold: how many entries (proteins) a filter of the group
comparison keeps at each threshold, beside all entries and the threshold
chosen now. A plateau means the threshold is not sensitive there; a steep drop
shows where the filter starts removing many entries.

Insight component: ``SeriesPlot``. Columns: ``threshold``, ``kept``,
``series`` (``Kept``, ``All``, ``Current``); ``rows()`` builds them.
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"

COLORS = {"Kept": "#3157e9", "All": "#a1a1aa", "Current": "#ff7501"}


def rows(thresholds: list[float], kept: list[int], total: int, current: float, kept_now: int) -> list[dict]:
    """The curve, the line of all entries and the point at the current threshold."""
    return (
        [{"threshold": t, "kept": k, "series": "Kept"} for t, k in zip(thresholds, kept)]
        + [{"threshold": t, "kept": total, "series": "All"} for t in (min(thresholds), max(thresholds))]
        + [{"threshold": current, "kept": kept_now, "series": "Current"}]
    )


def settings(x_label: str, noun: str = "Proteins", **overrides) -> dict:
    return dict(
        x_column="threshold", y_column="kept", series_column="series",
        series_names={"Kept": f"{noun} kept", "All": f"All {noun.lower()}", "Current": "Current threshold"},
        series_colors=COLORS, series_modes={"Kept": "lines+markers", "All": "lines", "Current": "markers"},
        title=f"{noun} kept at each threshold", x_label=x_label, y_label=f"{noun} kept",
        svg_filename="filter-threshold",
    ) | overrides
