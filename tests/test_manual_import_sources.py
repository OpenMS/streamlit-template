"""An upload with manual_import_sources is not filled automatically by that
source: files of its type go nowhere unless the user picks it as their target.
Other sources, and other uploads, still sort by file type."""
from src.data_import import job, ui

TARGETS = {
    "mzML-files": {"name": "MS data", "file_types": ["mzML"]},
    "fasta": {
        "name": "Database",
        "file_types": ["fasta"],
        "manual_import_sources": ["pride"],
    },
}


def test_pride_does_not_route_to_a_manual_only_upload():
    targets = ui._targets_for_source(TARGETS, "pride")
    assert job.target_for("run1.mzML", targets) == "mzML-files"
    assert job.target_for("proteome.fasta", targets) == ""
    assert job.target_for("proteome.fasta.gz", targets) == ""


def test_other_sources_still_route_by_type():
    targets = ui._targets_for_source(TARGETS, "link")
    assert job.target_for("proteome.fasta", targets) == "fasta"


def test_upload_without_option_routes_as_before():
    plain = {"mzML-files": {"name": "MS data", "file_types": ["mzML"]}}
    assert job.target_for("a.mzML", plain) == "mzML-files"
    assert job.target_for("a.mzML", ui._targets_for_source(plain, "pride")) == "mzML-files"


def test_manual_only_upload_stays_a_target_the_user_can_pick():
    targets = ui._targets_for_source(TARGETS, "pride")
    assert set(targets) == set(TARGETS)
    assert targets["fasta"]["auto_route"] is False


def _archive_job(tmp_path, target):
    import shutil
    import zipfile

    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("run1.mzML", "<mzML/>")
        zf.writestr("proteome.fasta", ">p\nPEPTIDE\n")
    targets = ui._targets_for_source({
        key: {**t, "dir": str(tmp_path / key)} for key, t in TARGETS.items()
    }, "pride")
    item = {"id": "a1", "name": "data.zip", "path": "data.zip", "kind": "archive",
            "size": archive.stat().st_size, "target": target,
            "files": [{"path": "data.zip", "url": "https://example.org/data.zip",
                       "size": archive.stat().st_size}]}
    runner = job._Job(tmp_path / "link-import", [item], targets, guard=False,
                      allowed_hosts=None, max_bytes=None)
    runner.fetch = lambda _item, _f, dest, base=0: (
        dest.parent.mkdir(parents=True, exist_ok=True), shutil.copy(archive, dest), dest)[2]
    runner.run_item(item)
    return runner


def test_archive_sent_to_a_manual_only_upload_fills_it(tmp_path):
    runner = _archive_job(tmp_path, "fasta")
    assert not runner.status["errors"]
    assert (tmp_path / "fasta" / "proteome.fasta").exists()
    assert not (tmp_path / "mzML-files").exists()
    assert runner.status["skipped"] == ["data.zip/run1.mzML"]


def test_unpacked_archive_still_skips_a_manual_only_upload(tmp_path):
    runner = _archive_job(tmp_path, "*")
    assert (tmp_path / "mzML-files" / "run1.mzML").exists()
    assert not (tmp_path / "fasta").exists()
    assert runner.status["skipped"] == ["data.zip/proteome.fasta"]
