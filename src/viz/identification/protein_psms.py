"""PSMs of the picked protein and peptide: the matches of the peptide picked
below the protein, with retention time, m/z, charge, score and file. A click
picks the PSM, whose annotated spectrum follows.

Insight component: ``Table`` (columns generated from the frame). Columns:
``accession``, ``peptide``, ``psm`` (hidden; filtered and picked on),
``RT (s)``, ``m/z`` and the rest.
"""

from __future__ import annotations

from src.viz.identification.protein_table import HIDDEN, decimals

COMPONENT = "Table"


def settings(protein: str = "protein", peptide: str = "peptide", psm: str = "psm", title: str = "PSMs",
             **overrides) -> dict:
    return dict(
        title=title, filters={protein: "accession", peptide: "peptide"}, interactivity={psm: "psm"},
        column_overrides={"accession": HIDDEN, "peptide": HIDDEN, "psm": HIDDEN,
                          "RT (s)": decimals(1), "m/z": decimals(4)},
    ) | overrides
