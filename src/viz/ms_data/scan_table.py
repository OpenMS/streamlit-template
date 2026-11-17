"""Scan table: one row per spectrum of a run, with its scan number, MS level,
retention time, precursor mass and how many masses it holds. A click selects
the spectrum.

Insight component: ``Table``. Columns: ``index`` (the spectrum's position),
``Scan``, ``MSLevel``, ``RT`` (s), ``PrecursorMass`` (Da), ``#Masses`` (or ``#Peaks``).
"""

from __future__ import annotations

from src.viz.columns import BROWSE, fixed

COMPONENT = "Table"

COLUMNS = [
    {"title": "Index", "field": "index", "sorter": "number",
     "headerTooltip": "The sequential index of the spectrum in the dataset."},
    {"title": "Scan Number", "field": "Scan", "sorter": "number",
     "headerTooltip": "The identifier of the mass spectrometry scan."},
    {"title": "MS Level", "field": "MSLevel", "sorter": "number",
     "headerTooltip": "The level of mass spectrometry analysis (e.g., MS1 or MS2)."},
    {"title": "Retention time", "field": "RT", "sorter": "number", **fixed(),
     "headerTooltip": "The time at which the spectrum was detected during the chromatographic separation in seconds."},
    {"title": "Precursor Mass", "field": "PrecursorMass", "sorter": "number", **fixed(),
     "headerTooltip": "The mass of the precursor ion selected for fragmentation in Daltons."},
    {"title": "#Masses", "field": "#Masses", "sorter": "number",
     "headerTooltip": "The number of detected masses in the spectrum."},
]


# A run that was not deconvolved counts the peaks of each spectrum instead
PEAKS = {"title": "#Peaks", "field": "#Peaks", "sorter": "number",
         "headerTooltip": "The number of peaks in the spectrum."}


def settings(spectrum: str = "scan", clears=("mass",), peaks: bool = False, **overrides) -> dict:
    """Constructor arguments: a click writes the spectrum's index to
    ``spectrum`` and clears ``clears`` (the mass picked in the last one).
    ``peaks``: the last column is ``#Peaks`` (peaks of the spectrum) in place
    of ``#Masses``."""
    columns = COLUMNS[:-1] + [PEAKS] if peaks else COLUMNS
    return dict(
        column_definitions=columns, title="Scan Table",
        index_field="index", go_to_fields=["index", "Scan"],
        interactivity={spectrum: "index"}, on_select={c: 0 for c in clears},
        **BROWSE,
    ) | overrides
