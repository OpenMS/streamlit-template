"""GO term panel: the Gene Ontology terms over-represented in picked proteins,
or, while nothing is picked (or on request), how many proteins carry each term.

Contract (the app's source fills it, per GO category ``BP``, ``CC``, ``MF``):

- an *enrichment* table per category (pandas or polars) with the columns
  ``GO_Term``, ``Count``, ``Background``, ``GeneRatio``, ``BgRatio``,
  ``FoldEnrichment``, ``p_value``, ``p_adj`` and ``Proteins`` (accessions
  joined by ``;``);
- a *count* table per category with ``term``, ``count`` and ``accessions``
  (joined by ``;``), most frequent first, and the number of proteins with
  any GO term;
- ``labels``, accession -> the name the tables show.

The panel draws a bar chart whose GO category and number of terms are picked
on the chart, and a paginated Insight table of every term of the category
picked on the chart. While proteins are picked, the chart's toolbar holds a
**Selection | All proteins** switch and **Clear selection**; what is shown
and how to pick proteins is said in the chart's info box. An openms-insight
whose ``SeriesPlot`` has no ``switch_identifier`` gets the switch, the button
and the line as Streamlit widgets above the chart instead.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import polars as pl
import streamlit as st

from src.viz.plumbing import accepts

CATEGORIES = {"BP": "Biological process", "CC": "Cellular component", "MF": "Molecular function"}
TERM_COUNTS = [10, 15, 20, 30, 50]
TOP_TERMS = 15
DEFAULT_CATEGORY = "BP"
# The state identifier the chart writes its GO category to; the table follows it
CATEGORY_IDENTIFIER = "go_category"

SELECTION = "Selection"
ALL = "All proteins"
# Values of the chart's switch, kept in the state under ``mode_identifier(key)``
MODES = {"selection": SELECTION, "all": ALL}


def mode_identifier(key: str) -> str:
    """The state identifier the chart's Selection | All proteins switch writes to."""
    return f"go_mode@{key}"


def _in_chart() -> bool:
    """Whether the installed openms-insight draws the switch and Clear selection in the chart."""
    try:
        from openms_insight import SeriesPlot
    except ImportError:
        return False
    return accepts(SeriesPlot, "switch_identifier") and accepts(SeriesPlot, "clear_identifiers")


def info_text(*parts: str | None) -> str | None:
    """The chart's info box: what is shown and how to pick proteins, then the panel's help.

    The box shows plain text, so Markdown emphasis (``**``) is left out.
    """
    text = "\n\n".join(p.replace("**", "").strip() for p in parts if p and p.strip())
    return text or None

TERM_COLUMNS = [
    {"title": "#", "field": "rank", "sorter": "number", "width": 50},
    {"title": "GO term", "field": "term", "sorter": "string", "minWidth": 220, "hozAlign": "left"},
    {"title": "Selected", "field": "count", "sorter": "number",
     "headerTooltip": "Selected proteins annotated with the term."},
    {"title": "Background", "field": "background", "sorter": "number",
     "headerTooltip": "Proteins of the background annotated with the term."},
    {"title": "Ratio", "field": "ratio", "sorter": "string",
     "headerTooltip": "Selected proteins with the term / selected proteins with any GO term."},
    {"title": "Bg ratio", "field": "bg_ratio", "sorter": "string",
     "headerTooltip": "Background proteins with the term / background proteins with any GO term."},
    {"title": "Fold", "field": "fold", "sorter": "number",
     "formatter": "fixed", "formatterParams": {"precision": 2}, "headerTooltip": "Ratio / Bg ratio."},
    {"title": "p-value", "field": "pvalue", "sorter": "number",
     "formatter": "scientific", "formatterParams": {"precision": 2},
     "headerTooltip": "One-sided Fisher's exact test."},
    {"title": "Adj. p-value", "field": "padj", "sorter": "number",
     "formatter": "scientific", "formatterParams": {"precision": 2},
     "headerTooltip": "Benjamini-Hochberg adjusted, within the category."},
    {"title": "Proteins", "field": "proteins", "sorter": "string", "minWidth": 200, "hozAlign": "left",
     "headerTooltip": "The selected proteins annotated with the term."},
]

