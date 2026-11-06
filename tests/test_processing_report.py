"""The processing report: what was done to each input file, with which tool, version and parameters."""

import json
import zipfile
from pathlib import Path

import pytest

from src.workflow.processing_report import (
    build_report,
    command_io,
    file_stem,
    ini_version,
    report_for,
    report_params,
    to_markdown,
    to_pdf,
)
from src.workflow.progress import RunProgress, read_progress
from src.workflow.RunManager import DESIGN_FILE, FINISHED, FOLLOW_UP_KEY, RunManager


def _step(progress, tool, io, params=None, version="3.6.0", kind="topp", ok=True):
    """Record one finished tool call the way run_topp() does."""
    step = progress.start_step(
        tool,
        [Path(c["inputs"][0]).name for c in io],
        provenance={"kind": kind, "program": tool, "version": version,
                    "params": params or {}, "io": io},
    )
    for i in range(len(io)):
        progress.file_started(step, i)
        progress.file_finished(step, i, ok, returncode=0 if ok else 1)
    progress.end_step(step)
    return step


def _workflow(tmp_path):
    """Two mzML files: detection per file, linking of both, a table, a filtered table."""
    progress = RunProgress(tmp_path)
    _step(progress, "FeatureFinderMetabo",
          command_io({"in": ["/d/A.mzML", "/d/B.mzML"], "out": ["/r/A.featureXML", "/r/B.featureXML"]}, 2),
          params={"algorithm:common:noise_threshold_int": "1000.0"})
    _step(progress, "FeatureLinkerUnlabeledKD",
          command_io({"in": [["/r/A.featureXML", "/r/B.featureXML"]], "out": ["/r/m.consensusXML"]}, 1))
    _step(progress, "export.py", command_io({"in": ["/r/m.consensusXML"], "out": ["/r/m.tsv"]}, 1),
          version=None, kind="python")
    return progress


def test_command_io_pairs_inputs_and_outputs_per_command():
    io = command_io({"in": ["a", "b"], "out": ["x", "y"], "database": ["db.fasta"]}, 2)
    assert io == [
        {"inputs": ["a", "db.fasta"], "outputs": ["x"], "shared": ["db.fasta"]},
        {"inputs": ["b", "db.fasta"], "outputs": ["y"], "shared": ["db.fasta"]},
    ]
    # A collected list is one command with every file as input
    assert command_io({"in": [["a", "b"]], "out": ["m"]}, 1) == [{"inputs": ["a", "b"], "outputs": ["m"]}]


def test_report_params_shows_file_names_and_leaves_out_threads(tmp_path):
    db = Path(tmp_path, "db.fasta")
    db.write_text(">P1\nPEPTIDE\n")
    shown = report_params({"threads": 4, "flag": True, "db": str(db), "tol": 10.0, "rule": "a/b"})
    # Only an existing file is shortened to its name; other text with a slash stays
    assert shown == {"flag": "true", "db": "db.fasta", "tol": "10.0", "rule": "a/b"}


def test_ini_version(tmp_path):
    ini = Path(tmp_path, "Tool.ini")
    ini.write_text('<NODE name="Tool"><ITEM name="version" value="3.6.0" type="string"/></NODE>')
    assert ini_version(ini) == "3.6.0"
    assert ini_version(Path(tmp_path, "missing.ini")) is None


def test_each_input_file_lists_every_tool_that_worked_on_it(tmp_path):
    _workflow(tmp_path)
    report = build_report(read_progress(tmp_path), app_name="App", app_version="1.0", workflow="WF")

    assert [i["name"] for i in report["inputs"]] == ["A.mzML", "B.mzML"]
    calls = report["inputs"][0]["calls"]
    assert [c["tool"] for c in calls] == ["FeatureFinderMetabo", "FeatureLinkerUnlabeledKD", "export.py"]
    assert calls[0]["outputs"] == ["A.featureXML"]
    assert calls[1]["with"] == 1  # linked with one other file
    assert calls[2]["outputs"] == ["m.tsv"]
    assert report["software"] == [
        {"name": "FeatureFinderMetabo", "version": "3.6.0"},
        {"name": "FeatureLinkerUnlabeledKD", "version": "3.6.0"},
        {"name": "export.py", "version": "Python script"},
    ]
    assert report["steps"][0]["params"] == {"algorithm:common:noise_threshold_int": "1000.0"}


def test_a_shared_database_is_not_an_input_file(tmp_path):
    progress = RunProgress(tmp_path)
    # One file searched: the database is shared by its key, not by being reused
    _step(progress, "CometAdapter",
          command_io({"in": ["/d/A.mzML"], "database": ["/d/db.fasta"], "out": ["/r/A.idXML"]}, 1))
    _step(progress, "PercolatorAdapter", command_io({"in": ["/r/A.idXML"], "out": ["/r/A_perc.idXML"]}, 1))
    report = build_report(read_progress(tmp_path))

    assert [i["name"] for i in report["inputs"]] == ["A.mzML"]
    calls = report["inputs"][0]["calls"]
    assert [c["tool"] for c in calls] == ["CometAdapter", "PercolatorAdapter"]
    assert calls[0]["with"] == 0


