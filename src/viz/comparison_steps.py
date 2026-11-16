"""Older import path of the plots behind the steps of a group comparison, now
one module each in ``src.viz.quantification``: ``missing_values``,
``imputed_values``, ``normalization`` and ``pvalue_histogram``."""

# pylint: disable=unused-import
from src.viz.quantification.imputed_values import (  # noqa: F401
    IMPUTED_COLORS, IMPUTED_SERIES, imputed_value_preview, show_imputed_values,
)
from src.viz.quantification.missing_values import (  # noqa: F401
    MISSING_COLORS, MISSING_SERIES, missingness_vs_intensity, show_missing_values,
)
from src.viz.quantification.normalization import (  # noqa: F401
    STAGE_COLORS, STAGE_SERIES, sample_distributions, show_normalization,
)
from src.viz.quantification.pvalue_histogram import pvalue_histogram, show_pvalues  # noqa: F401
from src.viz.quantification.steps import (  # noqa: F401
    _bin_centres, _empty_lines, _histogram_lines, _log2, plot_height,
)
from src.viz.series import show_series  # noqa: F401