COUNT_COLUMNS = [
    {"title": "#", "field": "rank", "sorter": "number", "width": 50},
    {"title": "GO term", "field": "term", "sorter": "string", "minWidth": 220, "hozAlign": "left"},
    {"title": "Proteins", "field": "count", "sorter": "number", "headerTooltip": "Proteins annotated with the term."},
    {"title": "% of annotated", "field": "share", "sorter": "number",
     "formatter": "fixed", "formatterParams": {"precision": 1},
     "headerTooltip": "Proteins with the term, in percent of the proteins with any GO term."},
    {"title": "Annotated proteins", "field": "proteins", "sorter": "string", "minWidth": 200,
     "hozAlign": "left", "headerTooltip": "The proteins annotated with the term."},
]

_TERM_SCHEMA = {
    "rank": pl.Int64, "term": pl.Utf8, "count": pl.Int64, "background": pl.Int64, "ratio": pl.Utf8,
    "bg_ratio": pl.Utf8, "fold": pl.Float64, "pvalue": pl.Float64, "padj": pl.Float64, "proteins": pl.Utf8,
}
_COUNT_SCHEMA = {"rank": pl.Int64, "term": pl.Utf8, "count": pl.Int64, "share": pl.Float64, "proteins": pl.Utf8}


def _pandas(table):
    if table is None:
        return None
    return table.to_pandas() if isinstance(table, pl.DataFrame) else table


def _polars(table):
    if table is None:
        return None
    return pl.from_pandas(table) if isinstance(table, pd.DataFrame) else table


def _names(accessions, labels: dict) -> str:
    return ", ".join(labels.get(a, a) for a in str(accessions).split(";") if a)


def term_frame(table, labels: dict) -> pl.DataFrame:
    """The enriched terms of one category, most significant first, as the table's rows."""
    table = _pandas(table)
    if table is None or not len(table):
        return pl.DataFrame(schema=_TERM_SCHEMA)
    table = table.sort_values("p_adj")
    return pl.DataFrame({
        "rank": list(range(1, len(table) + 1)),
        "term": table["GO_Term"].astype(str).tolist(),
        "count": table["Count"].astype(int).tolist(),
        "background": table["Background"].astype(int).tolist(),
        "ratio": table["GeneRatio"].astype(str).tolist(),
        "bg_ratio": table["BgRatio"].astype(str).tolist(),
        "fold": table["FoldEnrichment"].astype(float).tolist(),
        "pvalue": table["p_value"].astype(float).tolist(),
        "padj": table["p_adj"].astype(float).tolist(),
        "proteins": [_names(p, labels) for p in table["Proteins"]],
    }, schema=_TERM_SCHEMA)


def count_frame(table, labels: dict, total: int) -> pl.DataFrame:
    """The terms of one category with the number of proteins carrying each, as the table's rows."""
    table = _polars(table)
    if table is None or not table.height:
        return pl.DataFrame(schema=_COUNT_SCHEMA)
    counts = table["count"].to_list()
    return pl.DataFrame({
        "rank": list(range(1, table.height + 1)),
        "term": table["term"].to_list(),
        "count": counts,
        "share": [100.0 * c / total if total else 0.0 for c in counts],
        "proteins": [_names(a, labels) for a in table["accessions"].to_list()],
    }, schema=_COUNT_SCHEMA)


def term_chart(tables: dict) -> pl.DataFrame:
    """The most significant terms of every category: term, score (-log10 adjusted p), hover, category."""
    parts = []
    for category in CATEGORIES:
        table = _pandas(tables.get(category))
        if table is None or not len(table):
            continue
        top = table.sort_values("p_adj").head(max(TERM_COUNTS))
        padj = top["p_adj"].astype(float).clip(lower=1e-300)
        parts.append(pl.DataFrame({
            "term": top["GO_Term"].astype(str).tolist(),
            "score": (-np.log10(padj)).round(3).tolist(),
            "hover": [
                f"{t}: {c} selected ({r}), adj. p {p:.2e}, fold {f:.2f}"
                for t, c, r, p, f in zip(top["GO_Term"], top["Count"], top["GeneRatio"], padj, top["FoldEnrichment"])
            ],
            "category": [category] * len(top),
        }))
    return pl.concat(parts) if parts else pl.DataFrame(schema={
        "term": pl.Utf8, "score": pl.Float64, "hover": pl.Utf8, "category": pl.Utf8})


