"""Fragment mass errors: the error of each matched fragment of the picked
spectrum match (PrSM or PSM) over its mass or m/z, coloured by ion type, with
the fragment tolerance as two lines; a click picks the residue next to the
fragment's bond. Errors spread evenly around 0 are what a correct match looks
like; a trend over the mass points to a calibration issue.

Insight component: ``SeriesPlot``. Columns: ``proteoform_index`` (the match
the fragments belong to, when they are filtered by a selection),
``theoretical_mass``, ``ppm_error``, ``ion_type``, ``fragment``, ``residue``;
other position and error columns are named with ``x`` and ``y``.
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"

# Prefix ions blue, suffix ions red, internal fragments purple
ION_COLORS = {
    "a": "#9ecae1", "b": "#4292c6", "c": "#08519c",
    "x": "#fcbba1", "y": "#ef3b2c", "z": "#a50f15", "z+1": "#cb181d", "z+2": "#67000d",
    "internal": "#8E44AD",
}


TOLERANCE = "tolerance"


def tolerance_rows(tolerance: float, low: float, high: float, x: str = "theoretical_mass",
                   y: str = "ppm_error") -> list[dict]:
    """Rows drawing the fragment tolerance (±``tolerance``) from ``low`` to
    ``high`` as two series, ``tolerance +`` and ``tolerance -``, to append to
    the fragments."""
    return [{x: pos, y: sign * tolerance, "ion_type": f"{TOLERANCE} {'+' if sign > 0 else '-'}",
             "fragment": f"{'+' if sign > 0 else '-'}{tolerance:g}"}
            for sign in (1, -1) for pos in (low, high)]


def settings(prsm: str | None = "protein", residue: str | None = "aa",
             x: tuple = ("theoretical_mass", "Fragment mass (Da)"), y: tuple = ("ppm_error", "Error (ppm)"),
             **overrides) -> dict:
    """Constructor arguments: the fragments of the match in ``prsm`` (None:
    every row given), picking the residue in ``residue`` (None: no picking).
    ``x`` and ``y`` are the (column, axis title) of the position and error."""
    tolerance = "#a1a1aa"
    return dict(
        **({"filters": {prsm: "proteoform_index"}} if prsm else {}),
        **({"interactivity": {residue: "residue"}} if residue else {}),
        x_column=x[0], y_column=y[0], series_column="ion_type",
        series_colors=ION_COLORS | {f"{TOLERANCE} +": tolerance, f"{TOLERANCE} -": tolerance},
        series_modes={f"{TOLERANCE} +": "lines", f"{TOLERANCE} -": "lines"},
        mode="markers", y_range_mode="normal", hover_column="fragment",
        title="Fragment Mass Errors", x_label=x[1], y_label=y[1],
        svg_filename="fragment-errors",
    ) | overrides