def test_an_alias_keeps_a_converted_file_with_its_original(tmp_path):
    progress = RunProgress(tmp_path)
    progress.record_alias("/cache/A.mzML", "/d/A.raw", "converted to mzML in an earlier run")
    _step(progress, "FeatureFinderMetabo", command_io({"in": ["/cache/A.mzML"], "out": ["/r/A.featureXML"]}, 1))

    report = build_report(read_progress(tmp_path))

    assert [i["name"] for i in report["inputs"]] == ["A.raw"]
    assert report["inputs"][0]["notes"] == ["converted to mzML in an earlier run"]


def test_markdown_names_files_tools_versions_and_parameters(tmp_path):
    _workflow(tmp_path)
    md = to_markdown(build_report(read_progress(tmp_path), app_name="App", app_version="1.0",
                                  workflow="WF", run={"name": "First run", "status": FINISHED},
                                  params={"run-python-script": True}))

    assert md.startswith("# Processing report: First run")
    assert "### A.mzML" in md and "### B.mzML" in md
    assert "| 1 | FeatureFinderMetabo | 3.6.0 | done |" in md
    assert "| algorithm:common:noise_threshold_int | 1000.0 |" in md
    assert "| run-python-script | true |" in md
    assert "All parameters at their defaults." in md


def test_pdf(tmp_path):
    pytest.importorskip("reportlab")
    _workflow(tmp_path)
    pdf = to_pdf(build_report(read_progress(tmp_path), run={"name": "First run"}))
    assert pdf.startswith(b"%PDF")


def test_report_for_a_run_reads_its_own_logs_and_parameters(tmp_path):
    runs = RunManager(tmp_path)
    Path(tmp_path, "params.json").write_text(json.dumps({f"{Path(tmp_path).name}-param-x": 1}))
    run_id = runs.new_run("First run", Path(tmp_path, "params.json"))
    _workflow(Path(runs.run_dir(run_id)))
    runs.finish(run_id, FINISHED)

    report = report_for(tmp_path, run_id, settings={"app-name": "App", "version": "1.0"})

    assert report["run"]["name"] == "First run"
    assert report["settings"] == {"x": "1"}  # the workflow prefix removed
    assert file_stem(report).startswith("processing-report")


def test_run_zip_contains_the_report(tmp_path):
    runs = RunManager(tmp_path)
    run_id = runs.new_run("First run")
    _workflow(Path(runs.run_dir(run_id)))
    runs.finish(run_id, FINISHED)

    with zipfile.ZipFile(runs.zip(run_id)) as zf:
        names = zf.namelist()
        report = [n for n in names if n.endswith("processing-report.md")]
        assert report, names
        assert "A.mzML" in zf.read(report[0]).decode()


def test_restore_settings_makes_a_runs_parameters_the_next_ones(tmp_path):
    params = Path(tmp_path, "params.json")
    params.write_text(json.dumps({"identify": False, "Tool": {"a": 1, "b": 2}}))
    Path(tmp_path, DESIGN_FILE).write_text("design of run 1")
    runs = RunManager(tmp_path)
    run_id = runs.new_run("Deconvolution only", params)
    assert Path(runs.run_dir(run_id), DESIGN_FILE).read_text() == "design of run 1"

    # The user changes the settings and the design for something else
    params.write_text(json.dumps({"identify": False, "Tool": {"a": 9}}))
    Path(tmp_path, DESIGN_FILE).write_text("another design")

    assert runs.restore_settings(run_id, {"identify": True, "Tool": {"b": 3}}, note="with identification")

    restored = json.loads(params.read_text())
    assert restored["identify"] is True
    assert restored["Tool"] == {"a": 1, "b": 3}
    assert restored[FOLLOW_UP_KEY] == {"run": run_id, "name": "Deconvolution only",
                                       "note": "with identification"}
    assert Path(tmp_path, DESIGN_FILE).read_text() == "design of run 1"
    assert not runs.restore_settings("no-such-run")


def test_apply_settings_starts_from_stored_settings(tmp_path):
    """An app without run folders starts a follow-up from the settings it stored itself."""
    from src.workflow.RunManager import apply_settings

    Path(tmp_path, "params.json").write_text(json.dumps({"fasta-file": "db.fasta"}))
    written = apply_settings(tmp_path, {"mzML-files": ["a.mzML"], "Tool": {"a": 1}, FOLLOW_UP_KEY: {"old": 1}},
                             {"identify": True, "Tool": {"b": 2}}, {"name": "a", "note": "with identification"})

    assert json.loads(Path(tmp_path, "params.json").read_text()) == written == {
        "mzML-files": ["a.mzML"], "Tool": {"a": 1, "b": 2}, "identify": True,
        FOLLOW_UP_KEY: {"name": "a", "note": "with identification"},
    }


def test_report_without_run_folders_names_what_the_last_start_followed(tmp_path):
    _workflow(tmp_path)
    Path(tmp_path, "params.json").write_text("{}")
    Path(tmp_path, "last-follow-up.json").write_text(json.dumps({"name": "A", "note": "with identification"}))

    report = report_for(tmp_path, settings={})

    assert report["run"]["follows"] == "A"
    assert "| Settings from | A (with identification) |" in to_markdown(report)
