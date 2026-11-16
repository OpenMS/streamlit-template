"""Run QC: small plots of a run's masses: the QScore, charge and mass
distributions and the masses found per spectrum over retention time.

Insight component: ``SeriesPlot``, one per plot. Columns: ``x``, ``y``,
``series``. ``PLOTS`` names each plot's title, axis labels, mode and y range;
the caller builds each table.
"""

from __future__ import annotations

COMPONENT = "SeriesPlot"

# name: (title, x label, y label, mode, y range)
PLOTS = {
    "qc_qscore": ("QScore Distribution", "QScore", "Masses", "lines", "nonnegative"),
    "qc_charge": ("Charge States", "Charge", "Masses", "lines+markers", "nonnegative"),
    "qc_mass": ("Mass Distribution", "Monoisotopic mass (Da)", "Masses", "lines", "nonnegative"),
    "qc_masses_per_spectrum": ("Masses per Spectrum", "Retention time (s)", "Masses", "markers",
                               "nonnegative"),
}


def plot_settings(title, x_label, y_label, mode, y_range, series_count=1, name="qc",
                  **overrides) -> dict:
    """Constructor arguments of one QC plot; a legend only for more than one
    series (a single one repeats the axis title)."""
    return dict(
        x_column="x", y_column="y", series_column="series",
        mode=mode, title=title, x_label=x_label, y_label=y_label,
        y_range_mode=y_range, svg_filename=name,
        show_legend=series_count > 1,
    ) | overrides


def settings(name: str, series_count: int = 1, **overrides) -> dict:
    """Constructor arguments of the run QC plot ``name`` (a key of ``PLOTS``)."""
    return plot_settings(*PLOTS[name], series_count=series_count, name=name, **overrides)
