"""3D peak map: the MS1 peaks of a run by m/z, retention time and intensity,
the strongest peaks of each spectrum; the precursor spectrum of the selected
spectrum drawn apart.

Insight component: ``Plot3D``. Columns: ``mz``, ``rt``, ``intensity``,
``scan_idx``.
"""

from __future__ import annotations

COMPONENT = "Plot3D"

# A box wider than deep fills a full-width cell; its middle a little below
# the view's keeps the m/z axis in the cell
SHAPE = dict(aspect_ratio={"x": 2.2, "y": 1.2, "z": 1.0}, camera_center={"x": 0, "y": 0, "z": -0.25})


def settings(peaks_per_spectrum: int, color: str, highlight: str | None = None,
             highlight_color: str | None = None, **overrides) -> dict:
    """Constructor arguments. ``highlight`` names the selection whose spectrum
    (its ``scan_idx``) is drawn in ``highlight_color``; options of a newer
    openms-insight are left out by the caller."""
    extra = {}
    if highlight:
        extra = dict(highlight={highlight: "scan_idx"}, highlight_name="Precursor spectrum",
                     highlight_color=highlight_color)
    return dict(
        x_column="mz", y_column="rt", z_column="intensity", mode="stems",
        color=color, series_names={"": "MS1 peaks"},
        title=f"MS1 peaks (strongest {peaks_per_spectrum} per spectrum)",
        x_label="m/z", y_label="Retention Time", z_label="Intensity",
        camera_eye={"x": 1.4, "y": -2.0, "z": 0.45}, svg_filename="ms1-3d-map",
        **extra, **SHAPE,
    ) | overrides
