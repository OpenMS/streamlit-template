"""Configurable dashboards: the app registers panels, the template lays them out.

See docs/quantification-spec.md (B13). ``layout`` and ``quant`` are
Streamlit-free; ``ui`` draws.
"""

from src.common.dashboard.layout import (
    MAX_COLUMNS,
    Panel,
    active_layout,
    load_layout,
    save_layout,
    validate_layout,
)

__all__ = [
    "MAX_COLUMNS",
    "Panel",
    "active_layout",
    "load_layout",
    "save_layout",
    "validate_layout",
]
