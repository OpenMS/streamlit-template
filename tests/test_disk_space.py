"""The disk-space warning before a run (src/workflow/disk_space.py)."""
from src.workflow.disk_space import format_bytes, input_bytes, space_warning


def _inputs(tmp_path):
    folder = tmp_path / "input-files" / "mzML-files"
    folder.mkdir(parents=True)
    a = folder / "a.mzML"
    a.write_bytes(b"x" * 1000)
    b = folder / "b.mzML"
    b.write_bytes(b"x" * 3000)
    bruker = folder / "c.d"
    bruker.mkdir()
    (bruker / "analysis.tdf").write_bytes(b"x" * 500)
    return [str(a), str(b), str(bruker)]


def test_input_bytes_counts_each_selected_file_once(tmp_path):
    files = _inputs(tmp_path)
    params = {"mzML-files": files, "again": files[0], "_defaults": {"x": files[1]},
              "unit": "ppm", "tol": 10}
    assert input_bytes(params) == 4500


def test_warning_when_estimate_exceeds_free_space(tmp_path):
    params = {"mzML-files": _inputs(tmp_path)}
    message = space_warning(params, tmp_path, factor=2.0, free=8000)
    assert "9 KB" in message and "8 KB" in message and "4 KB" in message
    assert space_warning(params, tmp_path, factor=2.0, free=9000) == ""


def test_no_warning_when_switched_off_or_unknown(tmp_path):
    params = {"mzML-files": _inputs(tmp_path)}
    assert space_warning(params, tmp_path, factor=0, free=1) == ""
    assert space_warning({}, tmp_path, factor=2.0, free=0) == ""


def test_free_space_of_missing_folder_is_read_from_its_parent(tmp_path):
    params = {"mzML-files": _inputs(tmp_path)}
    # A workflow folder that does not exist yet: no error, no warning on a
    # disk with room for 9 KB.
    assert space_warning(params, tmp_path / "not" / "yet", factor=2.0) == ""


def test_format_bytes():
    assert format_bytes(512) == "512 B"
    assert format_bytes(4_500_000) == "4 MB"
    assert format_bytes(3_400_000_000) == "3.4 GB"
    assert format_bytes(1_200_000_000_000) == "1.2 TB"
