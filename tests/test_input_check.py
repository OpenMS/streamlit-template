"""Selected input files whose outputs would share a name."""

from pathlib import Path

from src.workflow.input_check import clash_message, name_clashes, selection_clashes


def test_same_name_in_two_folders_clashes():
    files = ["/a/plate1/sample1.mzML", "/a/plate2/sample1.mzML", "/a/plate1/sample2.mzML"]
    assert name_clashes(files) == [["/a/plate1/sample1.mzML", "/a/plate2/sample1.mzML"]]


def test_other_extension_and_case_clash():
    assert name_clashes(["x/S1.mzML", "x/s1.raw"]) == [["x/S1.mzML", "x/s1.raw"]]


def test_distinct_names_and_repeated_paths_do_not_clash():
    assert name_clashes(["x/a.mzML", "x/b.mzML"]) == []
    assert name_clashes(["x/a.mzML", "x/./a.mzML"]) == []
    assert name_clashes("x/a.mzML") == []
    assert name_clashes(None) == []


def test_only_input_file_selections_are_checked(tmp_path):
    Path(tmp_path, "input-files", "mzML-files").mkdir(parents=True)
    params = {
        "mzML-files": ["p1/a.mzML", "p2/a.mzML"],
        "labels": ["a.x", "a.y"],  # a list parameter, not a file selection
        "fasta": "db.fasta",
    }
    assert selection_clashes(tmp_path, params) == {"mzML-files": [["p1/a.mzML", "p2/a.mzML"]]}
    assert selection_clashes(tmp_path, {}) == {}


def test_message_names_the_files_and_their_folders():
    text = clash_message([["/d/plate1/sample1.mzML", "/d/plate2/sample1.mzML"]])
    assert "**sample1**" in text
    assert "`plate1/sample1.mzML`" in text and "`plate2/sample1.mzML`" in text
    assert "replace" in text


def test_workflow_input_problems(tmp_path):
    from unittest.mock import MagicMock
    from src.workflow.WorkflowManager import WorkflowManager

    Path(tmp_path, "input-files", "mzML-files").mkdir(parents=True)
    wf = object.__new__(WorkflowManager)
    wf.workflow_dir = tmp_path
    wf.parameter_manager = MagicMock()
    wf.parameter_manager.get_parameters_from_json.return_value = {
        "mzML-files": ["p1/a.mzML", "p2/a.mzML"]}
    assert "**a**" in wf.input_problems()
    wf.parameter_manager.get_parameters_from_json.return_value = {
        "mzML-files": ["p1/a.mzML", "p2/b.mzML"]}
    assert wf.input_problems() == ""


def test_an_online_start_refuses_clashing_selections(tmp_path):
    """The sync service checks the selections too, before params.json is written."""
    import pytest
    from src.sync import runs

    workflow_dir = Path(tmp_path, "topp-workflow")
    Path(workflow_dir, "input-files", "mzML-files").mkdir(parents=True)
    params = {"mzML-files": ["p1/a.mzML", "p2/a.mzML"]}
    assert "**a**" in runs.selection_problem(workflow_dir, params)
    assert runs.selection_problem(workflow_dir, {"mzML-files": ["p1/a.mzML"]}) == ""
    with pytest.raises(ValueError, match="a"):
        runs.start(None, tmp_path, "topp-workflow", "src.Workflow:Workflow", params)
    assert not Path(workflow_dir, "params.json").exists()


def test_an_online_start_checks_uploads_from_any_folder(tmp_path):
    """Uploaded inputs are a selection even where the key has no folder online."""
    import pytest
    from src.sync import runs

    ref = runs.WORKSPACE_REF
    params = {"mzML-files": [f"{ref}mzML-files/plate1/a.mzML", f"{ref}mzML-files/plate2/a.mzML"],
              "labels": ["a.x", "a.y"]}
    workflow_dir = Path(tmp_path, "topp-workflow")
    assert "`plate1/a.mzML`" in runs.selection_problem(workflow_dir, params)
    assert runs.selection_problem(workflow_dir, {"labels": ["a.x", "a.y"]}) == ""
    mixed = {"mzML-files": [f"{ref}mzML-files/plate1/a.mzML", "/data/plate2/a.mzML"]}
    assert "**a**" in runs.selection_problem(workflow_dir, mixed)
    from unittest.mock import MagicMock
    for selection in (params, mixed):
        qm = MagicMock()
        qm.load_job_id.return_value = None
        with pytest.raises(ValueError):
            runs.start(qm, tmp_path, "topp-workflow", "src.Workflow:Workflow", selection)
        qm.submit_job.assert_not_called()
        assert not workflow_dir.exists()


# ----------------------------------------------------------------------------- file contents

from src.workflow.input_check import (  # noqa: E402
    check_file, check_files, count_summary, selection_checks, unusable_message, warning_message,
)

MZML = """<?xml version="1.0" encoding="utf-8"?>
<indexedmzML xmlns="http://psi.hupo.org/ms/mzml">
<mzML xmlns="http://psi.hupo.org/ms/mzml" version="1.1.0">
<run id="r"><spectrumList count="{n}" defaultDataProcessingRef="dp">
{spectra}
</spectrumList></run>
</mzML>
<indexList count="1"></indexList>
</indexedmzML>
"""


