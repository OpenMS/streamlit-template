"""Peak spectrum: the measured peaks of the selected spectrum as sticks, by m/z
and intensity, the strongest labelled. Follows the spectrum a scan table,
chromatogram or peak map picks.

Insight component: ``LinePlot``. Columns: ``index`` (the spectrum), ``mz``,
``intensity``.
"""

from __future__ import annotations

COMPONENT = "LinePlot"


def settings(spectrum: str = "scan", title: str = "Spectrum", styling=None, **overrides) -> dict:
    """Constructor arguments: shows the peaks of the spectrum whose ``index`` is
    in ``spectrum``."""
    return dict(
        filters={spectrum: "index"},
        x_column="mz", y_column="intensity",
        title=title, x_label="m/z", y_label="Intensity",
        show_top_peak_labels=True, top_peak_labels=10,
        **({"styling": styling} if styling else {}),
    ) | overrides
