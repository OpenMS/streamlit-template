"""Mass table: the deconvolved masses of the selected spectrum with their
intensity, charge and isotope range, isotope cosine, S/N and quality score.
A click picks the mass.

Insight component: ``Table``. Columns: ``mass_idx``, ``scan_idx`` (the
spectrum), ``MonoMass``, ``SumIntensity``, ``MinCharges``, ``MaxCharges``,
``MinIsotopes``, ``MaxIsotopes``, ``CosineScore``, ``SNR``, ``QScore``.
"""

from __future__ import annotations

from src.viz.columns import BROWSE, fixed

COMPONENT = "Table"

COLUMNS = [
    {"title": "Index", "field": "mass_idx", "sorter": "number",
     "headerTooltip": "The sequential index of the mass entry in the dataset."},
    {"title": "Monoisotopic mass", "field": "MonoMass", "sorter": "number", **fixed(),
     "headerTooltip": "The monoisotopic mass of the detected ion in Daltons."},
    {"title": "Sum intensity", "field": "SumIntensity", "sorter": "number", **fixed(),
     "headerTooltip": "The total intensity of the detected mass across all isotopic peaks and charges."},
    {"title": "Min charge", "field": "MinCharges", "sorter": "number",
     "headerTooltip": "The minimum charge state detected for the mass."},
    {"title": "Max charge", "field": "MaxCharges", "sorter": "number",
     "headerTooltip": "The maximum charge state detected for the mass."},
    {"title": "Min isotope", "field": "MinIsotopes", "sorter": "number",
     "headerTooltip": "The smallest observed isotopic shift, expressed as a multiple of the average isotopic mass difference at 55kDA."},
    {"title": "Max isotope", "field": "MaxIsotopes", "sorter": "number",
     "headerTooltip": "The largest observed isotopic shift, expressed as a multiple of the average isotopic mass difference at 55kDA."},
    {"title": "Cosine score", "field": "CosineScore", "sorter": "number", **fixed(),
     "headerTooltip": "The cosine similarity score comparing the observed and theoretical isotopic patterns."},
    {"title": "SNR", "field": "SNR", "sorter": "number", **fixed(),
     "headerTooltip": "The signal-to-noise ratio for the detected mass."},
    {"title": "QScore", "field": "QScore", "sorter": "number", **fixed(),
     "headerTooltip": "The quality score indicating the confidence of the mass detection (higher is better)."},
]


def settings(spectrum: str = "scan", mass: str = "mass", **overrides) -> dict:
    """Constructor arguments: rows of the spectrum in ``spectrum``, a click
    writes ``mass``. The first mass is highlighted but not picked until one is
    clicked."""
    return dict(
        column_definitions=COLUMNS, title="Mass Table",
        index_field="mass_idx", go_to_fields=["mass_idx"],
        filters={spectrum: "scan_idx"}, interactivity={mass: "mass_idx"},
        default_row_selects=False,
        **BROWSE,
    ) | overrides
