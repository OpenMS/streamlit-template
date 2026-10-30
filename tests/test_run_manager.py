"""Tests for multi-run workflows: RunManager and the run widgets."""

import json
import zipfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.workflow.RunManager import (
    CANCELLED,
    FAILED,
    FINISHED,
    RUNNING,
    RunManager,
)


def _finished_run(runs: RunManager, name: str, files=("out/table.tsv",)) -> str:
    run_id = runs.new_run(name)
    for rel in files:
        path = Path(runs.results_dir(run_id), rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel)
    runs.finish(run_id, FINISHED)
    return run_id


def test_new_run_creates_folder_metadata_and_params(tmp_path):
    params = Path(tmp_path, "params.json")
    params.write_text(json.dumps({"x": 1}))
    runs = RunManager(tmp_path)

    run_id = runs.new_run("  My   first run ", params)

    assert runs.results_dir(run_id).is_dir()
    run = runs.get(run_id)
    assert run["name"] == "My first run"
    assert run["status"] == RUNNING
    assert runs.params(run_id) == {"x": 1}


def test_default_names_and_unique_ids(tmp_path):
    runs = RunManager(tmp_path)
    first = runs.new_run()
    second = runs.new_run()
    assert first != second
    assert {r["name"] for r in runs.list_runs()} == {"Run 1", "Run 2"}


def test_finish_copies_logs_and_keeps_cancelled(tmp_path):
    runs = RunManager(tmp_path)
    Path(tmp_path, "logs").mkdir()
    Path(tmp_path, "logs", "minimal.log").write_text("WORKFLOW FINISHED")
    run_id = runs.new_run()

    runs.finish(run_id, FINISHED)
    assert runs.get(run_id)["status"] == FINISHED
    assert Path(runs.run_dir(run_id), "logs", "minimal.log").exists()

    cancelled = runs.new_run()
    runs.finish(cancelled, CANCELLED)
    runs.finish(cancelled, FAILED)  # the dying worker reports a failure
    assert runs.get(cancelled)["status"] == CANCELLED


def test_list_latest_rename_delete(tmp_path):
    runs = RunManager(tmp_path)
    old = _finished_run(runs, "old")
    failed = runs.new_run("broken")
    runs.finish(failed, FAILED)

    assert [r["id"] for r in runs.list_runs()][0] == failed
    assert runs.latest() == old
    assert runs.latest(None) == failed

    assert runs.rename(old, "renamed")
    assert runs.get(old)["name"] == "renamed"
    assert not runs.rename(old, "   ")
    assert not runs.rename(old, "x" * 101)

    assert runs.delete(old)
    assert runs.get(old) is None
    assert not runs.run_dir(old).exists()


def test_unsafe_ids_are_rejected(tmp_path):
    runs = RunManager(tmp_path)
    assert runs.get("../x") is None
    assert runs.get("..") is None
    assert not runs.delete("..")


def test_zip_has_results_params_logs_and_honours_exclude(tmp_path):
    runs = RunManager(tmp_path)
    Path(tmp_path, "params.json").write_text("{}")
    run_id = runs.new_run("zip me", Path(tmp_path, "params.json"))
    for rel in ["quant/proteins.csv", "insight_cache/x.parquet"]:
        path = Path(runs.results_dir(run_id), rel)
        path.parent.mkdir(parents=True)
        path.write_text(rel)
    runs.finish(run_id, FINISHED)

    with zipfile.ZipFile(runs.zip(run_id, exclude=["insight_cache"])) as zf:
        names = set(zf.namelist())
    assert "results/quant/proteins.csv" in names
    assert "params.json" in names
    assert "run.json" in names
    assert not any("insight_cache" in n for n in names)


def test_adopt_legacy_results(tmp_path):
    legacy = Path(tmp_path, "results", "feature-linking")
    legacy.mkdir(parents=True)
    Path(legacy, "feature_matrix.tsv").write_text("x")
    Path(tmp_path, "params.json").write_text("{}")
    runs = RunManager(tmp_path)

    run_id = runs.adopt_legacy_results()

    assert run_id is not None
    assert runs.get(run_id)["name"] == "Earlier run"
    assert runs.get(run_id)["status"] == FINISHED
    assert Path(runs.results_dir(run_id), "feature-linking", "feature_matrix.tsv").exists()
    assert not Path(tmp_path, "results").exists()
    # Only once: with runs present nothing is adopted again.
    Path(tmp_path, "results", "new").mkdir(parents=True)
    Path(tmp_path, "results", "new", "f").write_text("y")
    assert runs.adopt_legacy_results() is None


