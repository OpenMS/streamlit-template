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


def test_identification_steps_read_their_columns():
    from src.viz.identification import identification_steps as steps

    args = steps.settings(max_causes=2)
    fields = [c["field"] for c in args["column_definitions"]]
    assert fields == ["step", "spectra", "share", "cause"]
    assert args["index_field"] == "row" and args["default_row"] == -1
    assert "2 at most" in args["column_definitions"][-1]["headerTooltip"]
    assert steps.settings(title="Steps")["title"] == "Steps"
