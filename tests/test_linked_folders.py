"""A folder a workspace links from its demo is made the workspace's own before
anything is written into it, so the demo every new workspace starts from is
never changed (src/workflow/linked_folders.py)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.workflow import linked_folders  # noqa: E402


@pytest.fixture
def linked(tmp_path):
    """A workspace whose cache/files/run is linked from a demo."""
    demo_run = tmp_path / "demo" / "cache" / "files" / "run"
    (demo_run / "report").mkdir(parents=True)
    (demo_run / "data.pq").write_text("demo")
    (demo_run / "report" / "report.md").write_text("demo report")
    files = tmp_path / "ws" / "cache" / "files"
    files.mkdir(parents=True)
    (files / "run").symlink_to(demo_run, target_is_directory=True)
    return tmp_path / "ws" / "cache", demo_run


def test_owned_folder_is_real_and_keeps_the_demo_files(linked):
    cache, demo_run = linked
    folder = linked_folders.own_folder(cache / "files" / "run", cache)
    assert folder.is_dir() and not folder.is_symlink()
    assert (folder / "data.pq").is_symlink()
    assert (folder / "data.pq").read_text() == "demo"
    # A file written there is the workspace's
    (folder / "data.pq").unlink()
    (folder / "data.pq").write_text("mine")
    (folder / "new.pq").write_text("new")
    assert (demo_run / "data.pq").read_text() == "demo"
    assert not (demo_run / "new.pq").exists()


def test_owning_a_subfolder_owns_the_linked_folder_above(linked):
    cache, demo_run = linked
    report = linked_folders.own_folder(cache / "files" / "run" / "report", cache)
    assert not (cache / "files" / "run").is_symlink()
    assert not report.is_symlink()
    (report / "archive.zip").write_text("zip")
    assert not (demo_run / "report" / "archive.zip").exists()
    assert (report / "report.md").read_text() == "demo report"


def test_a_folder_that_is_not_linked_is_left_alone(tmp_path):
    folder = tmp_path / "cache" / "files" / "new"
    assert linked_folders.own_folder(folder, tmp_path / "cache") == folder
    assert not folder.exists()


def test_folder_outside_the_root_is_refused(tmp_path):
    with pytest.raises(ValueError):
        linked_folders.own_folder(tmp_path / "elsewhere", tmp_path / "cache")


def test_owning_twice_keeps_the_first(linked):
    cache, _ = linked
    folder = linked_folders.own_folder(cache / "files" / "run", cache)
    (folder / "mine.pq").write_text("mine")
    linked_folders.own_folder(cache / "files" / "run", cache)
    assert (folder / "mine.pq").read_text() == "mine"
    assert [p.name for p in (cache / "files").iterdir()] == ["run"]


def test_removing_a_linked_folder_keeps_the_demo(linked):
    cache, demo_run = linked
    linked_folders.remove_folder(cache / "files" / "run")
    assert not (cache / "files" / "run").exists()
    assert (demo_run / "data.pq").read_text() == "demo"


def test_matches():
    assert linked_folders.matches("cache/files/run", ["cache/files/*"])
    assert not linked_folders.matches("cache/files", ["cache/files/*"])
    assert not linked_folders.matches("cache/files/run/sub", ["cache/files/*"])
    assert not linked_folders.matches("cache/files/run", [])
