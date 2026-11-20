"""Picked entry per run: the entry picked in a comparison in every run or
sample, with its raw abundance, condition, how its value was obtained (status)
and its match score and q-value.

Insight component: ``Table``. Columns: ``RowIndex``, the entry's identifier
column, ``Run``, ``Condition``, ``Abundance``, ``Status``, ``MatchScore`` and
``MatchQvalue``.
"""

from __future__ import annotations

from src.viz.columns import RECLICK, fixed

COMPONENT = "Table"

SCIENTIFIC = {"formatter": "scientific", "formatterParams": {"precision": 3}}
ABUNDANCE_HELP = "Raw signal, before normalization; summed over the features of an entry."
STATUS_HELP = ("detected: found in this run. transferred: measured where another run found it "
               "(match between runs); identified: and an identification of this run confirms it.")


def settings(noun: str, sample_noun: str = "Run", selection: str = "entry", id_column: str = "ConsensusIndex",
             abundance_help: str = ABUNDANCE_HELP, status_help: str = STATUS_HELP, **overrides) -> dict:
    """Constructor arguments, the data left out; the table shows the entry
    picked under ``selection``."""
    return dict(
        column_definitions=[
            {"title": sample_noun, "field": "Run", "sorter": "string"},
            {"title": "Condition", "field": "Condition", "sorter": "string"},
            {"title": "Abundance", "field": "Abundance", "sorter": "number", **SCIENTIFIC,
             "headerTooltip": abundance_help},
            {"title": "Status", "field": "Status", "sorter": "string", "headerTooltip": status_help},
            {"title": "Match score", "field": "MatchScore", "sorter": "number", **fixed(3)},
            {"title": "Match q-value", "field": "MatchQvalue", "sorter": "number", **SCIENTIFIC},
        ],
        title=f"Selected {noun} per {sample_noun.lower()}", index_field="RowIndex",
        filters={selection: id_column}, go_to_fields=[], reclick=RECLICK, pagination=False,
    ) | overrides


# Few rows of several columns: all of them shown, never folded into rows
RENDER = {"collapse_columns": False}
