"""Proteins: the identified proteins of a run with their coverage, peptides,
PSMs, replicates and contaminant mark; contaminants hidden by a switch, a
search over accession, gene and name. A click picks the protein, which
narrows the peptides and PSMs.

Insight component: ``Table`` (columns generated from the frame). Columns:
``accession``, ``gene``, ``description``, ``coverage (%)``, ``contaminant``,
``not_contaminant``, ``replicates`` and counts.
"""

from __future__ import annotations

COMPONENT = "Table"

HIDDEN = {"visible": False}


def decimals(n: int) -> dict:
    return {"formatter": "money", "formatterParams": {"thousand": False, "precision": n}}


def settings(fields: list[str], numeric_filters=None, protein: str = "protein", title: str = "Proteins",
             **overrides) -> dict:
    """Arguments of a generated-columns Table over a frame with ``fields``;
    ``column_overrides`` amends the generated columns."""
    replicates = (
        {"replicates": {"headerTooltip": "Most files of one condition with a PSM of this protein"}}
        if "replicates" in fields else {}
    )
    return dict(
        title=title, interactivity={protein: "accession"},
        column_overrides={
            "coverage (%)": decimals(1),
            "contaminant": {"formatter": "tickCross", "sorter": "boolean", "visible": False},
            "not_contaminant": HIDDEN, **replicates,
        },
        toggle_filters=[{"label": "Hide contaminants", "column": "not_contaminant", "default": True}],
        search=[c for c in ("accession", "gene", "description") if c in fields],
        search_placeholder="Accession, gene or name",
        **({"numeric_filters": numeric_filters} if numeric_filters is not None else {}),
    ) | overrides
