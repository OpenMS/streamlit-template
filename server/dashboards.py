"""
OpenMS-Insight dashboards for the Svelte app's results pages.

Each function builds Insight components and renders them, exactly as it would
in a Streamlit results page; ``server/insight.py`` runs it outside Streamlit.
A ``ResultView("insight", ..., {"dashboard": "server.dashboards:<name>"})``
in ``server/workflows.py`` puts it on a results page.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl


def _cache_dir(workflow_dir: Path) -> Path:
    # Outside results/, so the cache is not offered as a result download
    return Path(workflow_dir, "cache", "insight")


def consensus_features(workflow_dir: Path) -> None:
    """Consensus feature table; clicking a feature plots its intensity per sample."""
    from openms_insight import LinePlot, StateManager, Table

    file = Path(workflow_dir, "results", "feature-linking", "feature_matrix.tsv")
    if not file.exists():
        return
    # A new run writes a new file, which gets a new cache
    stamp = f"{file.stat().st_mtime_ns:x}"
    cache = str(_cache_dir(workflow_dir))

    df = pd.read_csv(file, sep="\t")
    samples = [str(c) for c in df.columns[5:]]
    features = pl.from_pandas(df.rename(columns={c: c.replace(".", "_") for c in df.columns})).with_row_index(
        "feature_id"
    )
    columns = [
        {"field": c.replace(".", "_"), "title": c, "sorter": "number" if c != "metabolite" else "string"}
        for c in df.columns
    ]
    intensities = (
        features.select(["feature_id", *[s.replace(".", "_") for s in samples]])
        .unpivot(index="feature_id", variable_name="sample", value_name="intensity")
        .with_columns(
            pl.col("sample").replace_strict(
                {s.replace(".", "_"): i + 1 for i, s in enumerate(samples)}, return_dtype=pl.Int64
            ).alias("sample_index"),
            pl.col("sample").str.replace(r"_featureXML$", "").alias("sample_name"),
        )
    )

    state = StateManager()
    Table(
        cache_id=f"consensus-features-{stamp}",
        data=features.lazy(),
        cache_path=cache,
        interactivity={"feature": "feature_id"},
        column_definitions=columns,
        index_field="feature_id",
        title="Consensus features",
        initial_sort=[{"column": "quality", "dir": "desc"}],
    )(key="consensus-features", state_manager=state, height=460)
    LinePlot(
        cache_id=f"feature-intensities-{stamp}",
        data=intensities.lazy(),
        cache_path=cache,
        filters={"feature": "feature_id"},
        x_column="sample_index",
        y_column="intensity",
        annotation_column="sample_name",
        title="Intensity per sample",
        x_label="Sample",
        y_label="Intensity",
    )(key="feature-intensities", state_manager=state, height=360)