def _mzml(path, n=2, cut=False):
    text = MZML.format(n=n, spectra="".join(f'<spectrum index="{i}" id="scan={i}"></spectrum>\n' for i in range(n)))
    if cut:
        text = text[: len(text) // 2]
    Path(path).write_text(text, encoding="utf-8")
    return str(path)


def test_a_good_mzml_counts_its_spectra(tmp_path):
    c = check_file(_mzml(tmp_path / "a.mzML", 3))
    assert (c.kind, c.count, c.errors, c.warnings) == ("spectra", 3, [], [])


def test_a_cut_off_empty_or_foreign_mzml_cannot_be_used(tmp_path):
    assert any("cut off" in e for e in check_file(_mzml(tmp_path / "cut.mzML", 50, cut=True)).errors)
    assert check_file(_mzml(tmp_path / "none.mzML", 0)).errors == ["holds no spectra"]
    Path(tmp_path, "empty.mzML").write_bytes(b"")
    assert check_file(tmp_path / "empty.mzML").errors == ["is empty"]
    Path(tmp_path, "x.mzML").write_text("RAW binary data", encoding="utf-8")
    assert check_file(tmp_path / "x.mzML").errors == ["is not an mzML file"]


def test_fasta_counts_proteins_and_warns(tmp_path):
    good = tmp_path / "db.fasta"
    good.write_text(">sp|P1|A desc\nMKV\nLLK\n>sp|P2|B\nPEPTIDE\n", encoding="utf-8")
    c = check_file(good)
    assert (c.kind, c.count, c.errors, c.warnings) == ("proteins", 2, [], [])
    odd = tmp_path / "odd.fasta"
    odd.write_bytes(b"\xef\xbb\xbf>P1\nmkv\n>P1\nPEP\n>P3\n")
    w = check_file(odd).warnings
    assert any("byte-order mark" in x for x in w)
    assert any("repeats accessions (`P1`)" in x for x in w)
    assert any("lowercase residues on 1 lines" in x for x in w)
    assert any("1 entries without a sequence" in x for x in w)
    assert check_file(odd).errors == []


def test_a_file_that_is_not_fasta_or_has_no_proteins_cannot_be_used(tmp_path):
    p = tmp_path / "x.fasta"
    p.write_text("PEPTIDE\n", encoding="utf-8")
    assert "is not a FASTA file" in check_file(p).errors[0]
    p.write_text("\n\n", encoding="utf-8")
    assert check_file(p).errors == ["holds no proteins"]


def test_other_and_missing_files_are_not_checked(tmp_path):
    raw = tmp_path / "a.raw"
    raw.write_bytes(b"\x01\x02")
    assert check_file(raw).errors == [] and check_file(raw).kind == ""
    assert check_file(tmp_path / "gone.mzML").errors == []


def test_a_changed_file_is_read_again(tmp_path):
    path = _mzml(tmp_path / "a.mzML", 2)
    assert check_file(path).count == 2
    _mzml(tmp_path / "a.mzML", 5)
    assert check_file(path).count == 5


def test_messages_and_summary(tmp_path):
    checks = check_files([_mzml(tmp_path / "a.mzML", 2), _mzml(tmp_path / "b.mzML", 3)])
    assert count_summary(checks) == "5 spectra in 2 files"
    assert unusable_message(checks) == "" and warning_message(checks) == ""
    bad = check_files(_mzml(tmp_path / "c.mzML", 0))
    assert unusable_message(bad) == "This file cannot be used: `c.mzML` holds no spectra. Replace it or leave it out."
    assert unusable_message(checks + bad + bad[:1]).startswith("This file")  # one distinct file
    two = check_files([str(tmp_path / "c.mzML"), _mzml(tmp_path / "d.mzML", 0)])
    assert unusable_message(two).startswith("2 files cannot be used")


def test_selection_checks_follow_the_input_folders(tmp_path):
    for key in ("mzML-files", "fasta"):
        Path(tmp_path, "input-files", key).mkdir(parents=True)
    a = _mzml(tmp_path / "a.mzML", 0)
    found = selection_checks(tmp_path, {"mzML-files": [a], "fasta": "", "other": [a]})
    assert list(found) == ["mzML-files"] and found["mzML-files"][0].errors == ["holds no spectra"]


def test_comments_after_the_root_element_are_allowed(tmp_path):
    path = _mzml(tmp_path / "c.mzML", 2)
    with open(path, "a", encoding="utf-8") as f:
        f.write("<!-- written by a converter -->\n<?pi done?>\n\n")
    assert check_file(path).errors == []


def test_a_read_error_is_not_remembered(tmp_path, monkeypatch):
    import src.workflow.input_check as ic
    path = _mzml(tmp_path / "r.mzML", 2)
    real = ic._mzml

    def fail(*_):
        raise PermissionError(13, "Permission denied")

    # ic.check_file, not the name imported above: other tests reload src.workflow.
    monkeypatch.setattr(ic, "_mzml", fail)
    assert any("cannot be read" in e for e in ic.check_file(path).errors)
    monkeypatch.setattr(ic, "_mzml", real)
    assert ic.check_file(path).errors == []
