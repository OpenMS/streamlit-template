"""Peptides of the picked protein: the peptides identified for the protein
picked in the protein table, with their PSM counts. A click picks the
peptide, which narrows the PSMs.

Insight component: ``Table`` (columns generated from the frame). Columns:
``accession`` (hidden, filtered on), ``peptide`` and counts.
"""

from __future__ import annotations

from src.viz.identification.protein_table import HIDDEN

COMPONENT = "Table"


def settings(protein: str = "protein", peptide: str = "peptide", title: str = "Peptides", **overrides) -> dict:
    return dict(
        title=title, filters={protein: "accession"}, interactivity={peptide: "peptide"},
        column_overrides={"accession": HIDDEN},
    ) | overrides
