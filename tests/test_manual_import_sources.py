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
