"""PSM map: every peptide-spectrum match as a point at its retention time and
precursor m/z, coloured by score. A click picks the PSM.

Insight component: ``Heatmap``. Columns: ``id_idx``, ``rt``, ``mz``, ``score``.
"""

from __future__ import annotations

COMPONENT = "Heatmap"


def settings(psm: str = "identification", **overrides) -> dict:
    return dict(x_column="rt", y_column="mz", intensity_column="score", interactivity={psm: "id_idx"}) | overrides
