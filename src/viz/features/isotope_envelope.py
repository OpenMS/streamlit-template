"""Isotope envelope fit: the observed isotope envelope of the picked mass (all
charges summed; the precursor while no mass is picked) above the averagine
envelope of that mass.

Insight component: ``MirrorPlot``. Columns: ``mass``, ``abundance``,
``top_scan``/``top_mass`` (observed rows), ``bottom_scan``/``bottom_mass``
(averagine rows).
"""

from __future__ import annotations

COMPONENT = "MirrorPlot"


def settings(spectrum: str = "scan", mass: str = "mass", styling=None, **overrides) -> dict:
    """Constructor arguments."""
    return dict(
        filters_top={spectrum: "top_scan", mass: "top_mass"},
        filter_defaults_top={mass: -1},
        filters_bottom={spectrum: "bottom_scan", mass: "bottom_mass"},
        filter_defaults_bottom={mass: -1},
        x_column="mass", y_column="abundance", title="Isotope Envelope Fit",
        title_top="Observed (all charges)", title_bottom="Averagine",
        x_label="Mass (Da)", y_label="Relative abundance",
        **({"styling": styling} if styling is not None else {}),
    ) | overrides
