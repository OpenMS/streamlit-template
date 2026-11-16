"""Shared identifications: what every two runs of a comparison share (the
Jaccard index of the entities each detected, in %), clustered so that runs
alike sit together, the runs coloured by condition.

Insight component: ``ClusteredHeatmap``. Data: a run by run matrix with the
run in ``Sample`` and one column per run.
"""

from __future__ import annotations

COMPONENT = "ClusteredHeatmap"


def settings(noun: str, sample_noun: str = "Run", metadata=None, group_colors=None, **overrides) -> dict:
    """Constructor arguments, the data left out; ``metadata`` and
    ``group_colors`` colour the runs by condition."""
    return dict(
        id_col="Sample", metadata=metadata,
        title=f"Shared {noun} (% of those either {sample_noun.lower()} detected)",
        x_label=f"{sample_noun}s", y_label=f"{sample_noun}s", intensity_label="Shared (%)",
        colorscale="Blues", reversescale=True, group_colors=group_colors,
    ) | overrides