def count_chart(tables: dict, total: int) -> pl.DataFrame:
    """The most frequent terms of every category: term, proteins, hover, category."""
    parts = []
    for category in CATEGORIES:
        table = _polars(tables.get(category))
        if table is None or not table.height:
            continue
        top = table.head(max(TERM_COUNTS))
        counts = top["count"].to_list()
        parts.append(pl.DataFrame({
            "term": top["term"].to_list(),
            "proteins": counts,
            "hover": [
                f"{t}: {c} proteins ({100.0 * c / total if total else 0.0:.1f}% of annotated)"
                for t, c in zip(top["term"].to_list(), counts)
            ],
            "category": [category] * len(counts),
        }))
    return pl.concat(parts) if parts else pl.DataFrame(schema={
        "term": pl.Utf8, "proteins": pl.Int64, "hover": pl.Utf8, "category": pl.Utf8})


def _fingerprint(frame: pl.DataFrame, *parts) -> str:
    digest = hashlib.sha1(repr(parts).encode())
    digest.update(repr((frame.columns, frame.shape)).encode())
    if frame.height:
        digest.update(str(int(frame.hash_rows(seed=0).sum())).encode())
    return digest.hexdigest()[:16]


def _default_category(frame: pl.DataFrame) -> str:
    present = set(frame["category"].unique().to_list()) if frame.height else set()
    return next((c for c in CATEGORIES if c in present), DEFAULT_CATEGORY)


def _chart(frame, y_column, y_label, title, cache_path, key, state_manager, help_text, toolbar=None):
    # ``key`` names the mode too: a component keeps the columns it was first drawn with.
    # ``toolbar``: the switch and Clear selection, given to the chart while proteins are picked
    from openms_insight import SeriesPlot

    default = _default_category(frame)
    cache_id = f"go-chart-{_fingerprint(frame, y_column, default)}"
    plot = SeriesPlot(
        cache_id=cache_id, cache_path=str(cache_path), data=frame.lazy(),
        x_column="term", y_column=y_column, mode="bars", orientation="h", show_legend=False,
        hover_column="hover", title=title, x_label=" ", y_label=y_label,
        view_column="category", view_names=dict(CATEGORIES), view_identifier=CATEGORY_IDENTIFIER,
        view_default=default, top_choices=TERM_COUNTS, top_default=TOP_TERMS, bar_height=26,
        **(toolbar or {}),
    )
    plot(key=f"{key}_chart", state_manager=state_manager, height=320, help=help_text)


TERM_TABLE_HELP = (
    "Every GO term of the selected proteins, tested against the background (all proteins of the "
    "experiment with a GO term). Sorted by adjusted p-value; the category buttons above pick biological "
    "process, molecular function or cellular component."
)
COUNT_TABLE_HELP = (
    "Every GO term of the proteins, with how many proteins carry it and which. Sorted by the number of "
    "proteins; the category buttons above pick biological process, molecular function or cellular "
    "component. Select proteins elsewhere to test which terms are enriched among them."
)


def _table(frames: dict, columns, sort, cache_path, key, state_manager, title, help_text=None):
    # ``key`` names the mode too: a table keeps the column definitions it was first drawn with
    from openms_insight import Table

    parts = [f.with_columns(pl.lit(c).alias("category")) for c, f in frames.items()]
    frame = pl.concat(parts, how="vertical_relaxed").with_row_index("id")
    default = _default_category(frame)
    table = Table(
        cache_id=f"go-table-{_fingerprint(frame, title, default)}", cache_path=str(cache_path),
        data=frame.lazy(), column_definitions=list(columns), index_field="id", title=title,
        filters={CATEGORY_IDENTIFIER: "category"}, filter_defaults={CATEGORY_IDENTIFIER: default},
        initial_sort=list(sort), layout="fitColumns", go_to_fields=["term"], float_precision="float64",
    )
    table(key=f"{key}_terms", state_manager=state_manager, height=380, help=help_text)


