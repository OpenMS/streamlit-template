"""PrSM masses: every deconvolved mass of the picked PrSM's spectrum and the
fragment ion it explains, with its mass errors; a toggle shows matched masses
only. A row picks its mass.

Insight component: ``Table``. Columns: ``mass_idx``, ``proteoform_index``
(the PrSM), ``mass_id``, ``MonoMass``, ``SumIntensity``, ``charges``,
``QScore``, ``status``, ``matched``, ``ions``, ``position``,
``theoretical_mass``, ``mass_error``, ``ppm_error``.
"""

from __future__ import annotations

from src.viz.columns import BROWSE, fixed

COMPONENT = "Table"

COLUMNS = [
    {'title': 'Mass ID', 'field': 'mass_id', 'sorter': 'number',
     'headerTooltip': 'The position of the mass in the deconvolved spectrum (1-based).'},
    {'title': 'Mono mass', 'field': 'MonoMass', 'sorter': 'number', **fixed(),
     'headerTooltip': 'The monoisotopic mass of the deconvolved mass in Daltons.'},
    {'title': 'Intensity', 'field': 'SumIntensity', 'sorter': 'number', **fixed(), 'responsive': 6,
     'headerTooltip': 'The total intensity of the mass across all isotopic peaks and charges.'},
    {'title': 'Charge', 'field': 'charges', 'responsive': 5,
     'headerTooltip': 'The charge states the mass was detected in.'},
    {'title': 'QScore', 'field': 'QScore', 'sorter': 'number', **fixed(), 'responsive': 8,
     'headerTooltip': 'The quality score of the mass detection (higher is better).'},
    {'title': 'Status', 'field': 'status', 'responsive': 0,
     'headerTooltip': 'Whether the mass matches a fragment ion of the proteoform. The table filter button shows only matched or only not matched masses.'},
    {'title': 'Ion', 'field': 'ions', 'responsive': 0,
     'headerTooltip': 'The fragment ion(s) the mass matches; the numbers to the right are those of the first one.'},
    {'title': 'Position', 'field': 'position', 'sorter': 'number', **fixed(0), 'responsive': 3,
     'headerTooltip': 'The residue next to the cleaved bond (1-based, in the database sequence).'},
    {'title': 'Theoretical mass', 'field': 'theoretical_mass', 'sorter': 'number', **fixed(), 'responsive': 4,
     'headerTooltip': 'The theoretical mass of the matched fragment ion in Daltons.'},
    {'title': 'Mass error (Da)', 'field': 'mass_error', 'sorter': 'number', **fixed(), 'responsive': 2,
     'headerTooltip': 'Observed minus theoretical mass in Daltons.'},
    {'title': 'Error (ppm)', 'field': 'ppm_error', 'sorter': 'number', **fixed(2), 'responsive': 0,
     'headerTooltip': 'Observed minus theoretical mass in parts per million.'},
]


def settings(title: str = "PrSM Mass Table", prsm: str = "protein", mass: str = "mass",
             **overrides) -> dict:
    """Constructor arguments: rows of the PrSM in ``prsm``; a row writes its
    mass to ``mass``."""
    return dict(
        column_definitions=COLUMNS, title=title,
        index_field="mass_idx", go_to_fields=["mass_id", "ions"],
        filters={prsm: "proteoform_index"},
        toggle_filters=[{"label": "Matched masses only", "column": "matched", "default": False}],
        interactivity={mass: "mass_idx"}, default_row_selects=False, **BROWSE,
    ) | overrides
