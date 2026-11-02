"""The quantification dashboard of docs/quantification-spec.md (B13).

Panel names, labels and the default layout every app uses, so a layout saved
in one app opens in another. Apps attach their own render functions (which
draw openms-insight components) with :func:`quant_panels`; the template does
not draw quantification data itself.
"""

from __future__ import annotations

from typing import Callable

from src.common.dashboard.layout import Panel

DASHBOARD_NAME = "quantification"

# name, label, group, requires (see the spec for what each panel shows)
QUANT_PANEL_SPECS = [
    ("key_figures", "Key figures (compared, up, down)", "Summary", None),
    ("statistics_table", "Statistics table", "Tables", None),
    ("abundance_table", "Abundance table", "Tables", None),
    ("volcano", "Volcano plot", "Comparison", None),
    ("abundance_per_sample", "Abundance per sample", "Comparison", "statistics_table"),
    ("pca", "Sample similarity (PCA)", "Samples", None),
    ("clustered_heatmap", "Clustered heatmap", "Samples", None),
    ("sample_counts", "Per-sample counts", "Samples", None),
    ("diagnostics", "Diagnostics of the comparison", "Quality control", None),
    ("go_enrichment", "GO enrichment", "Biology", None),
]

QUANT_DEFAULT_LAYOUT = [
    ["key_figures"],
    ["volcano", "abundance_per_sample"],
    ["statistics_table"],
    ["pca", "clustered_heatmap"],
]


def quant_panels(renderers: dict[str, Callable[[dict], None]]) -> list[Panel]:
    """Panels of the quant dashboard this app can draw.

    ``renderers`` maps panel names of ``QUANT_PANEL_SPECS`` to render
    functions; panels without one are not offered (e.g. GO enrichment where
    rows have no UniProt accession). Unknown names raise ``KeyError`` so a typo
    does not silently drop a panel.
    """
    specs = {name: (label, group, req) for name, label, group, req in QUANT_PANEL_SPECS}
    unknown = set(renderers) - set(specs)
    if unknown:
        raise KeyError(f"Not a quant dashboard panel: {', '.join(sorted(unknown))}")
    panels = []
    for name, (label, group, requires) in specs.items():
        if name in renderers:
            if requires and requires not in renderers:
                requires = None
            panels.append(Panel(name, label, renderers[name], group, requires))
    return panels
