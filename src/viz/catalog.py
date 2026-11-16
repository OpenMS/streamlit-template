"""Every component of the visualization library, by folder, with what it shows.

An app lists the components it offers in its own Viewer catalog; this one says
which library module draws each of them. ``tests/test_viz_catalog.py`` checks
that every module in a folder is listed here and every entry has a module.
"""

from __future__ import annotations

FOLDERS = {
    "ms_data": "MS data",
    "features": "Features and masses",
    "identification": "Identification",
    "quantification": "Quantification",
}

# name, folder, label, entry point, description
_ENTRIES = [
    ("volcano", "quantification", "Volcano plot", "show_volcano",
     "log2 fold change against the p-value of every entry of a group comparison, changes beyond "
     "both cut-offs coloured by direction, the most significant labelled."),
    ("pca", "quantification", "Sample similarity (PCA)", "pca_component",
     "Samples on their first principal components over the most variable entries, coloured by group."),
    ("clustered_heatmap", "quantification", "Clustered heatmap", "show_clustered_heatmap",
     "Row z-scores with entries and samples ordered by similarity, dendrograms and group colours."),
    ("zscore_heatmap", "quantification", "Z-score heatmap", "show_zscore_heatmap",
     "Row z-scores of the most variable entries in the input order, with a slider for how many."),
    ("abundance_profile", "quantification", "Abundance profile", "show_profile",
     "The picked entry's abundance per sample, samples side by side by group with a line at each "
     "group's mean; several picked entries as one series each."),
    ("comparison_table", "quantification", "Comparison table", "show_comparison_table",
     "Every entry of a group comparison, most significant first, with its change, log2 fold change "
     "and p-values."),
    ("missing_values", "quantification", "Where missing values occur", "show_missing_values",
     "Density of the mean abundance of complete entries and of entries with gaps."),
    ("imputed_values", "quantification", "Imputed values", "show_imputed_values",
     "The values imputation fills in against the measured ones."),
    ("normalization", "quantification", "Normalization", "show_normalization",
     "A box per sample of the abundances before and after normalization."),
    ("pvalue_histogram", "quantification", "p-value distribution", "show_pvalues",
     "Entries per p-value bin with the count expected when nothing changes."),
    ("go_enrichment", "quantification", "GO enrichment", "show_go_panel",
     "GO terms over-represented in the picked proteins, or how many proteins carry each term, as a "
     "chart and a table."),
]

COMPONENTS = [
    {"name": name, "folder": folder, "label": label, "module": f"src.viz.{folder}.{name}",
     "entry": entry, "description": description}
    for name, folder, label, entry, description in _ENTRIES
]


def components(folder: str | None = None) -> list[dict]:
    """The library's components, those of ``folder`` when given."""
    return [c for c in COMPONENTS if folder is None or c["folder"] == folder]


def component(name: str) -> dict:
    """The entry of ``name``; KeyError for a name the library lacks."""
    for entry in COMPONENTS:
        if entry["name"] == name:
            return entry
    raise KeyError(name)


def draw_function(name: str):
    """The function that draws ``name``."""
    import importlib

    entry = component(name)
    return getattr(importlib.import_module(entry["module"]), entry["entry"])
