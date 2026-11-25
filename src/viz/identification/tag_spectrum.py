"""Tag spectrum: the deconvolved masses of the selected spectrum with the
picked sequence tag drawn as a ladder of residues over them.

Insight component: ``DeconvolvedSpectrum`` (``view="ladder"``), columns as in
``ms_data.spectrum``. The caller passes the tag with ``set_ladder(masses,
sequence, picked residue)``.
"""

from __future__ import annotations

from src.viz.ms_data.spectrum import spectrum_settings

COMPONENT = "DeconvolvedSpectrum"


def settings(spectrum: str = "pscan", mass: str = "mass", styling=None, **overrides) -> dict:
    """Constructor arguments, following the spectrum picked in ``spectrum``."""
    return spectrum_settings("ladder", spectrum, mass, styling, **overrides)
