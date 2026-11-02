"""Example of a configurable dashboard (src/common/dashboard).

Shows the quantification dashboard of docs/quantification-spec.md on made-up
data. The panels here use Plotly so the template stays free of openms-insight;
an app registers panels that draw openms-insight components instead, with the
same names, so its layouts follow the spec.
"""

import math

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.common.common import page_setup, show_fig, show_table
from src.common.dashboard.quant import (
    DASHBOARD_NAME,
    QUANT_DEFAULT_LAYOUT,
    quant_panels,
)
from src.common.dashboard.ui import layout_editor, render_dashboard

page_setup()

st.title("Dashboard")
st.markdown(
    "A dashboard shows several views of one result on one page. Which panels appear, "
    "and where, is set under **Arrange panels** and saved with the workspace. This "
    "example compares two made-up groups of samples, as a quantification app would."
)

SAMPLES = ["control_1", "control_2", "control_3", "treated_1", "treated_2", "treated_3"]
GROUPS = {s: s.split("_")[0] for s in SAMPLES}


@st.cache_data
def example_comparison(n_rows: int = 300, n_changed: int = 20, seed: int = 3):
    """Made-up abundances and a Welch test between the two groups."""
    rng = np.random.default_rng(seed)
    base = rng.lognormal(16, 1.5, n_rows)
    changed = np.ones(n_rows)
    changed[:n_changed] = rng.choice([0.25, 4.0], n_changed)
    table = pd.DataFrame({"id": [f"Protein {i + 1}" for i in range(n_rows)]})
    for sample in SAMPLES:
        fold = changed if GROUPS[sample] == "treated" else 1.0
        values = base * fold * rng.lognormal(0, 0.15, n_rows)
        values[rng.random(n_rows) < 0.03] = np.nan
        table[sample] = values

    log = np.log2(table[SAMPLES])
    log = log - log.median() + log.median().mean()
    a = log[[s for s in SAMPLES if GROUPS[s] == "control"]]
    b = log[[s for s in SAMPLES if GROUPS[s] == "treated"]]
    diff = b.mean(axis=1) - a.mean(axis=1)
    se = np.sqrt(a.var(axis=1) / a.count(axis=1) + b.var(axis=1) / b.count(axis=1))
    stat = diff / se
    # normal approximation of the t distribution: enough for an example
    p = stat.abs().map(lambda t: math.erfc(t / math.sqrt(2)) if np.isfinite(t) else np.nan)
    # Benjamini-Hochberg
    ranked = p.dropna().sort_values()
    adjusted = (ranked * len(ranked) / np.arange(1, len(ranked) + 1))[::-1].cummin()[::-1]
    padj = adjusted.clip(upper=1).reindex(p.index)
    stats = pd.DataFrame(
        {"id": table["id"], "log2FC": diff, "p-value": p, "p-adj": padj, "stat": stat}
    ).sort_values("p-value")
    return table, log.assign(id=table["id"]), stats


table, normalized, stats = example_comparison()
significant = (stats["p-adj"] <= 0.05) & (stats["log2FC"].abs() >= 1)


def key_figures(ctx):
    up = int((significant & (ctx["stats"]["log2FC"] > 0)).sum())
    down = int((significant & (ctx["stats"]["log2FC"] < 0)).sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Compared", len(ctx["stats"]))
    c2.metric("Higher in treated", up)
    c3.metric("Lower in treated", down)


def volcano(ctx):
    df = ctx["stats"].assign(
        **{
            "-log10(p-adj)": -np.log10(ctx["stats"]["p-adj"]),
            "Change": np.where(
                significant,
                np.where(ctx["stats"]["log2FC"] > 0, "Up", "Down"),
                "Not significant",
            ),
        }
    )
    fig = px.scatter(
        df, x="log2FC", y="-log10(p-adj)", color="Change", hover_name="id",
        color_discrete_map={"Up": "#E74C3C", "Down": "#3498DB", "Not significant": "#95A5A6"},
        title="Volcano plot",
    )
    show_fig(fig, "volcano")


def statistics_table(ctx):
    st.markdown("**Statistics**")
    choice = st.selectbox(
        "Show the abundance of", ctx["stats"]["id"].head(50), key="dashboard_example_pick"
    )
    ctx["selected"] = choice
    show_table(ctx["stats"].head(50).round(4), "statistics")


def abundance_per_sample(ctx):
    selected = st.session_state.get("dashboard_example_pick") or ctx["stats"]["id"].iloc[0]
    row = ctx["normalized"].set_index("id").loc[selected, SAMPLES]
    df = pd.DataFrame({"Sample": SAMPLES, "log2 abundance": row.values, "Group": [GROUPS[s] for s in SAMPLES]})
    fig = px.scatter(df, x="Sample", y="log2 abundance", color="Group", title=f"{selected} per sample")
    fig.update_traces(marker_size=12)
    show_fig(fig, "abundance-per-sample")


def pca(ctx):
    values = ctx["normalized"][SAMPLES].dropna()
    centered = values.T - values.T.mean()
    u, s, _ = np.linalg.svd(centered, full_matrices=False)
    explained = s**2 / (s**2).sum() * 100
    df = pd.DataFrame({"PC1": u[:, 0] * s[0], "PC2": u[:, 1] * s[1], "Sample": SAMPLES, "Group": [GROUPS[x] for x in SAMPLES]})
    fig = px.scatter(df, x="PC1", y="PC2", color="Group", text="Sample", title="Sample similarity (PCA)")
    fig.update_traces(textposition="top center", marker_size=12)
    fig.update_layout(xaxis_title=f"PC1 ({explained[0]:.0f} %)", yaxis_title=f"PC2 ({explained[1]:.0f} %)")
    show_fig(fig, "pca")


def clustered_heatmap(ctx):
    top = ctx["stats"]["id"].head(30)
    values = ctx["normalized"].set_index("id").loc[top, SAMPLES]
    z = values.sub(values.mean(axis=1), axis=0).div(values.std(axis=1), axis=0)
    z = z.loc[ctx["stats"].set_index("id").loc[top, "log2FC"].sort_values().index]
    fig = px.imshow(z, color_continuous_scale="RdBu_r", zmin=-2, zmax=2, aspect="auto", title="30 most significant (z-scores)")
    show_fig(fig, "heatmap")


def sample_counts(ctx):
    counts = ctx["table"][SAMPLES].notna().sum()
    fig = px.bar(x=counts.index, y=counts.values, labels={"x": "Sample", "y": "Quantified"}, title="Quantified per sample")
    show_fig(fig, "sample-counts")


def diagnostics(ctx):
    fig = px.histogram(ctx["stats"], x="p-value", nbins=20, title="p-value distribution")
    show_fig(fig, "p-values")


panels = quant_panels(
    {
        "key_figures": key_figures,
        "volcano": volcano,
        "statistics_table": statistics_table,
        "abundance_per_sample": abundance_per_sample,
        "pca": pca,
        "clustered_heatmap": clustered_heatmap,
        "sample_counts": sample_counts,
        "diagnostics": diagnostics,
    }
)
workspace = st.session_state["workspace"]

with st.expander("Arrange panels"):
    layout_editor(workspace, DASHBOARD_NAME, panels, QUANT_DEFAULT_LAYOUT, key="dashboard_example_editor")

render_dashboard(
    workspace,
    DASHBOARD_NAME,
    panels,
    QUANT_DEFAULT_LAYOUT,
    context={"table": table, "normalized": normalized, "stats": stats},
)
