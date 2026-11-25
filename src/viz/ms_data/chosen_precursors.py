"""Chosen precursors: every precursor an intelligent acquisition chose, newest
first, with its mass, charge, quality score, the scans commanded for it, the
best collision energy of an exploration and, once identified, its proteoform,
score and coverage. A click picks the precursor; a toggle keeps the identified.

Insight component: ``Table``. Columns: ``precursor``, ``RT``, ``Mass``, ``z``,
``QScore``, ``MS2/MS3``, ``Decisions``, ``Best energy``, ``Quant verdict``,
``Identified``, ``Score``, ``Coverage``, ``Proteoform``.
"""

from __future__ import annotations

COMPONENT = "Table"


def _fixed(precision=4):
    return {'formatter': 'fixed', 'formatterParams': {'precision': precision, 'minLength': 4}}


TICK = {'formatter': 'tickCross', 'hozAlign': 'center'}

COLUMNS = [
    {'title': '#', 'field': 'precursor', 'sorter': 'number',
     'headerTooltip': 'Precursors in the order they were chosen.'},
    {'title': 'RT', 'field': 'RT', 'sorter': 'number', **_fixed(2),
     'headerTooltip': 'Retention time (min) of the survey scan it was chosen from.'},
    {'title': 'Mass', 'field': 'Mass', 'sorter': 'number', **_fixed(),
     'headerTooltip': 'Monoisotopic mass.'},
    {'title': 'z', 'field': 'z', 'sorter': 'number'},
    {'title': 'QScore', 'field': 'QScore', 'sorter': 'number', **_fixed(3)},
    {'title': 'MS2/MS3', 'field': 'MS2/MS3',
     'headerTooltip': 'MS2 scans commanded for it / MS3 scans for its fragments.'},
    {'title': 'Scans for', 'field': 'Decisions',
     'headerTooltip': 'What its scans were for: recording, exploration, quantification, ...'},
    {'title': 'Best CE', 'field': 'Best energy', 'sorter': 'number',
     'headerTooltip': 'Energy of the winning variant of an exploration.'},
    {'title': 'Quant', 'field': 'Quant verdict',
     'headerTooltip': 'Quantification verdict.'},
    {'title': 'Identified', 'field': 'Identified', **TICK},
    {'title': 'Score', 'field': 'Score', 'sorter': 'number', **_fixed(0)},
    {'title': 'Cov. %', 'field': 'Coverage', 'sorter': 'number', **_fixed(1),
     'headerTooltip': 'Sequence coverage of the fragments pooled over its scans.'},
    {'title': 'Proteoform', 'field': 'Proteoform', 'hozAlign': 'left'},
]

HIDDEN = ['Identified']


def no_collapse(columns):
    """Columns that never fold into a row's details: a table too narrow for
    them scrolls instead."""
    return [{**c, 'responsive': 0} for c in columns]


def settings(selection: str = "precursor", page: str | None = None, **overrides) -> dict:
    """Constructor arguments; a click writes ``selection``. Pass
    ``hidden_columns=HIDDEN`` at render time."""
    arguments = dict(
        title='Chosen precursors', index_field='precursor',
        go_to_fields=['precursor', 'Mass'], interactivity={selection: 'precursor'},
        column_definitions=no_collapse(COLUMNS),
        initial_sort=[{'column': 'precursor', 'dir': 'desc'}],
        reclick='keep', scroll_position='top',
        toggle_filters=[{'label': 'Identified', 'column': 'Identified', 'default': False}],
    )
    if page:
        arguments['pagination_identifier'] = page
    return arguments | overrides