def _clear(state_manager, identifier, mode_key):  # the Streamlit button of an older openms-insight
    # Set to None, not removed: the components keep a selection Python no
    # longer sends and would send it back
    state_manager.set_selection(identifier, None)
    st.session_state.pop(mode_key, None)


def show_go_panel(
    key: str,
    cache_path,
    state_manager,
    selection_identifier: str,
    selected: bool,
    line: str,
    enrichment: Callable[[], tuple[dict | None, str | None]],
    counts: Callable[[], tuple[int, dict, str | None]],
    labels: dict,
    hint: str = "",
    help: str | None = None,  # pylint: disable=redefined-builtin
) -> None:
    """Draw the GO panel.

    ``selected``: whether proteins are picked (``line`` then says how many).
    ``enrichment()`` returns ``(tables, error)`` for the picked proteins, a dict
    of category -> enrichment table, or None when none of them has a GO term;
    ``counts()`` returns ``(annotated, tables, error)`` for every protein. Both
    are only called when shown, so the app may compute them there (and should
    cache them). ``hint`` says how to pick proteins; it goes in the chart's info
    box with ``line`` and ``help``.
    """
    cache_path = Path(cache_path, "go")
    toolbar = None
    if _in_chart():
        switch = mode_identifier(key)
        if not selected:
            # A new selection starts on its enrichment again
            if state_manager.get_selection(switch) is not None:
                state_manager.set_selection(switch, None)
            mode = ALL
        else:
            mode = MODES.get(state_manager.get_selection(switch), SELECTION)
            toolbar = dict(
                switch_identifier=switch, switch_names=dict(MODES), switch_default="selection",
                clear_identifiers=[selection_identifier, switch],
            )
        help = info_text(line if selected else None, hint, help)
    else:
        mode_key = f"{key}_go_mode"
        if not selected:
            st.session_state.pop(mode_key, None)
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(line if selected else (hint or line), width="stretch")
            if selected:
                mode = st.segmented_control(
                    "Show", [SELECTION, ALL], default=SELECTION, key=mode_key, label_visibility="collapsed",
                    width="content",
                ) or SELECTION
                st.button(
                    "Clear selection", key=f"{key}_go_clear", on_click=_clear,
                    args=(state_manager, selection_identifier, mode_key), width="content",
                )
            else:
                mode = ALL

    if mode == SELECTION:
        tables, error = enrichment()
        if error:
            st.warning(error)
        empty = None
        if tables is None:
            empty = "None of the selected proteins has a GO annotation."
        elif not any(t is not None and len(t) for t in tables.values()):
            empty = "The selected proteins have no GO terms."
        if empty and toolbar is None:
            st.info(empty)
            return
        if empty:
            # Nothing to test: the terms of all proteins, whose chart still offers Clear selection
            st.info(f"{empty} Showing the terms of all proteins.")
            mode = ALL
    if mode == SELECTION:
        _chart(term_chart(tables), "score", "-log10(adjusted p-value)", "{view}: the most significant terms",
               cache_path, f"{key}_selection", state_manager, help, toolbar)
        _table({c: term_frame(tables.get(c), labels) for c in CATEGORIES}, TERM_COLUMNS,
               ({"column": "padj", "dir": "asc"},), cache_path, f"{key}_selection", state_manager, "Enriched GO terms",
               TERM_TABLE_HELP)
        return

    annotated, tables, error = counts()
    if error:
        st.warning(error)
    if not annotated or not any(t is not None and len(t) for t in tables.values()):
        st.info("None of these proteins has a GO annotation.")
        if toolbar is not None:
            # No chart to hold Clear selection, so the selection can still be cleared here
            st.button("Clear selection", key=f"{key}_go_clear", on_click=_clear,
                      args=(state_manager, selection_identifier, switch), width="content")
        return
    _chart(count_chart(tables, annotated), "proteins", "Proteins", "{view}: the most frequent terms",
           cache_path, f"{key}_all", state_manager, help, toolbar)
    _table({c: count_frame(tables.get(c), labels, annotated) for c in CATEGORIES}, COUNT_COLUMNS,
           ({"column": "count", "dir": "desc"},), cache_path, f"{key}_all", state_manager, "GO terms of all proteins",
           COUNT_TABLE_HELP)
