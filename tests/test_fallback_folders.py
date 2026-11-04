"""Example (fallback) files given as a dict arrive in the folders it names."""
import sys
from pathlib import Path

from src.workflow.InputFolders import load_folders, save_folders
from src.workflow.StreamlitUI import StreamlitUI

# Later test files import src.workflow with streamlit mocked: let them import
# it afresh instead of finding the modules imported here.
for _key in [k for k in sys.modules if k.startswith("src.workflow")]:
    del sys.modules[_key]


def _ui(workflow_dir):
    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = Path(workflow_dir)
    return ui


def _examples(tmp_path):
    src = tmp_path / "examples"
    src.mkdir()
    for name in ("a.mzML", "b.mzML", "c.mzML"):
        (src / name).write_text(name)
    return {
        str(src / "a.mzML"): "Label-free/ctrl",
        str(src / "b.mzML"): "Label-free/drug",
        str(src / "c.mzML"): "",
    }


def test_copied_examples_arrive_in_their_folders(tmp_path):
    workflow_dir = tmp_path / "wf"
    _ui(workflow_dir)._ensure_fallback("mzML-files", _examples(tmp_path))
    assert sorted(p.name for p in (workflow_dir / "input-files" / "mzML-files").iterdir()) == [
        "a.mzML", "b.mzML", "c.mzML"
    ]
    assert load_folders(workflow_dir, "mzML-files") == {
        "a.mzML": "Label-free/ctrl", "b.mzML": "Label-free/drug"
    }


def test_folders_the_user_chose_stay(tmp_path):
    workflow_dir = tmp_path / "wf"
    save_folders(workflow_dir, "mzML-files", {"a.mzML": "mine"})
    _ui(workflow_dir)._ensure_fallback("mzML-files", _examples(tmp_path))
    assert load_folders(workflow_dir, "mzML-files") == {
        "a.mzML": "mine", "b.mzML": "Label-free/drug"
    }


def test_a_list_of_examples_sets_no_folders(tmp_path):
    workflow_dir = tmp_path / "wf"
    _ui(workflow_dir)._ensure_fallback("mzML-files", list(_examples(tmp_path)))
    assert (workflow_dir / "input-files" / "mzML-files" / "a.mzML").exists()
    assert load_folders(workflow_dir, "mzML-files") == {}
