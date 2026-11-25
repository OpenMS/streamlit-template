"""Deconvolved spectrum: the masses of the selected spectrum as sticks, the
picked one highlighted, with the fragment ions a sequence view matched.

Insight component: ``DeconvolvedSpectrum`` (``view="deconvolved"``), columns
as in ``ms_data.spectrum``.
"""

from __future__ import annotations

from src.viz.ms_data.spectrum import spectrum_settings

COMPONENT = "DeconvolvedSpectrum"


def settings(spectrum: str = "scan", mass: str = "mass", styling=None, **overrides) -> dict:
    """Constructor arguments, following the spectrum picked in ``spectrum``."""
    return spectrum_settings("deconvolved", spectrum, mass, styling, **overrides)