def test_adopt_legacy_ignores_empty_results(tmp_path):
    Path(tmp_path, "results").mkdir()
    assert RunManager(tmp_path).adopt_legacy_results() is None


def test_file_manager_writes_into_run(tmp_path):
    from src.workflow.FileManager import FileManager

    runs = RunManager(tmp_path)
    run_id = runs.new_run()
    fm = FileManager(tmp_path, runs.results_dir(run_id))
    out = fm.get_files("a.mzML", "featureXML", "feature-detection")
    assert Path(out[0]).parent == Path(runs.results_dir(run_id), "feature-detection")
    assert Path(out[0]).parent.is_dir()
    # Default stays <workflow_dir>/results
    assert FileManager(tmp_path).results_dir == Path(tmp_path, "results")


# Widgets


def _select_script(workflow_dir: str):
    from pathlib import Path

    import streamlit as st

    from src.workflow.RunManager import RunManager
    from src.workflow.run_widgets import select_run

    st.session_state["picked"] = select_run(RunManager(Path(workflow_dir)))


def test_select_run_defaults_to_newest_finished_and_remembers(tmp_path):
    runs = RunManager(tmp_path)
    first = _finished_run(runs, "first")
    second = _finished_run(runs, "second")
    runs.finish(runs.new_run("running"), FAILED)

    at = AppTest.from_function(_select_script, args=(str(tmp_path),)).run(timeout=30)
    assert not at.exception
    assert at.session_state["picked"] == second
    # Only finished runs are offered.
    options = at.selectbox[0].options
    assert len(options) == 2
    assert options[0].startswith("second · ") and options[1].startswith("first · ")

    at.selectbox[0].set_value(first).run(timeout=30)
    assert at.session_state["picked"] == first
    at.run(timeout=30)
    assert at.session_state["picked"] == first


def test_select_run_without_runs_returns_none(tmp_path):
    at = AppTest.from_function(_select_script, args=(str(tmp_path),)).run(timeout=30)
    assert not at.exception
    assert at.session_state["picked"] is None


def _manager_script(workflow_dir: str):
    from pathlib import Path

    from src.workflow.RunManager import RunManager
    from src.workflow.run_widgets import run_manager_section

    run_manager_section(RunManager(Path(workflow_dir)))


def test_run_manager_lists_and_deletes(tmp_path):
    runs = RunManager(tmp_path)
    keep = _finished_run(runs, "keep me")
    drop = _finished_run(runs, "drop me")

    at = AppTest.from_function(_manager_script, args=(str(tmp_path),)).run(timeout=30)
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "keep me" in text and "drop me" in text

    at.button(key=f"runs-{Path(tmp_path).name}-delete-{drop}").click().run(timeout=30)
    assert not at.exception
    assert runs.get(drop) is None
    assert runs.get(keep) is not None


def test_run_manager_renames_and_zips(tmp_path):
    runs = RunManager(tmp_path)
    run_id = _finished_run(runs, "before")
    slug = Path(tmp_path).name

    at = AppTest.from_function(_manager_script, args=(str(tmp_path),)).run(timeout=30)
    at.text_input(key=f"runs-{slug}-name-{run_id}").set_value("after")
    at.button(key=f"runs-{slug}-rename-{run_id}").click().run(timeout=30)
    assert not at.exception
    assert runs.get(run_id)["name"] == "after"

    at.button(key=f"runs-{slug}-zip-{run_id}").click().run(timeout=30)
    assert not at.exception
    assert Path(tmp_path, "downloads", f"{run_id}.zip").exists()


def test_run_manager_without_runs(tmp_path):
    at = AppTest.from_function(_manager_script, args=(str(tmp_path),)).run(timeout=30)
    assert not at.exception
    assert "No runs yet" in at.info[0].value
