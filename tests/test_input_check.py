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
