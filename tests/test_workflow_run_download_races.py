"""Run downloads recover when another tab removes or replaces an archive."""

import importlib
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from streamlit.delta_generator import DeltaGenerator
from streamlit.testing.v1 import AppTest
from test_run_manager import _finished_run, _manager_script


@pytest.fixture
def run_download(tmp_path):
    # Legacy tests purge workflow imports during collection. Match the fresh
    # class imported by the real Streamlit script, not a collection-time copy.
    runs = importlib.import_module("src.workflow.RunManager").RunManager(tmp_path)
    run_id = _finished_run(runs, "Download evidence")
    slug = runs.workflow_dir.name
    app = AppTest.from_function(_manager_script, args=(str(tmp_path),))
    app.run(timeout=30)
    assert not app.exception
    return runs, run_id, slug, app


def _prepared_key(slug, run_id):
    return f"_runs-{slug}-zip-{run_id}"


def _pack_key(slug, run_id):
    return f"runs-{slug}-zip-{run_id}"


@pytest.fixture
def downloaded_bytes(monkeypatch):
    """Keep real Streamlit rendering while recording its actual download data."""
    download = DeltaGenerator.download_button
    delivered = []

    def capture(self, label, *args, **kwargs):
        if label == "⬇️":
            delivered.append(kwargs["data"])
        return download(self, label, *args, **kwargs)

    monkeypatch.setattr(DeltaGenerator, "download_button", capture)
    return delivered


def test_completed_run_prepares_a_complete_download(run_download, downloaded_bytes):
    runs, run_id, slug, app = run_download
    app.button(key=_pack_key(slug, run_id)).click().run(timeout=30)
    assert not app.exception
    assert app.session_state[_prepared_key(slug, run_id)] is True
    assert downloaded_bytes and isinstance(downloaded_bytes[-1], bytes)
    with zipfile.ZipFile(BytesIO(downloaded_bytes[-1])) as archive:
        assert {"run.json", "results/out/table.tsv"} <= set(archive.namelist())
        assert archive.read("results/out/table.tsv") == b"out/table.tsv"
    assert runs.get(run_id)["status"] == "finished"


def test_prepared_archive_removed_at_read_is_reset_and_can_be_prepared_again(
    run_download, monkeypatch
):
    runs, run_id, slug, app = run_download
    archive = runs.zip(run_id)
    app.session_state[_prepared_key(slug, run_id)] = True
    read_bytes = Path.read_bytes
    removed = []

    def vanished(path):
        if path == archive and not removed:
            path.unlink()
            removed.append(path)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", vanished)
    app.run(timeout=30)
    assert not app.exception
    assert removed == [archive]
    assert any("prepared ZIP is no longer available" in message.value for message in app.info)
    assert app.session_state[_prepared_key(slug, run_id)] is False
    app.button(key=_pack_key(slug, run_id)).click().run(timeout=30)
    assert not app.exception
    assert app.session_state[_prepared_key(slug, run_id)] is True
    assert archive.is_file()


def test_deleted_run_during_zip_preparation_has_recoverable_error(run_download, monkeypatch):
    runs, run_id, slug, app = run_download
    prepare = type(runs).zip

    def deleted(manager, identity, *args, **kwargs):
        assert manager.delete(identity)
        return prepare(manager, identity, *args, **kwargs)

    monkeypatch.setattr(type(runs), "zip", deleted)
    app.button(key=_pack_key(slug, run_id)).click().run(timeout=30)
    assert not app.exception
    assert any("Could not prepare this run's ZIP" in message.value for message in app.error)
    assert app.session_state[_prepared_key(slug, run_id)] is False
    assert runs.get(run_id) is None
    assert not (runs.workflow_dir / "downloads" / f"{run_id}.zip").exists()
    app.run(timeout=30)
    assert not app.exception
    assert any("No runs yet" in message.value for message in app.info)


def test_zip_preparation_storage_error_retains_run_and_allows_retry(run_download, monkeypatch):
    runs, run_id, slug, app = run_download
    prepare = type(runs).zip

    def unavailable(*_args, **_kwargs):
        raise PermissionError("download folder is read-only")

    monkeypatch.setattr(type(runs), "zip", unavailable)
    app.button(key=_pack_key(slug, run_id)).click().run(timeout=30)
    assert not app.exception
    assert any("read-only" in message.value for message in app.error)
    assert app.session_state[_prepared_key(slug, run_id)] is False
    assert (runs.results_dir(run_id) / "out/table.tsv").read_text() == "out/table.tsv"
    monkeypatch.setattr(type(runs), "zip", prepare)
    app.button(key=_pack_key(slug, run_id)).click().run(timeout=30)
    assert not app.exception
    assert app.session_state[_prepared_key(slug, run_id)] is True


def test_prepared_archive_permission_error_is_reported_and_recoverable(run_download, monkeypatch):
    runs, run_id, slug, app = run_download
    archive = runs.zip(run_id)
    app.session_state[_prepared_key(slug, run_id)] = True
    read_bytes = Path.read_bytes

    def locked(path):
        if path == archive:
            raise PermissionError("archive temporarily locked")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", locked)
    app.run(timeout=30)
    assert not app.exception
    assert any("Could not read this run's ZIP" in message.value and "locked" in message.value for message in app.error)
    assert app.session_state[_prepared_key(slug, run_id)] is False
    assert archive.is_file()
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    app.button(key=_pack_key(slug, run_id)).click().run(timeout=30)
    assert not app.exception
    assert app.session_state[_prepared_key(slug, run_id)] is True


def test_prepared_archive_replacement_downloads_one_complete_blob(
    run_download, monkeypatch, downloaded_bytes, tmp_path
):
    runs, run_id, slug, app = run_download
    archive = runs.zip(run_id)
    replacement = tmp_path / "replacement.zip"
    with zipfile.ZipFile(replacement, "w") as output:
        output.writestr("complete.txt", "new complete archive")
    expected = replacement.read_bytes()
    app.session_state[_prepared_key(slug, run_id)] = True
    read_bytes = Path.read_bytes
    replaced = []

    def rotate(path):
        if path == archive and not replaced:
            replacement.replace(path)
            replaced.append(path)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", rotate)
    app.run(timeout=30)
    assert not app.exception
    assert replaced == [archive]
    assert downloaded_bytes[-1] == expected
    with zipfile.ZipFile(BytesIO(downloaded_bytes[-1])) as output:
        assert output.read("complete.txt") == b"new complete archive"
    assert app.session_state[_prepared_key(slug, run_id)] is True
