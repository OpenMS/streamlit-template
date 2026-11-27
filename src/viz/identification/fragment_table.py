"""Fragment table: the fragment ions a search assigned in the picked
spectrum, with their series, observed and expected m/z, error and relative
intensity. A click picks the fragment's peak in the fragment spectrum.

Insight component: ``Table``. Columns: ``fragment`` (the row), ``spectrum``
(the filter), ``peak``, ``ion``, ``series``, ``mz``, ``expected_mz``,
``error_ppm`` and ``intensity`` (relative, %).
"""

from __future__ import annotations

import copy

from src.viz.columns import BROWSE, fixed

COMPONENT = "Table"

COLUMNS = [
    {"field": "ion", "title": "Ion"},
    {"field": "series", "title": "Series"},
    {"field": "mz", "title": "m/z", "sorter": "number", **fixed(4)},
    {"field": "expected_mz", "title": "Expected m/z", "sorter": "number", **fixed(4)},
    {"field": "error_ppm", "title": "Error (ppm)", "sorter": "number", **fixed(2)},
    {"field": "intensity", "title": "Intensity (%)", "sorter": "number", **fixed(1)},
]


def columns() -> list[dict]:
    """A fresh copy of the columns for one Table."""
    return copy.deepcopy(COLUMNS)


def settings(spectrum: str = "spectrum", peak: str = "peak", **overrides) -> dict:
    """Constructor arguments, the data left out."""
    return dict(
        filters={spectrum: "spectrum"}, interactivity={peak: "peak"},
        column_definitions=columns(), index_field="fragment",
        initial_sort=[{"column": "mz", "dir": "asc"}],
        title="Fragment ions", **BROWSE,
    ) | overrides
