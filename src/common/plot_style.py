"""Colours of the OpenMS theme for openms-insight spectra (Streamlit-free).

The template does not depend on openms-insight; apps that draw spectra with it
pass these as ``styling=`` so their plots match the theme in
.streamlit/config.toml. Peaks are a quiet warm grey, so colour marks only what
matters: blue for matched (highlighted) peaks and their labels, orange for the
peak the user picked. The values read on the light and on the dark theme.

    from openms_insight import LinePlot
    from src.common.plot_style import spectrum_styling

    LinePlot(..., styling=spectrum_styling())
"""

from __future__ import annotations

import copy
from typing import Any

PEAK = "#9d9094"  # corporate grey
MATCHED = "#3157e9"  # corporate blue
PICKED = "#ff7501"  # corporate orange
MATCHED_HIDDEN = "#7891f1"  # light blue of the palette, for matches out of view

SPECTRUM_STYLING: dict[str, Any] = {
    "unhighlightedColor": PEAK,
    "highlightColor": MATCHED,
    "selectedColor": PICKED,
    "highlightHiddenColor": MATCHED_HIDDEN,
    "annotationColors": {
        "massButton": MATCHED,
        "selectedMassButton": PICKED,
        "sequenceArrow": MATCHED,
        "selectedSequenceArrow": PICKED,
    },
}


def spectrum_styling(**overrides: Any) -> dict[str, Any]:
    """A copy of SPECTRUM_STYLING with ``overrides`` applied.

    ``annotationColors`` given as an override is merged into the default one.
    """
    styling = copy.deepcopy(SPECTRUM_STYLING)
    for key, value in overrides.items():
        if key == "annotationColors" and isinstance(value, dict):
            styling["annotationColors"].update(value)
        else:
            styling[key] = value
    return styling
