"""Mass shift histogram: how many spectrum matches (PrSMs or PSMs) carry each
precursor mass shift, the recurring shifts labelled with the modification they
match. A click picks the shift, which narrows the tables below to the rows
carrying it.

Insight component: ``LinePlot``. Columns: ``delta``, the count column
(``prsms`` by default), ``peak`` (highlighted), ``label``, ``shift_id``.
"""

from __future__ import annotations

COMPONENT = "LinePlot"


def settings(mass_shift: str = "mass_shift", count: tuple = ("prsms", "PrSMs"), **overrides) -> dict:
    """``count`` is the (column, axis title) of the spectrum-match count."""
    return dict(
        x_column="delta", y_column=count[0], highlight_column="peak", annotation_column="label",
        interactivity={mass_shift: "shift_id"},
        title="Mass shifts of the identified proteoforms",
        x_label="Mass shift (Da)", y_label=count[1],
    ) | overrides
