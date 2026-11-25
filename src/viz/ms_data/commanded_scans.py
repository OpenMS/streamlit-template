"""Commanded scans: the MS2 and MS3 scans an intelligent acquisition commanded
for the picked precursor, with their status, what each was for, isolation,
activation and energy, the variant of an exploration and its winner, and what
was deconvolved and identified from the scan.

Insight component: ``Table``. Columns: ``scan``, ``precursor``, ``Scan``,
``Status``, ``Decision``, ``MS``, ``RT``, ``Fragment``, ``Mass``, ``z``,
``m/z``, ``Width``, ``Activation``, ``Energy``, ``Variant``,
``Exploration score``, ``Winner``, ``Masses``, ``Tags``, ``Quant verdict``,
``Score``, ``Proteoform``, ``QScore``, ``Priority``, ``Parent``.
"""

from __future__ import annotations

from src.viz.ms_data.chosen_precursors import TICK, _fixed, no_collapse

COMPONENT = "Table"

COLUMNS = [
    {'title': 'Scan', 'field': 'Scan', 'headerTooltip': 'Id of the commanded scan.'},
    {'title': 'Status', 'field': 'Status'},
    {'title': 'Decision', 'field': 'Decision'},
    {'title': 'MS', 'field': 'MS', 'sorter': 'number'},
    {'title': 'RT', 'field': 'RT', 'sorter': 'number', **_fixed(2),
     'headerTooltip': 'Retention time (min) of the acquired scan.'},
    {'title': 'Fragment', 'field': 'Fragment',
     'headerTooltip': 'Fragment ion isolated for an MS3 scan.'},
    {'title': 'Mass', 'field': 'Mass', 'sorter': 'number', **_fixed()},
    {'title': 'z', 'field': 'z', 'sorter': 'number'},
    {'title': 'm/z', 'field': 'm/z', 'sorter': 'number', **_fixed()},
    {'title': 'Width', 'field': 'Width', 'sorter': 'number', **_fixed(2),
     'headerTooltip': 'Isolation width (Th).'},
    {'title': 'Activation', 'field': 'Activation'},
    {'title': 'Energy', 'field': 'Energy', 'sorter': 'number'},
    {'title': 'Variant', 'field': 'Variant',
     'headerTooltip': 'Variant of an exploration (e.g. a collision energy step).'},
    {'title': 'Expl. score', 'field': 'Exploration score', 'sorter': 'number', **_fixed(2)},
    {'title': 'Winner', 'field': 'Winner', **TICK,
     'headerTooltip': 'The variant the exploration chose.'},
    {'title': 'Masses', 'field': 'Masses', 'sorter': 'number',
     'headerTooltip': 'Masses deconvolved from the scan.'},
    {'title': 'Tags', 'field': 'Tags', 'sorter': 'number'},
    {'title': 'Quant', 'field': 'Quant verdict'},
    {'title': 'Score', 'field': 'Score', 'sorter': 'number', **_fixed(0)},
    {'title': 'Proteoform', 'field': 'Proteoform', 'hozAlign': 'left'},
    {'title': 'QScore', 'field': 'QScore', 'sorter': 'number', **_fixed(3)},
    {'title': 'Priority', 'field': 'Priority', 'sorter': 'number'},
    {'title': 'Parent', 'field': 'Parent',
     'headerTooltip': 'The scan this one was decided from.'},
]

HIDDEN = ['m/z', 'Width', 'Exploration score', 'Tags', 'Quant verdict', 'QScore',
          'Priority', 'Parent']


def settings(selection: str = "precursor", page: str | None = None, **overrides) -> dict:
    """Constructor arguments: the scans of the precursor in ``selection``. Pass
    ``hidden_columns=HIDDEN`` at render time."""
    arguments = dict(
        title='Scans commanded for the precursor', index_field='scan',
        filters={selection: 'precursor'}, column_definitions=no_collapse(COLUMNS),
        reclick='keep', scroll_position='top', default_row_selects=False,
    )
    if page:
        arguments['pagination_identifier'] = page
    return arguments | overrides
