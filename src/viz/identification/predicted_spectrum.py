"""Measured against predicted spectrum: the measured spectrum of the picked
PSM above, the fragment spectrum a prediction model expects for its peptide
below, matched fragments marked on both. The selections ``measured`` and
``predicted`` pick the side each half shows; set them to 0 and 1.

Insight component: ``MirrorPlot``. Columns: ``side`` (0 measured, 1
predicted), ``peak_id``, ``mass``, ``intensity`` (relative, %), ``highlight``,
``ion``.
"""

from __future__ import annotations

COMPONENT = "MirrorPlot"


def settings(predicted_by: str, styling=None, measured: str = "mirror_measured",
             predicted: str = "mirror_predicted", peak: str = "peak", **overrides) -> dict:
    """``predicted_by`` names the lower half (the model and instrument)."""
    return dict(
        filters_top={measured: "side"}, filter_defaults_top={measured: 0},
        filters_bottom={predicted: "side"}, filter_defaults_bottom={predicted: 1},
        interactivity={peak: "peak_id"},
        x_column="mass", y_column="intensity", highlight_column="highlight", annotation_column="ion",
        title_top="Measured", title_bottom=predicted_by,
        x_label="m/z", y_label="Relative intensity (%)",
        **({"styling": styling} if styling else {}),
    ) | overrides
