"""A long run (a study of 200 files) lists on the Run page what needs a look.

The failed and running files or samples come first, then the next waiting and
the latest finished ones; the rest are counted in one line.
"""
import json
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.workflow.progress import (
    DONE, FAILED, LIST_LIMIT, PENDING, RUNNING, left_out_line, list_entries,
)


def _entries(statuses):
    now = 1000.0
    out = []
    for i, status in enumerate(statuses):
        started = now + i if status != PENDING else None
        ended = started + 10 if status in (DONE, FAILED) else None
        out.append({"name": f"f{i}.mzML", "status": status, "started": started, "ended": ended})
    return out


def test_short_list_is_shown_whole_and_in_order():
    entries = _entries([DONE, FAILED, RUNNING, PENDING])
    assert list_entries(entries) == ([0, 1, 2, 3], {})


def test_long_list_puts_failed_and_running_first():
    statuses = [DONE] * 140 + [FAILED] * 2 + [RUNNING] * 3 + [PENDING] * 55
    entries = _entries(statuses)
    shown, left_out = list_entries(entries)
    assert len(shown) == LIST_LIMIT
    assert [entries[i]["status"] for i in shown[:5]] == [FAILED] * 2 + [RUNNING] * 3
    # the next three waiting files, then the latest finished
    assert shown[5:8] == [145, 146, 147]
    assert shown[8] == 139
    assert left_out == {DONE: 136, PENDING: 52}
    assert left_out_line(left_out) == "… and 188 more: 136 done, 52 waiting"


def _script():
    import os
    from pathlib import Path

    from src.workflow.StreamlitUI import StreamlitUI

    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = Path(os.environ["PANEL_WORKFLOW_DIR"])
    ui._show_run_progress()


def test_panel_of_a_study_stays_short(tmp_path, monkeypatch):
    now = time.time()
    files = []
    for i in range(200):
        status = DONE if i < 150 else FAILED if i < 152 else RUNNING if i < 154 else PENDING
        started = now - 600 + i if status != PENDING else None
        files.append({
            "name": f"sample_{i:03d}.mzML", "status": status, "started": started,
            "ended": started + 60 if status in (DONE, FAILED) else None,
        })
    step = {"tool": "CometAdapter", "started": now - 600, "ended": None, "threads": 2,
            "parallel": 4, "sample": None, "files": files}
    logs = Path(tmp_path, "logs")
    logs.mkdir()
    (logs / "progress.json").write_text(json.dumps({"started": now - 700, "steps": [step]}))
    monkeypatch.setenv("PANEL_WORKFLOW_DIR", str(tmp_path))
    at = AppTest.from_function(_script, default_timeout=60)
    at.run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert text.count(".mzML") == LIST_LIMIT
    assert "sample_150.mzML" in text and "sample_153.mzML" in text
    assert "… and 188 more: 145 done, 43 waiting" in text


def test_failures_are_grouped_by_tool():
    from src.workflow.progress import failures_by_tool

    files = _entries([DONE, FAILED, DONE, FAILED])
    files[1]["output"] = ["Error: cannot read f1.mzML"]
    state = {"steps": [
        {"tool": "DecoyDatabase", "files": _entries([DONE])},
        {"tool": "CometAdapter", "files": files},
    ]}
    (group,) = failures_by_tool(state)
    assert group["tool"] == "CometAdapter"
    assert group["total"] == 4
    assert [f["file"] for f in group["failures"]] == ["f1.mzML", "f3.mzML"]
    assert group["failures"][0]["message"] == "Error: cannot read f1.mzML"


def _summary_script():
    import os
    from pathlib import Path

    from src.workflow.StreamlitUI import StreamlitUI

    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = Path(os.environ["PANEL_WORKFLOW_DIR"])
    ui._show_run_summary(show_failures=True)


def test_failed_files_after_a_run_are_one_table(tmp_path, monkeypatch):
    files = _entries([DONE] * 193 + [FAILED] * 7)
    for f in files:
        if f["status"] == FAILED:
            f.update(output=[f"Error: cannot read {f['name']}"], returncode=1)
    step = {"tool": "CometAdapter", "started": 1000.0, "ended": 2000.0, "threads": 2,
            "parallel": 4, "sample": None, "files": files}
    logs = Path(tmp_path, "logs")
    logs.mkdir()
    (logs / "progress.json").write_text(json.dumps({"started": 900.0, "steps": [step]}))
    monkeypatch.setenv("PANEL_WORKFLOW_DIR", str(tmp_path))
    at = AppTest.from_function(_summary_script, default_timeout=60)
    at.run()
    assert not at.exception
    assert [e.value for e in at.error] == ["**CometAdapter failed on 7 of 200 files.**"]
    (table,) = at.dataframe
    assert len(table.value) == 7
    assert list(table.value.columns) == ["File", "Error"]
    assert len(at.selectbox) == 1


def test_finished_run_shows_no_sample_list(tmp_path, monkeypatch):
    samples = _entries([DONE] * 30 + [FAILED] * 2)
    steps = []
    for s in samples:
        entry = dict(s)
        if s["status"] == FAILED:
            entry.update(output=[f"Error: cannot read {s['name']}"], returncode=1)
        steps.append({"tool": "FLASHDeconv", "started": s["started"], "ended": s["ended"],
                      "threads": 1, "parallel": 1, "sample": s["name"], "files": [entry]})
    logs = Path(tmp_path, "logs")
    logs.mkdir()
    (logs / "progress.json").write_text(json.dumps({"started": 900.0, "samples": samples, "steps": steps}))
    monkeypatch.setenv("PANEL_WORKFLOW_DIR", str(tmp_path))
    at = AppTest.from_function(_summary_script, default_timeout=60)
    at.run()
    assert not at.exception
    assert [e.value for e in at.error] == ["**FLASHDeconv failed on 2 of 32 files.**"]
    assert not at.expander or all("samples" not in e.label for e in at.expander)
    assert not any("f0.mzML" in m.value for m in at.markdown)
    assert any("FLASHDeconv: 32 runs" in c.value for c in at.caption)
