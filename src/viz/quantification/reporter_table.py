"""Reporter ions: the spectra of an isobarically labelled run with their
retention time, precursor mass and how many labels carry a reporter ion, and,
for an identified run, the protein each was identified as. A click picks the
spectrum.

Insight component: ``Table``. Columns: ``scan_idx``, ``Scan``, ``RT``,
``PrecursorMass``, ``QuantifiedChannels``, ``Identified`` (with
identifications).
"""

from __future__ import annotations

from src.viz.columns import BROWSE, fixed

COMPONENT = "Table"


def columns(identified: bool) -> list[dict]:
    """The spectrum and how many labels it carries; the intensity of each label
    is in the reporter ion plot, not one column per label."""
    cols = [
        {"title": "Scan", "field": "Scan", "sorter": "number"},
        {"title": "RT (min)", "field": "RT", "sorter": "number", **fixed(2)},
        {"title": "Precursor mass", "field": "PrecursorMass", "sorter": "number", **fixed(2),
         "headerTooltip": "Monoisotopic mass of the precursor, in Daltons."},
        {"title": "Labels found", "field": "QuantifiedChannels", "sorter": "number",
         "headerTooltip": "How many labels have a reporter ion in the spectrum."},
    ]
    if identified:
        cols.append({"title": "Identified as", "field": "Identified", "sorter": "string",
                     "headerTooltip": "The protein of the best PrSM of the spectrum."})
    return cols


def settings(label: str, identified: bool = False, spectrum: str = "scan", **overrides) -> dict:
    """Constructor arguments; ``label`` names the labels (TMT 16plex, ...)."""
    return dict(
        column_definitions=columns(identified), title=f"Reporter ions ({label})",
        index_field="scan_idx", go_to_fields=["Scan"], interactivity={spectrum: "scan_idx"},
        **BROWSE,
    ) | overrides
