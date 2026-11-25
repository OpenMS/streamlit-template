"""Identification steps: how many MS2 spectra of a run are left after each step
from acquisition to the identifications kept at the FDR cut-off, with the
share of all MS2 spectra and, where a step loses more than usual, its likely
cause. Read top to bottom, it says where a run with few identifications lost
its spectra.

Insight component: ``Table``. Columns: ``row`` (the step's position),
``step``, ``spectra``, ``share`` (percent of the run's MS2 spectra), ``cause``
(empty where nothing stands out).
"""

from __future__ import annotations

from src.viz.columns import fixed

COMPONENT = "Table"


def columns(max_causes: int = 3) -> list[dict]:
    """The columns; ``max_causes`` is how many causes the source names at most."""
    return [
        {'title': 'Step', 'field': 'step', 'hozAlign': 'left', 'widthGrow': 3, 'headerSort': False},
        {'title': 'MS2 spectra', 'field': 'spectra', 'hozAlign': 'right', 'minWidth': 120,
         'widthGrow': 1, 'headerSort': False},
        {'title': '% of MS2', 'field': 'share', 'hozAlign': 'right', 'minWidth': 110, 'widthGrow': 1,
         'headerSort': False, **fixed(1),
         'headerTooltip': "Share of the run's MS2 spectra left after this step."},
        {'title': 'Likely cause', 'field': 'cause', 'formatter': 'textarea', 'hozAlign': 'left',
         'widthGrow': 7, 'headerSort': False,
         'headerTooltip': 'Named where a step loses more spectra than is usual, the most telling '
                          f'{max_causes} at most.'},
    ]


COLUMNS = columns()


def settings(title: str = "Identification diagnostics", max_causes: int = 3, **overrides) -> dict:
    """Constructor arguments: one row per step in their order, nothing picked."""
    return dict(
        column_definitions=columns(max_causes), title=title, index_field="row",
        layout="fitColumns", default_row=-1, fill_height=True, pagination=False,
    ) | overrides
