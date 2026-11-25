"""Proteins: one row per identified protein with its proteoform and PrSM
counts, best score and q-values. A click picks the protein; the proteoform
table lists its proteoforms.

Insight component: ``Table``. Columns: ``protein_group``, ``accession``,
``description``, ``mass_shifts``, ``proteoforms``, ``prsms``, ``best_score``,
``best_qvalue``, ``best_protein_qvalue``, ``shift_ids``.
"""

from __future__ import annotations

from src.viz.columns import HIDDEN, QVALUE, threshold_filters
from src.viz.identification import _hierarchy

COMPONENT = "Table"

COLUMNS = [
    {"title": "#", "field": "protein_group", "sorter": "number", "width": 44,
     "headerTooltip": "Proteins numbered by their best score."},
    {"title": "Accession", "field": "accession", "widthGrow": 2, "tooltip": True},
    {"title": "Description", "field": "description", **HIDDEN},
    {"title": "Mass shifts", "field": "mass_shifts", "widthGrow": 2, "tooltip": True, **HIDDEN,
     "headerTooltip": 'Mass shifts of its proteoforms with the modification they match ("?": none).'},
    {"title": "Forms", "field": "proteoforms", "sorter": "number", "minWidth": 92,
     "headerTooltip": "Number of distinct proteoforms (ProForma strings) identified for the protein."},
    {"title": "PrSMs", "field": "prsms", "sorter": "number", "minWidth": 92,
     "headerTooltip": "Number of spectra whose best hit is a proteoform of the protein."},
    {"title": "Score", "field": "best_score", "sorter": "number", "minWidth": 92, **HIDDEN,
     "headerTooltip": "Best score of its PrSMs."},
    {"title": "q-value", "field": "best_qvalue", "sorter": "number", "minWidth": 96, **QVALUE,
     "headerTooltip": "Lowest proteoform-level q-value of its PrSMs. Only PrSMs at q ≤ 0.01 are counted."},
    {"title": "Protein q", "field": "best_protein_qvalue", "sorter": "number", "minWidth": 96, **QVALUE,
     "headerTooltip": "Protein-level q-value: the estimated share of false proteins among proteins "
                      "scoring at least as well."},
]


def settings(title: str, with_qvalues: bool = True, table_cls=None, protein_group: str = "protein_group",
             protein_set: str | None = None, all_rows=None, **overrides) -> dict:
    """Constructor arguments. ``protein_set`` names the selection a multi-row
    pick writes the accessions to; ``table_cls`` the installed Insight
    ``Table`` (q-value filters where it takes them)."""
    extra = threshold_filters(table_cls, ("best_qvalue", "best_protein_qvalue")) \
        if with_qvalues and table_cls is not None else {}
    return dict(
        column_definitions=_hierarchy.columns(COLUMNS, with_qvalues), **extra,
        title=title, index_field="protein_group", go_to_fields=["accession"],
        interactivity={protein_group: "protein_group"},
        **({"multi_select": {protein_set: "accession"}} if protein_set else {}),
        **_hierarchy.shift_filter({}, all_rows), **_hierarchy.COMMON,
    ) | overrides
