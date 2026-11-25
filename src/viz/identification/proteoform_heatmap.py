"""Proteoform map: every PrSM as a point at its retention time and proteoform
mass, coloured by score. A click picks the PrSM in the protein, proteoform and
PrSM tables; a box or lasso picks the proteins of the PrSMs in it.

Insight component: ``Heatmap``. Columns: ``rt``, ``mass``, ``score``,
``index`` (the PrSM), ``scan_idx``, ``proteoform_id``, ``protein_group``,
``accession``, ``label`` (the hover text).
"""

from __future__ import annotations

from src.viz.identification._hierarchy import ON_SELECT

COMPONENT = "Heatmap"


def settings(prsms: int, prsm: str = "protein", spectra=("pscan", "scan"), proteoform: str = "proteoform",
             protein_group: str = "protein_group", protein_set: str | None = None,
             min_points: int = 20000, **overrides) -> dict:
    """Constructor arguments of the map of ``prsms`` PrSMs."""
    return dict(
        x_column="rt", y_column="mass", intensity_column="score",
        interactivity={prsm: "index", **{s: "scan_idx" for s in spectra},
                       proteoform: "proteoform_id", protein_group: "protein_group"},
        on_select=ON_SELECT, highlight={prsm: "index"},
        **({"multi_select": {protein_set: "accession"}} if protein_set else {}),
        hover_column="label",
        title=f"Proteoform Heatmap ({prsms} PrSMs)",
        x_label="Retention Time", y_label="Proteoform Mass",
        colorscale="Portland", log_scale=False, intensity_label="Score",
        min_points=min_points, downsample_zoomed=False,
        svg_filename="proteoform-heatmap", scroll_zoom=False,
    ) | overrides
