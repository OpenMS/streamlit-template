"""Matches of the picked mass shift: the spectrum matches (PSMs or PrSMs)
carrying the shift picked in the mass shift histogram or table, best score
first.

Insight component: ``Table``. Columns: ``match_id``, ``shift_id``,
``sequence``, ``delta``, ``charge``, ``mz``, ``rt``, ``score``, ``file``.
"""

from __future__ import annotations

from src.viz.columns import fixed


def _number(precision: int) -> dict:
    return {"sorter": "number", "hozAlign": "right", **fixed(precision)}

COMPONENT = "Table"

COLUMNS = [
    {"field": "sequence", "title": "Sequence"},
    {"field": "delta", "title": "Δ (Da)", **_number(4)},
    {"field": "charge", "title": "Z", "sorter": "number"},
    {"field": "mz", "title": "m/z", **_number(4)},
    {"field": "rt", "title": "RT", **_number(1)},
    {"field": "score", "title": "Score", "sorter": "number"},
    {"field": "file", "title": "File"},
]


def settings(mass_shift: str = "mass_shift", noun: str = "PSMs", ascending: bool = True, **overrides) -> dict:
    """``ascending`` says whether a lower score is better (an error probability)."""
    return dict(
        column_definitions=COLUMNS, filters={mass_shift: "shift_id"}, index_field="match_id",
        title=f"{noun} of the selected shift",
        initial_sort=[{"column": "score", "dir": "asc" if ascending else "desc"}],
    ) | overrides
