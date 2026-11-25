"""PrSMs of a proteoform: every spectrum matched to the picked proteoform with
its fragments, score and q-values. A click picks the PrSM and its spectrum.

Insight component: ``Table``. Columns: ``index`` (the PrSM), ``Scan``,
``RetentionTime``, ``PrecursorMass``, ``ProteoformMass``,
``MatchingFragments``, ``Score``, ``mass_shifts``, ``qvalue``,
``protein_qvalue``, ``proteoform_id``, ``scan_idx``, ``accession``,
``shift_ids``.
"""

from __future__ import annotations

from src.viz.columns import HIDDEN, MASS, QVALUE, fixed, threshold_filters
from src.viz.identification import _hierarchy

COMPONENT = "Table"

COLUMNS = [
    {"title": "Scan", "field": "Scan", "sorter": "number", "minWidth": 84},
    {"title": "RT", "field": "RetentionTime", "sorter": "number", **fixed(), **HIDDEN,
     "headerTooltip": "Retention time."},
    {"title": "Precursor", "field": "PrecursorMass", "sorter": "number", "minWidth": 110, **HIDDEN,
     "headerTooltip": "Precursor mass.", "formatter": "fixed",
     "formatterParams": {"precision": 4, "minLength": 4, "placeholders": {"-1": "-", "-1.0": "-"}}},
    {"title": "Proteoform mass", "field": "ProteoformMass", "sorter": "number", **MASS, **HIDDEN},
    {"title": "Fragments", "field": "MatchingFragments", "sorter": "number", "minWidth": 112,
     "headerTooltip": "Number of matched fragments."},
    {"title": "Score", "field": "Score", "sorter": "number", "minWidth": 92},
    {"title": "Mass shifts", "field": "mass_shifts", "widthGrow": 2, "tooltip": True, **HIDDEN,
     "headerTooltip": 'Mass shifts of the PrSM with the modification they match ("?": none).'},
    {"title": "q-value", "field": "qvalue", "sorter": "number", "minWidth": 96, **QVALUE,
     "headerTooltip": "Proteoform-level q-value. Only PrSMs at q ≤ 0.01 are counted."},
    {"title": "Protein q", "field": "protein_qvalue", "sorter": "number", "minWidth": 96, **QVALUE,
     **HIDDEN, "headerTooltip": "Protein-level q-value of its protein."},
]


def settings(title: str, with_qvalues: bool = True, table_cls=None, proteoform: str = "proteoform",
             prsm: str = "protein", spectra=("pscan", "scan"), protein_set: str | None = None,
             all_rows=None, **overrides) -> dict:
    """Constructor arguments: rows of the proteoform in ``proteoform``; a click
    writes the PrSM to ``prsm`` and its spectrum to each of ``spectra``."""
    extra = threshold_filters(table_cls, ("qvalue", "protein_qvalue")) \
        if with_qvalues and table_cls is not None else {}
    return dict(
        column_definitions=_hierarchy.columns(COLUMNS, with_qvalues), **extra,
        title=title, index_field="index", go_to_fields=["Scan"],
        **_hierarchy.shift_filter({proteoform: "proteoform_id"}, all_rows),
        interactivity={prsm: "index", **{s: "scan_idx" for s in spectra}},
        **({"multi_select": {protein_set: "accession"}} if protein_set else {}),
        on_select=_hierarchy.ON_SELECT, **_hierarchy.COMMON,
    ) | overrides
