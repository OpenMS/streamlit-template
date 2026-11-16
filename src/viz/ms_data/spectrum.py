"""Raw spectrum: the peaks of the selected spectrum, those of a deconvolved
mass marked, with the picked mass's isotope envelope and the fragment ions a
sequence view matched.

Insight component: ``DeconvolvedSpectrum`` (``view="annotated"``). Columns:
``index`` (the spectrum), ``MonoMass``/``SumIntensity`` (the masses),
``MonoMass_Anno``/``SumIntensity_Anno`` (the peaks), ``SignalPeaks``.
"""

from __future__ import annotations

COMPONENT = "DeconvolvedSpectrum"

COLUMNS = dict(
    mass_column="MonoMass", mass_intensity_column="SumIntensity",
    peak_mz_column="MonoMass_Anno", peak_intensity_column="SumIntensity_Anno",
    signal_column="SignalPeaks",
)
TITLES = {
    "deconvolved": "Deconvolved Spectrum",
    "annotated": "Annotated Spectrum",
    "ladder": "Augmented Deconvolved Spectrum",
}


def spectrum_settings(view: str, spectrum: str = "scan", mass: str = "mass", styling=None,
                      title: str | None = None, **overrides) -> dict:
    """Constructor arguments of a spectrum drawn as ``view`` (deconvolved,
    annotated or ladder), following the spectrum picked in ``spectrum``."""
    return dict(
        filters={spectrum: "index"}, view=view, mass_identifier=mass,
        title=title or TITLES[view], svg_filename="lineplot",
        drilldown_title="Augmented Annotated Spectrum",
        **COLUMNS, float_precision="float64",
        **({"styling": styling} if styling is not None else {}),
    ) | overrides


def settings(spectrum: str = "scan", mass: str = "mass", styling=None, **overrides) -> dict:
    """Constructor arguments of the raw (annotated) spectrum."""
    return spectrum_settings("annotated", spectrum, mass, styling, **overrides)
