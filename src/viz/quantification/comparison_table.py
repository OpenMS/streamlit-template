"""The table of a group comparison: every entry, most significant first, with
the direction of its change, its log2 fold change and its p-values.

Contract: a table (pandas or polars) with an entry column, ``log2FC``,
``p-adj`` and optionally ``p-value``. Only the entry column's name differs
between apps (Protein, Proteoform, Metabolite): it is the ``entity_title``.
``interactivity`` and ``multi_select`` map state identifiers to its columns.
"""

from __future__ import annotations

import polars as pl

from src.viz.plumbing import as_polars, fingerprint

P_FORMAT = {"formatter": "scientific", "formatterParams": {"precision": 3}}
FC_FORMAT = {"formatter": "signed", "formatterParams": {"precision": 2}}
NO_CHANGE = "–"


def change_expression(compared: str | None, fc: float, padj: float, *,
                      log2fc_column: str = "log2FC", padj_column: str = "p-adj") -> pl.Expr:
    """``higher in <compared>`` / ``lower in <compared>`` beyond both cut-offs, else ``–``."""
    if not compared:
        return pl.lit(NO_CHANGE)
    significant = (pl.col(padj_column) <= padj) & (pl.col(log2fc_column).abs() >= fc)
    return (
        pl.when(significant & (pl.col(log2fc_column) > 0)).then(pl.lit(f"higher in {compared}"))
        .when(significant & (pl.col(log2fc_column) < 0)).then(pl.lit(f"lower in {compared}"))
        .otherwise(pl.lit(NO_CHANGE))
    )


def comparison_table(data, compared: str | None, fc: float, padj: float, *,
                     log2fc_column: str = "log2FC", padj_column: str = "p-adj"):
    """``data`` with a ``Change`` column, most significant first (untested
    entries last). A LazyFrame stays lazy."""
    lazy = isinstance(data, pl.LazyFrame)
    frame = data if lazy else as_polars(data)
    frame = frame.with_columns(
        pl.col(log2fc_column).cast(pl.Float64), pl.col(padj_column).cast(pl.Float64),
        change_expression(compared, fc, padj, log2fc_column=log2fc_column,
                          padj_column=padj_column).alias("Change"),
    ).sort(padj_column, nulls_last=True)
    return frame


def comparison_columns(entity_field: str, entity_title: str, *, entity_tooltip: str | None = None,
                       after_entity=(), after=(), p_value: bool = True,
                       log2fc_column: str = "log2FC", padj_column: str = "p-adj") -> list[dict]:
    """The ``Table`` column definitions: the entry, ``after_entity``, what
    changed (change, log2 fold change, adjusted p-value, p-value), ``after``."""
    entity = {"title": entity_title, "field": entity_field, "sorter": "string"}
    if entity_tooltip:
        entity["headerTooltip"] = entity_tooltip
    columns = [entity, *after_entity,
               {"title": "Change", "field": "Change", "sorter": "string"},
               {"title": "log2 fold change", "field": log2fc_column, "sorter": "number", **FC_FORMAT},
               {"title": "Adjusted p-value", "field": padj_column, "sorter": "number", **P_FORMAT,
                "headerTooltip": "Empty: removed by the filter, so not tested."}]
    if p_value:
        columns.append({"title": "p-value", "field": "p-value", "sorter": "number", **P_FORMAT})
    return [*columns, *after]


def comparison_title(reference: str | None, compared: str | None) -> str:
    return f"{compared} vs. {reference}" if reference and compared else "Group comparison"


def show_comparison_table(data, entity_field: str, entity_title: str, name: str = "comparison-table", *,
                          cache_path, key: str, reference: str | None, compared: str | None,
                          fc: float, padj: float, state_manager=None, height: int = 534,
                          help: str | None = None, title: str | None = None,  # pylint: disable=redefined-builtin
                          index_field: str | None = None, interactivity: dict | None = None,
                          multi_select: dict | None = None, hidden=(), **columns):
    """Draw ``data`` (see the module) as the comparison table; ``columns`` go
    to ``comparison_columns``, ``hidden`` columns sit in the column menu."""
    from openms_insight import Table

    frame = comparison_table(data, compared, fc, padj,
                             log2fc_column=columns.get("log2fc_column", "log2FC"),
                             padj_column=columns.get("padj_column", "p-adj"))
    if isinstance(frame, pl.LazyFrame):
        frame = frame.collect()
    if index_field is None:
        index_field = "_row"
        frame = frame.with_row_index(index_field).with_columns(pl.col(index_field).cast(pl.Int64))
    columns.setdefault("p_value", "p-value" in frame.columns)
    definitions = [{**c, "visible": False} if c["field"] in hidden else c
                   for c in comparison_columns(entity_field, entity_title, **columns)]
    arguments = dict(column_definitions=definitions, title=title or comparison_title(reference, compared),
                     index_field=index_field)
    if interactivity:
        arguments["interactivity"] = interactivity
    if multi_select:
        arguments["multi_select"] = multi_select
    table = Table(
        cache_id=f"{name}-{fingerprint(frame, repr(sorted(arguments.items(), key=lambda kv: kv[0])))}",
        cache_path=str(cache_path), data=frame.lazy(), **arguments,
    )
    table(key=key, state_manager=state_manager, height=height, help=help)
    return table

