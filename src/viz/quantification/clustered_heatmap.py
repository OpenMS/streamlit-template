"""Clustered heatmap of row z-scores: entries and samples ordered by
similarity, with dendrograms, and samples marked by group.

Contract: a wide table of z-scores with an id column and one column per
sample (``steps.zscores`` makes it from abundances), and ``groups``,
sample -> group.
"""

from __future__ import annotations

from src.viz.plumbing import as_polars, fingerprint, group_colors
from src.viz.quantification.pca import sample_metadata
from src.viz.quantification.steps import zscores  # noqa: F401  pylint: disable=unused-import


def clustered_height(rows: int) -> int:
    """Room for the dendrograms and a readable label per row."""
    return max(600, min(1400, 300 + rows * 20))


def clustered_settings(groups: dict, id_column: str, samples=None, *, title: str,
                       x_label: str = "Samples", y_label: str = "Entries",
                       multi_select: dict | None = None) -> dict:
    """The ``ClusteredHeatmap`` arguments (besides data and cache)."""
    metadata = sample_metadata(groups, samples)
    settings = dict(
        id_col=id_column, metadata=metadata, row_cluster=True, col_cluster=True, title=title,
        x_label=x_label, y_label=y_label, intensity_label="Z-score",
        group_colors=group_colors(metadata["group"].to_list()),
    )
    if multi_select:
        settings["multi_select"] = multi_select
    return settings


def show_clustered_heatmap(data, groups: dict, id_column: str, name: str = "clustered-heatmap", *,
                           cache_path, key: str, state_manager=None, height: int | None = None,
                           help: str | None = None, toolbar_settings=None,  # pylint: disable=redefined-builtin
                           **settings):
    """Draw z-scores (``id_column`` and a column per sample) as a clustered heatmap."""
    from openms_insight import ClusteredHeatmap

    frame = as_polars(data)
    arguments = clustered_settings(groups, id_column, **settings)
    stamp = fingerprint(frame, arguments["metadata"].rows(), arguments["title"], arguments["y_label"],
                        sorted(arguments.get("multi_select", {}).items()))
    extra = {"toolbar_settings": toolbar_settings} if toolbar_settings else {}
    plot = ClusteredHeatmap(cache_id=f"{name}-{stamp}", cache_path=str(cache_path), data=frame.lazy(),
                            **arguments, **extra)
    plot(key=key, state_manager=state_manager, height=height or clustered_height(frame.height), help=help)
    return plot
