"""Raw heatmap: the peaks of one MS level by retention time and m/z, coloured
by log intensity, downsampled in levels so a whole run draws at once. A click
selects the spectrum.

Insight component: ``Heatmap``. Columns: ``rt``, ``mass`` (m/z, or the
monoisotopic mass of a deconvolved map), ``intensity``, ``scan_idx`` (and
``mass_idx`` when a click also picks the mass).
"""

from __future__ import annotations

COMPONENT = "Heatmap"

# Points a zoomed view shows of the first level with this many in range
MIN_POINTS = 20000


def settings(title: str = "Raw MS1 Heatmap", y_label: str = "m/z", spectrum: str = "scan",
             mass: str | None = None, min_points: int = MIN_POINTS, **overrides) -> dict:
    """Constructor arguments; ``mass`` names the selection a click writes the
    point's ``mass_idx`` to (a deconvolved map)."""
    interactivity = {spectrum: "scan_idx"}
    if mass:
        interactivity[mass] = "mass_idx"
    return dict(
        x_column="rt", y_column="mass", intensity_column="intensity",
        interactivity=interactivity,
        title=title, x_label="Retention Time", y_label=y_label,
        colorscale="Portland", log_scale=True,
        min_points=min_points,
        # A zoomed view shows every point of the first level with min_points in range
        downsample_zoomed=False,
        svg_filename="heatmap", scroll_zoom=False,
    ) | overrides
