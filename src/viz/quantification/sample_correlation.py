"""Sample correlation: the Pearson correlation of the log intensities of
every two samples of a comparison, clustered; replicates should correlate
best.

Insight component: ``ClusteredHeatmap``. Data: a sample by sample matrix with
the sample in ``Sample`` and one column per sample.
"""

from __future__ import annotations

COMPONENT = "ClusteredHeatmap"


def settings(noun: str, sample_noun: str = "Run", metadata=None, group_colors=None, **overrides) -> dict:
    """Constructor arguments, the data left out; ``noun`` names the entries
    correlated (plural)."""
    return dict(
        id_col="Sample", metadata=metadata,
        title=f"Correlation of the {sample_noun.lower()}s (log2 intensities of {noun})",
        x_label=f"{sample_noun}s", y_label=f"{sample_noun}s", intensity_label="Pearson r",
        colorscale="Viridis", reversescale=False, group_colors=group_colors,
    ) | overrides
