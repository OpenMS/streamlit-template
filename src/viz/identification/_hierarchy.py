"""What the protein, proteoform and PrSM tables share: how they browse,
their height and the mass shift filter."""

from __future__ import annotations

from src.viz.columns import BROWSE, hide_fields

# Without a decoy search there are no q-values; their columns are hidden
QVALUE_FIELDS = ("best_qvalue", "qvalue", "best_protein_qvalue", "protein_qvalue")

# Rows of 33 px below the title bar and header
CHROME = 100
ROW = 33
# Browsed, not glanced at: up to 15 rows
HEIGHT = CHROME + 15 * ROW

# Picking a PrSM forgets the tag, residue and mass picked for the last one
ON_SELECT = {"tag": None, "aa": None, "mass": None}

COMMON = dict(
    **BROWSE,
    # Columns share the cell's width, so a narrow cell never scrolls sideways
    layout="fitColumns",
    # Stay at the shared height, whatever the rows
    fill_height=True,
)


def height(most_rows: int) -> int:
    """The tables' shared height: that of the level with the most rows it can
    show at once, so tables side by side line up."""
    return min(HEIGHT, CHROME + ROW * max(most_rows, 1))


def columns(definitions: list[dict], with_qvalues: bool) -> list[dict]:
    return definitions if with_qvalues else hide_fields(definitions, QVALUE_FIELDS)


def shift_filter(filters: dict, all_rows=None, mass_shift: str = "mass_shift") -> dict:
    """``filters`` and, when Insight has an "all rows" default (``all_rows``),
    the rows carrying the picked mass shift (column ``shift_ids``)."""
    if all_rows is None:
        return dict(filters=filters) if filters else {}
    return dict(filters={**filters, mass_shift: "shift_ids"},
                filter_defaults={mass_shift: all_rows})
