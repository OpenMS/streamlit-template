"""A workflow's setup file: settings, design, folders and the picked input files by name."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from src.workflow.setup_file import (
    apply_setup,
    export_setup,
    input_files,
    is_setup_file,
    read_setup,
    still_missing,
)

DESIGN = (
    "Fraction_Group\tFraction\tSpectra_Filepath\tLabel\tSample\n"
    "1\t1\t/a/Control.mzML\t1\t1\n2\t1\t/a/Treated.mzML\t1\t2\n\n"
    "Sample\tMSstats_Condition\tMSstats_BioReplicate\n1\tcontrol\t1\n2\ttreated\t1\n"
)


def _workflow(root: Path, files=("Control.mzML", "Treated.mzML", "Blank.mzML")) -> Path:
    wf = root / "topp-workflow"
    mzml = wf / "input-files" / "mzML-files"
    mzml.mkdir(parents=True)
    for name in files:
        (mzml / name).write_text("x" * 10)
    db = wf / "input-files" / "fasta"
    db.mkdir()
    (db / "human.fasta").write_text(">p\nPEPTIDE\n")
    return wf


def test_a_setup_carries_the_settings_design_folders_and_picked_files_by_name(tmp_path):
    source = _workflow(tmp_path / "mine")
    mzml = source / "input-files" / "mzML-files"
    (source / "params.json").write_text(json.dumps({
        "mzML-files": [str(mzml / "Control.mzML"), str(mzml / "Treated.mzML")],
        "fasta": str(source / "input-files" / "fasta" / "human.fasta"),
        "Comet:1:precursor_mass_tolerance": 10.0,
        "_follow_up": {"run": "20261101-000000"},
    }))
    (source / "experimental-design.tsv").write_text(DESIGN)
    (source / "input-folders.json").write_text(json.dumps({"mzML-files": {"Control.mzML": "Day 1"}}))

    data = export_setup(source, app="App", version="1.0")
    assert is_setup_file(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("setup.json"))
        assert "_follow_up" not in json.loads(archive.read("params.json"))
        assert not [n for n in archive.namelist() if n.endswith((".mzML", ".fasta"))]
    assert manifest["selections"]["mzML-files"] == {
        "key": "mzML-files", "files": ["Control.mzML", "Treated.mzML"], "multiple": True}
    assert manifest["selections"]["fasta"]["multiple"] is False
    assert {f["name"] for f in manifest["files"]["mzML-files"]} == {"Blank.mzML", "Control.mzML", "Treated.mzML"}

    # A colleague's workspace has the same files under other paths, and not Treated.mzML
    target = _workflow(tmp_path / "theirs", files=("Control.mzML", "Blank.mzML"))
    params, missing = apply_setup(target, read_setup(data))
    assert params["mzML-files"] == [str(target / "input-files" / "mzML-files" / "Control.mzML")]
    assert params["fasta"] == str(target / "input-files" / "fasta" / "human.fasta")
    assert params["Comet:1:precursor_mass_tolerance"] == 10.0
    assert "_follow_up" not in params
    assert missing == {"mzML-files": ["Treated.mzML"]}
    assert (target / "experimental-design.tsv").read_text() == DESIGN
    assert json.loads((target / "input-folders.json").read_text()) == {"mzML-files": {"Control.mzML": "Day 1"}}

    # Once the file is uploaded it is no longer reported
    (target / "input-files" / "mzML-files" / "Treated.mzML").write_text("x")
    assert still_missing(target, missing) == {}


def test_a_single_selection_whose_file_is_missing_falls_back_to_the_default(tmp_path):
    source = _workflow(tmp_path / "mine")
    (source / "params.json").write_text(json.dumps(
        {"fasta": str(source / "input-files" / "fasta" / "human.fasta")}))
    target = tmp_path / "empty" / "topp-workflow"
    params, missing = apply_setup(target, read_setup(export_setup(source)))
    assert "fasta" not in params
    assert missing == {"fasta": ["human.fasta"]}


def test_a_picked_file_that_is_gone_still_counts_for_its_selection(tmp_path):
    source = _workflow(tmp_path / "mine", files=("Control.mzML",))
    mzml = source / "input-files" / "mzML-files"
    (source / "params.json").write_text(json.dumps(
        {"mzML-files": [str(mzml / "Control.mzML"), str(mzml / "Deleted.mzML")]}))
    selections = json.loads(zipfile.ZipFile(io.BytesIO(export_setup(source))).read("setup.json"))["selections"]
    assert selections["mzML-files"]["files"] == ["Control.mzML", "Deleted.mzML"]
    _, missing = apply_setup(tmp_path / "theirs", read_setup(export_setup(source)))
    assert missing == {"mzML-files": ["Control.mzML", "Deleted.mzML"]}


def test_referenced_files_count_as_input_files(tmp_path):
    wf = _workflow(tmp_path)
    elsewhere = tmp_path / "data" / "Far.mzML"
    elsewhere.parent.mkdir()
    elsewhere.write_text("x")
    (wf / "input-files" / "mzML-files" / "external_files.txt").write_text(f"{elsewhere}\n/gone/Old.mzML\n")
    names = [Path(p).name for p in input_files(wf)["mzML-files"]]
    assert "Far.mzML" in names and "Old.mzML" not in names and "external_files.txt" not in names


@pytest.mark.parametrize("members", [
    {},
    {"setup.json": "{}", "params.json": "{}"},
    {"setup.json": '{"format": 1}', "params.json": "[]"},
    {"setup.json": '{"format": 1}', "params.json": "{", },
    {"setup.json": '{"format": 1}', "params.json": "{}", "experimental-design.tsv": "not a design"},
    {"setup.json": '{"format": 1, "selections": []}', "params.json": "{}"},
    {"setup.json": '{"format": 1, "selections": {"a": "x"}}', "params.json": "{}"},
    {"setup.json": '{"format": 1, "selections": {"a": {"key": "k", "files": "x.mzML", "multiple": true}}}',
     "params.json": "{}"},
    {"setup.json": '{"format": 1, "selections": {"a": {"key": "k", "files": [1], "multiple": true}}}',
     "params.json": "{}"},
    {"setup.json": '{"format": 1, "selections": {"a": {"key": 1, "files": [], "multiple": true}}}',
     "params.json": "{}"},
])
def test_a_damaged_setup_is_refused(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    with pytest.raises(ValueError):
        read_setup(buffer.getvalue())


def test_a_parameters_json_is_not_a_setup_file():
    assert not is_setup_file(b'{"a": 1}')
    with pytest.raises(ValueError):
        read_setup(b'{"a": 1}')


PAGE = """
from pathlib import Path
import streamlit as st
from src.workflow.ParameterManager import ParameterManager
from src.workflow.StreamlitUI import StreamlitUI
manager = ParameterManager(Path(st.session_state.folder))
ui = object.__new__(StreamlitUI)
ui.workflow_dir, ui.parameter_manager = Path(st.session_state.folder), manager
ui.preset_buttons = lambda: None
ui.user_presets = lambda: None
ui.parameter_section(lambda: None)
"""


def test_importing_a_setup_on_the_configure_page_names_the_files_to_upload(tmp_path, monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    source = _workflow(tmp_path / "mine")
    mzml = source / "input-files" / "mzML-files"
    (source / "params.json").write_text(json.dumps(
        {"mzML-files": [str(mzml / "Control.mzML"), str(mzml / "Treated.mzML")]}))
    data = export_setup(source)
    target = _workflow(tmp_path / "theirs", files=("Control.mzML",))
    (target / "params.json").write_text("{}")

    uploader = st.file_uploader

    def uploaded(label, *args, **kwargs):
        result = uploader(label, *args, **kwargs)
        if label == "⬆️ Import parameters" and kwargs["key"].endswith("-0"):
            return io.BytesIO(data)
        return result

    monkeypatch.setattr(st, "file_uploader", uploaded)
    app = AppTest.from_string(PAGE)
    app.session_state.folder = str(target)
    app.session_state.settings = {"online_deployment": True}
    app.run(timeout=30)
    assert not app.exception
    params = json.loads((target / "params.json").read_text())
    assert params["mzML-files"] == [str(target / "input-files" / "mzML-files" / "Control.mzML")]
    assert any("Treated.mzML" in w.value for w in app.warning)


def test_a_setup_import_draws_the_design_editor_again(tmp_path, monkeypatch):
    import streamlit as st
    from src.workflow.StreamlitUI import StreamlitUI

    wf = _workflow(tmp_path)
    state = {f"_design-{wf.name}-mzML-files": 2, f"_design-{wf.name}-mzML-files-refill": False}
    monkeypatch.setattr(st, "session_state", state)
    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = wf
    ui._restart_design_editors()
    assert state[f"_design-{wf.name}-mzML-files"] == 3
    assert state[f"_design-{wf.name}-mzML-files-refill"] is False
