"""Volcano plot of a group comparison: log2 fold change against the p-value
of every entry, changes beyond both cut-offs coloured by their direction.

Contract: a table (pandas or polars) with a log2 fold change column, a
p-value column (raw or adjusted) and a label column; ``interactivity`` and
``multi_select`` map the state identifiers a click or a picked set writes to
columns of it.
"""

from __future__ import annotations

from src.viz.plumbing import as_polars, fingerprint, zoom_args

UP_COLOR, DOWN_COLOR, NS_COLOR = "#E74C3C", "#3498DB", "#95A5A6"
MAX_LABELS = 10


def short_label(name) -> str:
    """``sp|P05161|ISG15_HUMAN`` -> ``ISG15_HUMAN``, so neighbouring labels overlap less."""
    return str(name).split("|")[-1]


def volcano_settings(*, log2fc_column: str = "log2FC", pvalue_column: str = "p-value",
                     label_column: str = "label", reference: str | None = None, compared: str | None = None,
                     interactivity: dict | None = None, multi_select: dict | None = None,
                     adjusted: bool | None = None, title: str | None = None) -> dict:
    """The ``VolcanoPlot`` arguments every app draws it with (besides data and cache).

    With ``reference`` and ``compared`` the plot is titled ``compared vs.
    reference`` and its presets read *Higher / Lower in compared*. ``adjusted``
    names the y-axis (default: whether the column is ``p-adj``).
    """
    if adjusted is None:
        adjusted = pvalue_column == "p-adj"
    settings = dict(
        log2fc_column=log2fc_column, pvalue_column=pvalue_column, label_column=label_column,
        x_label="log2 fold change", y_label="-log10(adjusted p-value)" if adjusted else "-log10(p-value)",
        up_color=UP_COLOR, down_color=DOWN_COLOR, ns_color=NS_COLOR,
        show_threshold_lines=True, threshold_line_style="dash",
    )
    if interactivity:
        settings["interactivity"] = interactivity
    if multi_select:
        # A box or lasso, or All changed / Higher / Lower above the plot, picks a set
        settings.update(multi_select=multi_select, selection_presets=True)
    if compared and reference:
        settings["title"] = f"{compared} vs. {reference}"
        settings["preset_labels"] = {"up": f"Higher in {compared}", "down": f"Lower in {compared}"}
    if title is not None:
        settings["title"] = title
    return settings


def show_volcano(data, name: str = "volcano", *, cache_path, key: str, fc_threshold: float,
                 p_threshold: float, state_manager=None, height: int = 560,
                 help: str | None = None, zoom: str | None = None,  # pylint: disable=redefined-builtin
                 max_labels: int = MAX_LABELS, **settings):
    """Draw ``data`` as a volcano plot; ``settings`` go to ``volcano_settings``."""
    from openms_insight import VolcanoPlot

    frame = as_polars(data)
    arguments = volcano_settings(**settings)
    plot = VolcanoPlot(
        cache_id=f"{name}-{fingerprint(frame, sorted(arguments.items(), key=lambda kv: kv[0]))}",
        cache_path=str(cache_path), data=frame.lazy(), **zoom_args(VolcanoPlot, zoom), **arguments,
    )
    plot(key=key, state_manager=state_manager, fc_threshold=fc_threshold, p_threshold=p_threshold,
         max_labels=max_labels, height=height, help=help)
    return plot
