"""Proteoforms: the proteoforms of the picked protein with their mass shifts,
PrSM count, best score and q-values. A click picks the proteoform and its best
PrSM.

Insight component: ``Table``. Columns: ``proteoform_id``, ``proteoform``
(ProForma), ``start``, ``end``, ``mass``, ``modifications``, ``mass_shifts``,
``prsms``, ``best_score``, ``best_qvalue``, ``best_protein_qvalue``,
``protein_group``, ``best_index``, ``scan_idx``, ``accession``, ``shift_ids``.
"""

from __future__ import annotations

from src.viz.columns import HIDDEN, MASS, POSITION, QVALUE, threshold_filters
from src.viz.identification import _hierarchy

COMPONENT = "Table"

COLUMNS = [
    {"title": "#", "field": "proteoform_id", "sorter": "number", "width": 44,
     "headerTooltip": "Proteoforms numbered by protein, then by their best score."},
    {"title": "Proteoform", "field": "proteoform", "widthGrow": 3, "tooltip": True,
     "headerTooltip": "The proteoform in ProForma notation, as the search reports it."},
    {"title": "First residue", "field": "start", "sorter": "number", **POSITION, **HIDDEN,
     "headerTooltip": 'First residue of the proteoform in the protein (1-based); "-" when the N-terminus was not determined.'},
    {"title": "Last residue", "field": "end", "sorter": "number", **POSITION, **HIDDEN,
     "headerTooltip": 'Last residue of the proteoform in the protein (1-based); "-" when the C-terminus was not determined.'},
    {"title": "Mass", "field": "mass", "sorter": "number", **MASS, **HIDDEN,
     "headerTooltip": "Proteoform mass of its best PrSM."},
    {"title": "Mods", "field": "modifications", "sorter": "number", **HIDDEN},
    {"title": "Mass shifts", "field": "mass_shifts", "widthGrow": 2, "tooltip": True,
     "headerTooltip": 'Mass shifts of the proteoform with the modification they match ("?": none). '
                      "Pick a shift in the Mass shifts component to list the proteoforms carrying it."},
    {"title": "PrSMs", "field": "prsms", "sorter": "number", "minWidth": 92},
    {"title": "Score", "field": "best_score", "sorter": "number", **HIDDEN,
     "headerTooltip": "Best score of its PrSMs."},
    {"title": "q-value", "field": "best_qvalue", "sorter": "number", "minWidth": 96, **QVALUE,
     "headerTooltip": "Lowest proteoform-level q-value of its PrSMs. Only PrSMs at q ≤ 0.01 are counted."},
    {"title": "Protein q", "field": "best_protein_qvalue", "sorter": "number", "minWidth": 96, **QVALUE,
     **HIDDEN, "headerTooltip": "Protein-level q-value of its protein."},
]


def settings(title: str, with_qvalues: bool = True, table_cls=None, protein_group: str = "protein_group",
             proteoform: str = "proteoform", prsm: str = "protein", spectra=("pscan", "scan"),
             protein_set: str | None = None, all_rows=None, **overrides) -> dict:
    """Constructor arguments: rows of the protein in ``protein_group``; a click
    writes ``proteoform``, its best PrSM to ``prsm`` and that PrSM's spectrum to
    each of ``spectra``."""
    extra = threshold_filters(table_cls, ("best_qvalue", "best_protein_qvalue")) \
        if with_qvalues and table_cls is not None else {}
    return dict(
        column_definitions=_hierarchy.columns(COLUMNS, with_qvalues), **extra,
        title=title, index_field="proteoform_id", go_to_fields=["proteoform"],
        **_hierarchy.shift_filter({protein_group: "protein_group"}, all_rows),
        interactivity={proteoform: "proteoform_id", prsm: "best_index",
                       **{s: "scan_idx" for s in spectra}},
        **({"multi_select": {protein_set: "accession"}} if protein_set else {}),
        on_select=_hierarchy.ON_SELECT, **_hierarchy.COMMON,
    ) | overrides
