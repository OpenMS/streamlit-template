"""3D S/N plot: the signal and noise peaks of the picked mass (the precursor
while none is picked) by mass, charge and intensity.

Insight component: ``Plot3D``. Columns: ``mass``, ``charge``, ``intensity``,
``kind`` (Signal or Noise), ``scan_idx``, ``mass_idx``.
"""

from __future__ import annotations

COMPONENT = "Plot3D"


def settings(spectrum: str = "scan", mass: str = "mass", **overrides) -> dict:
    """Constructor arguments."""
    return dict(
        filters={spectrum: "scan_idx", mass: "mass_idx"},
        filter_defaults={mass: -1},
        x_column="mass", y_column="charge", z_column="intensity", mode="stems",
        series_column="kind",
        series_colors={"Signal": "#3366CC", "Noise": "#DC3912"},
        # Both in the legend, also when one is empty
        series_names={"Signal": "Signal", "Noise": "Noise"},
        title="", selection_titles={mass: "Mass signals", spectrum: "Precursor signals"},
        x_label="Mass", y_label="Charge", z_label="Intensity", y_dtick=1,
        camera_eye={"x": 2.5, "y": 0, "z": 0.2}, svg_filename="3d-plot",
    ) | overrides
