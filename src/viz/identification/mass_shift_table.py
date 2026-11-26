"""Mass shifts: the recurring mass shifts of the identifications with how
many spectrum matches (and, where given, distinct entries such as proteoforms)
carry each, and the Unimod modifications they match. Clicking a shift picks it,
clicking it again unpicks it.

Insight component: ``Table``. Columns: ``shift_id``, ``shift``, the count
column (``prsms`` by default), optionally the entry column (``proteoforms`` by
default), ``interpretation``, ``unimod``, ``deviation``, ``residues``, ``other``.
"""

from __future__ import annotations

from src.viz.columns import SCROLL, fixed

COMPONENT = "Table"


def columns(tolerance: float, count: tuple = ("prsms", "PrSMs"),
            entries: tuple | None = ("proteoforms", "Proteoforms")) -> list[dict]:
    """The columns; ``tolerance`` (Da) is how close a Unimod match is,
    ``count`` the (field, title) of the spectrum-match count and ``entries``
    that of the distinct entries, None to leave it out."""
    return [
        {"title": "Shift (Da)", "field": "shift", "sorter": "number", "hozAlign": "right", **fixed(4),
         "headerTooltip": "Median of the mass shifts in this group."},
        {"title": count[1], "field": count[0], "sorter": "number", "hozAlign": "right", "width": 80},
        *([{"title": entries[1], "field": entries[0], "sorter": "number", "hozAlign": "right", "width": 110}]
          if entries else []),
        {"title": "Interpretation", "field": "interpretation", "widthGrow": 2, "tooltip": True,
         "headerTooltip": "Closest common Unimod modification of this mass, "
                          f"within {tolerance * 1000:g} mDa; "
                          "a match after missing the monoisotopic peak says so."},
        {"title": "Unimod Δ (Da)", "field": "unimod", "sorter": "number", "hozAlign": "right", **fixed(4)},
        {"title": "Deviation (mDa)", "field": "deviation", "sorter": "number", "hozAlign": "right", **fixed(1)},
        {"title": "Residues", "field": "residues", "tooltip": True,
         "headerTooltip": "Residues the modification is defined on in Unimod."},
        {"title": "Other matches", "field": "other", "widthGrow": 2, "tooltip": True},
    ]


def height(shifts: int, most: int = 376) -> int:
    """As tall as its rows, at most ``most`` px."""
    return min(most, 90 + 34 * shifts)


def settings(tolerance: float, mass_shift: str = "mass_shift", count: tuple = ("prsms", "PrSMs"),
             entries: tuple | None = ("proteoforms", "Proteoforms"), **overrides) -> dict:
    return dict(
        column_definitions=columns(tolerance, count, entries),
        index_field="shift_id", interactivity={mass_shift: "shift_id"},
        title="Mass shifts", initial_sort=[{"column": count[0], "dir": "desc"}],
        reclick="deselect", default_row=-1, scroll_position=SCROLL, layout="fitColumns",
    ) | overrides
