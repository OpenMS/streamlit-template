"""Sequence tags: the tags of the selected spectrum with their position in
the protein, sequence, score and flanking masses, sorted by score. Picking a
residue lists the tags covering it; a click picks the tag.

Insight component: ``Table``. Columns: ``TagIndex``, ``scan_idx``, ``Scan``,
``StartPos``, ``EndPos``, ``TagSequence``, ``Length``, ``Score``, ``Nmass``,
``Cmass``, ``DeltaMass``. Pass the rows sorted by score.
"""

from __future__ import annotations

from src.viz.columns import BLANK_FOR_MISSING, BROWSE, DASH_FOR_MISSING

COMPONENT = "Table"

COLUMNS = [
    {'title': 'Scan Number', 'field': 'Scan', 'sorter': 'number',
     'headerTooltip': 'The identifier of the mass spectrometry scan containing the sequence tag.'},
    {'title': 'Start Position', 'field': 'StartPos', 'sorter': 'number', **BLANK_FOR_MISSING,
     'headerTooltip': 'The position in the protein sequence where the sequence tag begins.'},
    {'title': 'End Position', 'field': 'EndPos', 'sorter': 'number', **BLANK_FOR_MISSING,
     'headerTooltip': 'The position in the protein sequence where the sequence tag ends.'},
    # FLASHTnT also reports long de novo tags (hundreds of residues)
    {'title': 'Sequence', 'field': 'TagSequence', 'sorter': 'string', 'maxWidth': 240,
     'tooltip': True, 'headerTooltip': 'The amino acid sequence of the identified tag.'},
    {'title': 'Length', 'field': 'Length', 'sorter': 'number',
     'headerTooltip': 'The number of amino acids in the sequence tag.'},
    {'title': 'Tag Score', 'field': 'Score', 'sorter': 'number',
     'headerTooltip': 'A score indicating the confidence of the sequence tag identification (higher is better).'},
    {'title': 'N mass', 'field': 'Nmass', 'sorter': 'number', **DASH_FOR_MISSING,
     'headerTooltip': 'The N-terminal mass offset from the start of the sequence tag in Daltons.'},
    {'title': 'C mass', 'field': 'Cmass', 'sorter': 'number', **DASH_FOR_MISSING,
     'headerTooltip': 'The C-terminal mass offset from the end of the sequence tag in Daltons.'},
    {'title': 'Δ mass', 'field': 'DeltaMass', 'sorter': 'number', **BLANK_FOR_MISSING,
     'headerTooltip': 'Delta mass is the difference between the tag flanking mass and the (partial) proteoform mass, from its terminal to the tag boundary.'},
]


def settings(title: str = "Tag Table", spectrum: str = "scan", residue: str = "aa",
             tag: str = "tag", mass: str = "mass", prsm: str = "protein", **overrides) -> dict:
    """Constructor arguments: rows of the spectrum in ``spectrum`` covering the
    residue in ``residue``; a click writes ``tag`` and forgets ``mass``."""
    return dict(
        column_definitions=COLUMNS, title=title,
        index_field="TagIndex", go_to_fields=["Scan", "StartPos", "EndPos", "TagSequence"],
        filters={spectrum: "scan_idx"}, range_filters={residue: ["StartPos", "EndPos"]},
        interactivity={tag: "TagIndex"}, on_select={mass: None},
        **BROWSE, reset_sort_on=[prsm],
    ) | overrides
