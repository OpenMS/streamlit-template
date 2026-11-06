"""The time limit of a queued run grows with its input files (src/workflow/job_timeout.py)."""
import json
from pathlib import Path

from src.workflow.job_timeout import count_input_files, format_duration, job_timeout


def test_counts_selected_files_once_and_ignores_plain_values(tmp_path):
    files = []
    for name in ("a.mzML", "b.mzML", "db.fasta"):
        f = tmp_path / name
        f.write_text("x")
        files.append(str(f))
    bruker = tmp_path / "run.d"
    bruker.mkdir()
    other_dir = tmp_path / "folder"
    other_dir.mkdir()
    params = {
        "mzML-files": files[:2] + [str(bruker)],
        "fasta-file": files[2],
        "again": files[0],
        "folder": str(other_dir),
        "missing": str(tmp_path / "gone.mzML"),
        "_defaults": {"x": files[0]},
        "Tool:1:unit": "ppm",
        "Tool:1:threshold": 5.0,
        "max_threads": 4,
    }
    assert count_input_files(params) == 4
    assert count_input_files({}) == 0
    assert count_input_files(None) == 0


def test_time_limit_grows_per_input_up_to_the_ceiling():
    assert job_timeout(0) == 7200
    assert job_timeout(2) == 7200 + 2 * 1800
    assert job_timeout(200) == 7200 + 200 * 1800  # 102 h
    assert job_timeout(400) == 7 * 24 * 3600
    qs = {"default_timeout": 600, "timeout_per_input": 60, "max_timeout": 3600}
    assert job_timeout(5, qs) == 900
    assert job_timeout(100, qs) == 3600
    # a base above the ceiling is kept: the ceiling never shortens it
    assert job_timeout(3, {"default_timeout": 10000, "max_timeout": 3600, "timeout_per_input": 0}) == 10000


def test_shipped_settings_hold_the_keys():
    qs = json.loads(Path("settings.json").read_text(encoding="utf-8"))["queue_settings"]
    assert {"default_timeout", "timeout_per_input", "max_timeout"} <= set(qs)


def test_durations_read_as_people_say_them():
    assert format_duration(2700) == "45 min"
    assert format_duration(7200) == "2 h"
    assert format_duration(16200) == "4 h 30 min"
    assert format_duration(7 * 24 * 3600) == "7 days"
    assert format_duration(90000) == "1 d 1 h"
    assert format_duration(30) == "30 s"
