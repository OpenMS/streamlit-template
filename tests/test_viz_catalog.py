"""The library catalog and its folders agree: one module per component."""

import importlib
from pathlib import Path

from src.viz import catalog

ROOT = Path(__file__).resolve().parents[1] / "src" / "viz"
SHARED = {"__init__", "steps"}


def test_every_module_is_listed():
    listed = {(c["folder"], c["name"]) for c in catalog.COMPONENTS}
    found = {
        (folder, path.stem)
        for folder in catalog.FOLDERS
        for path in (ROOT / folder).glob("*.py")
        if path.stem not in SHARED and not path.stem.startswith("_")
    }
    assert found == listed


def test_entries_resolve_and_describe():
    names = [c["name"] for c in catalog.COMPONENTS]
    assert len(names) == len(set(names))
    for entry in catalog.COMPONENTS:
        assert entry["folder"] in catalog.FOLDERS
        assert entry["description"].endswith(".")
        assert callable(catalog.draw_function(entry["name"]))


def test_old_paths_still_import():
    from src.viz import comparison_steps, go_panel, heatmap, profile, volcano

    assert profile.show_profile is importlib.import_module("src.viz.quantification.abundance_profile").show_profile
    assert go_panel._TERM_SCHEMA is not None
    assert volcano.short_label("sp|P1|A_HUMAN") == "A_HUMAN"
    assert heatmap.zscores and comparison_steps.show_pvalues
