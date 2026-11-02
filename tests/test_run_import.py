"""
Opening a run from a ZIP: RunManager.import_zip() takes what RunManager.zip()
writes (or a ZIP of the run folder) and adds it as a new run, refusing
anything that could write outside the run folder.
"""
import io
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.workflow.RunManager import (  # noqa: E402
    FAILED,
    FINISHED,
    RunImportError,
    RunManager,
)


def _finished_run(runs: RunManager, workflow_dir: Path) -> str:
    workflow_dir.mkdir(parents=True, exist_ok=True)
    params = workflow_dir / "params.json"
    params.write_text(json.dumps({"mzML-files": ["a.mzML"], "Tool": {"x": 2}}))
    run_id = runs.new_run("Spike-in 1:10", params)
    (runs.results_dir(run_id) / "feature-linking").mkdir()
    (runs.results_dir(run_id) / "feature-linking" / "table.tsv").write_text("a\tb\n1\t2\n")
    (workflow_dir / "logs").mkdir()
    (workflow_dir / "logs" / "minimal.log").write_text("WORKFLOW FINISHED\n")
    runs.finish(run_id, FINISHED)
    return run_id


def _zip(entries: dict, symlink: str = None) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    buf.seek(0)
    return buf


def test_round_trip_keeps_results_params_logs_and_name(tmp_path):
    src_dir = tmp_path / "src-workflow"
    src = RunManager(src_dir)
    run_id = _finished_run(src, src_dir)
    archive = src.zip(run_id)

    dst = RunManager(tmp_path / "other-workflow")
    new_id = dst.import_zip(archive)
    run = dst.get(new_id)
    assert run["name"] == "Spike-in 1:10"
    assert run["status"] == FINISHED
    assert run["created"] == src.get(run_id)["created"]
    assert "imported" in run
    assert (dst.results_dir(new_id) / "feature-linking" / "table.tsv").read_text() == "a\tb\n1\t2\n"
    assert dst.params(new_id) == {"mzML-files": ["a.mzML"], "Tool": {"x": 2}}
    assert (dst.run_dir(new_id) / "logs" / "minimal.log").exists()
    assert dst.latest(FINISHED) == new_id
    # No temporary folder is left behind
    assert [p.name for p in dst.workflow_dir.iterdir()] == ["runs"]

    # Importing again gives a second run with a distinct name
    again = dst.import_zip(archive)
    assert again != new_id
    assert dst.get(again)["name"] == "Spike-in 1:10 (2)"
    # An explicit name wins
    assert dst.get(dst.import_zip(archive, name="  Mine "))["name"] == "Mine"


def test_zip_of_the_run_folder_and_minimal_zip(tmp_path):
    runs = RunManager(tmp_path / "wf")
    wrapped = _zip({
        "Run 3/run.json": json.dumps({"name": "Run 3", "status": FAILED}),
        "Run 3/results/out.txt": "x",
        "Run 3/params.json": "{not json",
    })
    run_id = runs.import_zip(wrapped)
    assert runs.get(run_id)["status"] == FAILED
    assert (runs.results_dir(run_id) / "out.txt").read_text() == "x"
    # Unreadable parameters are dropped, not kept as a broken file
    assert not runs.params_file(run_id).exists()

    bare = runs.import_zip(_zip({"results/a.tsv": "1"}))
    assert runs.get(bare)["name"] == "Imported run"
    assert runs.get(bare)["status"] == FINISHED


@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "results/../../evil.txt", "/etc/evil", "C:/evil.txt", "results\\..\\evil"],
)
def test_path_traversal_is_refused(tmp_path, name):
    runs = RunManager(tmp_path / "wf")
    with pytest.raises(RunImportError, match="unsafe path"):
        runs.import_zip(_zip({"results/a.tsv": "1", name: "pwned"}))
    assert not (tmp_path / "evil.txt").exists()
    assert runs.list_runs() == []
    assert not (tmp_path / "wf").exists() or not any((tmp_path / "wf").iterdir())


def test_other_refusals(tmp_path):
    runs = RunManager(tmp_path / "wf")
    with pytest.raises(RunImportError, match="symbolic link"):
        runs.import_zip(_zip({"results/a.tsv": "1"}, symlink="results/link"))
    with pytest.raises(RunImportError, match="not a ZIP"):
        runs.import_zip(io.BytesIO(b"plain text"))
    with pytest.raises(RunImportError, match="no run"):
        runs.import_zip(_zip({"notes.txt": "hello", "data/x.csv": "1"}))
    with pytest.raises(RunImportError, match="more than"):
        runs.import_zip(_zip({"results/big.bin": "0" * 5000}), max_bytes=1000)
    assert runs.list_runs() == []
