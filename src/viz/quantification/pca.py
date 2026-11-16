"""Sample similarity (PCA) over the most variable entries, samples coloured by group.

Contract: a wide table with an id column and one column per sample, and
``groups``, sample -> group. Samples without a group are left out.
"""

from __future__ import annotations

import polars as pl

from src.viz.plumbing import as_polars, fingerprint, group_colors, zoom_args

TOP_ENTRIES = 500
MIN_SAMPLES = 3


def most_variable(data, samples: list[str], top: int = TOP_ENTRIES, id_column: str | None = None) -> pl.DataFrame:
    """The ``top`` rows of ``data`` whose values vary most across ``samples``
    (the id column, when named, and the sample columns). Rows with a missing
    or infinite value in any sample are left out: a PCA cannot take them."""
    frame = as_polars(data).with_columns([pl.col(s).cast(pl.Float64) for s in samples])
    frame = frame.filter(pl.all_horizontal([pl.col(s).is_not_null() & pl.col(s).is_finite() for s in samples]))
    columns = ([id_column] if id_column else []) + list(samples)
    variance = frame.select(pl.concat_list([pl.col(s) for s in samples]).list.var().alias("_v"))
    return (frame.select(columns).with_columns(variance["_v"])
            .sort("_v", descending=True, nulls_last=True).head(top).drop("_v"))


def sample_metadata(groups: dict, samples=None) -> pl.DataFrame:
    """``sample_id``, ``group``: the metadata a PCA or clustered heatmap colours samples by."""
    samples = list(groups) if samples is None else [s for s in samples if s in groups]
    return pl.DataFrame({"sample_id": [str(s) for s in samples], "group": [str(groups[s]) for s in samples]},
                        schema={"sample_id": pl.String, "group": pl.String})


def pca_settings(groups: dict, samples=None, *, n_components: int | None = None,
                 title: str = "Sample similarity (PCA)") -> dict:
    """The ``PCAPlot`` arguments (besides data and cache)."""
    metadata = sample_metadata(groups, samples)
    return dict(
        metadata=metadata, sample_id_field="sample_id", group_field="group",
        n_components=n_components or min(5, metadata.height), title=title,
        group_colors=group_colors(metadata["group"].to_list()),
    )


def pca_component(data, groups: dict, name: str = "pca", *, cache_path, samples=None,
                  zoom: str | None = None, **settings):
    """The ``PCAPlot`` of ``data`` (cached by its content), not drawn yet, so the
    caller can read its components (``get_pc_columns``) and set its toolbar.
    Raises ``ValueError`` when the PCA cannot be computed."""
    from openms_insight import PCAPlot

    frame = as_polars(data)
    arguments = pca_settings(groups, samples, **settings)
    stamp = fingerprint(frame, arguments["metadata"].rows(), arguments["title"], arguments["n_components"])
    return PCAPlot(cache_id=f"{name}-{stamp}", cache_path=str(cache_path), data=frame.lazy(),
                   **zoom_args(PCAPlot, zoom), **arguments)
