"""Deconvolved heatmap: the masses of one MS level by retention time and
monoisotopic mass, coloured by log intensity. A click selects the spectrum and
the mass.

Insight component: ``Heatmap``. Columns: ``rt``, ``mass``, ``intensity``,
``scan_idx``, ``mass_idx``.
"""

from __future__ import annotations

from src.viz.ms_data.raw_heatmap import settings as _heatmap_settings

COMPONENT = "Heatmap"


def settings(title: str = "Deconvolved MS1 Heatmap", spectrum: str = "scan", mass: str = "mass",
             **overrides) -> dict:
    """Constructor arguments."""
    return _heatmap_settings(title, "Monoisotopic Mass", spectrum, mass, **overrides)
