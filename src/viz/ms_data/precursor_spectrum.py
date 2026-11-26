"""Precursor spectrum: the MS1 spectrum the selected fragmentation spectrum's
precursor was picked from, its precursor mass marked and the isolated m/z
range shaded.

Insight component: ``DeconvolvedSpectrum`` (``view="annotated"``), columns as
in ``ms_data.spectrum``. The caller sets the shown spectrum in ``survey`` and
the isolation window with ``set_isolation_window``.
"""

from __future__ import annotations

from src.viz.ms_data.spectrum import spectrum_settings

COMPONENT = "DeconvolvedSpectrum"


def settings(survey: str = "survey", survey_mass: str = "survey_mass", styling=None,
             **overrides) -> dict:
    """Constructor arguments: follows the spectrum in ``survey``, highlights the
    mass in ``survey_mass``."""
    return spectrum_settings(
        "annotated", survey, survey_mass, styling, title="Precursor Spectrum (MS1)",
    ) | {"svg_filename": "precursor-spectrum", "drilldown_title": "Precursor Spectrum (MS1)"} | overrides
