"""The detection preset the example workflow suggests for the selected files."""
import json
from pathlib import Path

from src.Workflow import Workflow


def _wf():
    return object.__new__(Workflow)


def test_no_files_no_suggestion():
    assert _wf().recommend_preset([]) == (None, "")


def test_few_files_balanced():
    preset, why = _wf().recommend_preset(["a.mzML", "b.mzML"])
    assert preset == "Metabolomics Default"
    assert "2 files" in why and "Balanced" in why


def test_many_files_fast():
    files = [f"{i}.mzML" for i in range(Workflow.MANY_FILES)]
    preset, why = _wf().recommend_preset(files)
    assert preset == "Fast Analysis"
    assert "Fast" in why


def test_every_offered_preset_exists():
    presets = json.loads(Path("presets.json").read_text())["topp-workflow"]
    assert set(Workflow.DETECTION_PRESETS) <= set(presets)
