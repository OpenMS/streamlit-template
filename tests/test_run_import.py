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

from src.workflow import RunManager as run_manager_module  # noqa: E402
from src.workflow.RunManager import (  # noqa: E402
    FAILED,
    FINISHED,
    MAX_NAME_LENGTH,
    RUNNING,
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
    [
        "../evil.txt", "results/../../evil.txt", "/etc/evil", "C:/evil.txt",
        "results\\..\\evil", "results/NUL", "results/con.txt", "results/LPT1/a.tsv",
        "results/aux. ",
    ],
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


def test_names_like_reserved_ones_are_kept(tmp_path):
    runs = RunManager(tmp_path / "wf")
    run_id = runs.import_zip(_zip({"results/nullable.tsv": "1", "results/console/a": "2"}))
    assert (runs.results_dir(run_id) / "nullable.tsv").exists()
    assert (runs.results_dir(run_id) / "console" / "a").exists()


def test_run_without_result_files_round_trips(tmp_path):
    src = RunManager(tmp_path / "src")
    run_id = src.new_run("Empty")
    src.finish(run_id, FINISHED)
    archive = src.zip(run_id)
    with zipfile.ZipFile(archive) as zf:
        assert not any(n.startswith("results/") for n in zf.namelist())

    dst = RunManager(tmp_path / "dst")
    new_id = dst.import_zip(archive)
    assert dst.get(new_id)["name"] == "Empty"
    assert dst.results_dir(new_id).is_dir()
    # Also inside one top folder
    wrapped = dst.import_zip(_zip({"Run 9/run.json": json.dumps({"name": "Run 9"})}))
    assert dst.get(wrapped)["name"] == "Run 9"


def test_interrupted_run_is_imported_as_failed(tmp_path):
    runs = RunManager(tmp_path / "wf")
    run_id = runs.import_zip(_zip({
        "run.json": json.dumps({"name": "Cut off", "status": RUNNING}),
        "results/partial.tsv": "1",
    }))
    assert runs.get(run_id)["status"] == FAILED


def test_bad_timestamps_are_replaced(tmp_path):
    runs = RunManager(tmp_path / "wf")
    run_id = runs.import_zip(_zip({
        "run.json": json.dumps({"created": 123, "finished": ["x"], "status": FINISHED}),
        "results/a.tsv": "1",
    }))
    run = runs.get(run_id)
    assert isinstance(run["created"], str) and run["created"]
    assert "finished" not in run
    # list_runs() sorts by "created": a number there would break it
    runs.import_zip(_zip({"run.json": json.dumps({"created": "not a time"}), "results/b": "1"}))
    assert len(runs.list_runs()) == 2
    for r in runs.list_runs():
        run_manager_module.format_time(r["created"])


def test_name_stays_within_the_limit_with_a_suffix(tmp_path):
    runs = RunManager(tmp_path / "wf")
    long = "x" * (MAX_NAME_LENGTH + 20)
    entries = {"run.json": json.dumps({"name": long}), "results/a": "1"}
    first = runs.import_zip(_zip(entries))
    second = runs.import_zip(_zip(entries))
    third = runs.import_zip(_zip(entries))
    names = [runs.get(r)["name"] for r in (first, second, third)]
    assert names[0] == "x" * MAX_NAME_LENGTH
    assert names[1].endswith(" (2)") and names[2].endswith(" (3)")
    assert all(len(n) <= MAX_NAME_LENGTH for n in names)
    assert len(set(names)) == 3


def test_size_and_count_limits(tmp_path, monkeypatch):
    runs = RunManager(tmp_path / "wf")
    monkeypatch.setattr(run_manager_module, "MAX_IMPORT_MEMBERS", 3)
    with pytest.raises(RunImportError, match="files, more than"):
        runs.import_zip(_zip({f"results/{i}": "" for i in range(4)}))
    monkeypatch.setattr(run_manager_module, "MAX_RUN_FILE_BYTES", 100)
    with pytest.raises(RunImportError, match="run.json is larger"):
        runs.import_zip(_zip({"run.json": json.dumps({"name": "y" * 200}), "results/a": "1"}))
    monkeypatch.setattr(run_manager_module, "MAX_PARAMS_FILE_BYTES", 100)
    with pytest.raises(RunImportError, match="params.json is larger"):
        runs.import_zip(_zip({"params.json": json.dumps({"k": "z" * 200}), "results/a": "1"}))
    assert runs.list_runs() == []


def test_damaged_member_data_is_refused(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("results/a.tsv", "".join(f"{i}\t{i * i}\n" for i in range(5000)))
    data = bytearray(buf.getvalue())
    # Corrupt the compressed data of the one member, between its local
    # header and the central directory at the end
    for i in range(200, 240):
        data[i] ^= 0xFF
    runs = RunManager(tmp_path / "wf")
    with pytest.raises(RunImportError, match="damaged"):
        runs.import_zip(io.BytesIO(bytes(data)))
    assert runs.list_runs() == []


def test_unreadable_members_are_refused(tmp_path, monkeypatch):
    runs = RunManager(tmp_path / "wf")
    # Over-nested JSON in run.json: json.loads raises RecursionError
    nested = "[" * 100_000 + "]" * 100_000
    with pytest.raises(RunImportError, match="can not be read"):
        runs.import_zip(_zip({"run.json": nested, "results/a": "1"}))

    # Encrypted members: ZipFile.open raises RuntimeError
    def encrypted(*args, **kwargs):
        raise RuntimeError("File 'results/a' is encrypted, password required")

    archive = _zip({"results/a": "1"})
    monkeypatch.setattr(zipfile.ZipFile, "open", encrypted)
    with pytest.raises(RunImportError, match="can not be read"):
        runs.import_zip(archive)
    assert runs.list_runs() == []
