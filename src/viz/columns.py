"""Column formats and table behaviour the library's tables share.

Plain dicts for Insight's ``Table(column_definitions=...)``: a component module
builds its columns from them, so numbers look the same in every table.
"""

from __future__ import annotations


def fixed(precision: int = 4) -> dict:
    """Four decimals (or ``precision``) for values longer than four characters,
    short values as they are."""
    return {"formatter": "fixed", "formatterParams": {"precision": precision, "minLength": 4}}


# -1 marks a value that was not determined; a missing value shows empty
DASH_FOR_MISSING = {"formatter": "fixed", "formatterParams": {"placeholders": {"-1": "-", "NaN": ""}, "minLength": 1000}}
BLANK_FOR_MISSING = {"formatter": "fixed", "formatterParams": {"placeholders": {"NaN": ""}, "minLength": 1000}}
# Masses in Da; a missing value shows "-"
MASS = {"formatter": "fixed", "formatterParams": {"precision": 4, "minLength": 4, "placeholders": {"NaN": "-"}}}
QVALUE = {"formatter": "fixed", "formatterParams": {"precision": 4, "minLength": 0, "placeholders": {"NaN": "-"}}}
POSITION = {"formatter": "fixed", "formatterParams": {"minLength": 1000, "placeholders": {"NaN": "-"}}}
# A column that starts hidden; the column chooser shows it
HIDDEN = {"visible": False}

# Clicking the highlighted row again only removes the highlight; the selection
# stays. A selected row is scrolled to the top, a clicked one only when cut off.
RECLICK = "unhighlight"
SCROLL = "top"
# How a browsed table behaves: every row in one scrolling list, the sort reset
# when its data changes, numbers as they are stored
BROWSE = dict(
    reclick=RECLICK, scroll_position=SCROLL, reset_sort=True, pagination=False,
    float_precision="float64",
)
# One table never exceeds this height (px)
TABLE_HEIGHT = 376


def hide_fields(columns: list[dict], fields) -> list[dict]:
    """``columns`` with those of ``fields`` hidden (a value the data lacks)."""
    fields = set(fields)
    return [{**c, "visible": False} if c["field"] in fields else c for c in columns]


def threshold_filters(table_cls, fields, thresholds=(0.01, 0.05)) -> dict:
    """One-sided number filters (``<=``) on ``fields`` with one-click
    thresholds, when the installed Insight ``Table`` takes them."""
    from src.viz.plumbing import accepts
    if not accepts(table_cls, "numeric_filters"):
        return {}
    return {"numeric_filters": {f: {"op": "<=", "suggestions": list(thresholds)} for f in fields}}
