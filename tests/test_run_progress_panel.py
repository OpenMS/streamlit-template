"""The progress panel keeps the same shape whatever it shows.

The Run page redraws it every second and ends each redraw with st.rerun(),
which never clears elements a redraw left out. A part drawn only sometimes
(the running tool's own progress bar) shifted the parts after it, and the
sample list of the previous redraw stayed on the page as a second, outdated
list.
"""
import json
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def _script():
    import os
    from pathlib import Path

    from src.workflow.StreamlitUI import StreamlitUI

    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = Path(os.environ["PANEL_WORKFLOW_DIR"])
    ui._show_run_progress()


def _write(workflow_dir: Path, samples: bool, tool_progress: bool) -> None:
    logs = workflow_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = time.time()
    names = ["a.mzML", "b.mzML", "c.mzML"]
    step = {
        "tool": "FLASHDeconv", "started": now, "ended": None, "threads": 1,
        "parallel": 1, "sample": names[1] if samples else None,
        "files": [{"name": names[1], "status": "running", "started": now, "ended": None}],
    }
    state = {"started": now - 60, "steps": [dict(step, ended=now, tool="Earlier"), step]}
    if samples:
        state["samples"] = [
            {"name": names[0], "status": "done", "started": now - 50, "ended": now - 10},
            {"name": names[1], "status": "running", "started": now, "ended": None},
            {"name": names[2], "status": "pending", "started": None, "ended": None},
        ]
    (logs / "progress.json").write_text(json.dumps(state))
    log = "Running command: FLASHDeconv\n"
    if tool_progress:
        log += "Progress of 'loading spectra':\n-- 42.0 % --\n"
    (logs / "all.log").write_text(log)


def _shape(node):
    """The places on the page: a block is the list of its children's places,
    an element one place, whatever it shows (an empty slot included)."""
    children = getattr(node, "children", None)
    if children is None:
        return 1
    return [_shape(c) for c in children.values()]


@pytest.mark.parametrize("samples", [True, False])
def test_panel_shape_does_not_depend_on_tool_progress(tmp_path, monkeypatch, samples):
    monkeypatch.setenv("PANEL_WORKFLOW_DIR", str(tmp_path))
    shapes, bars = [], []
    for tool_progress in (True, False):
        _write(tmp_path, samples, tool_progress)
        at = AppTest.from_function(_script)
        at.run()
        assert not at.exception
        shapes.append(_shape(at.main))
        bars.append(len(at.get("progress")))
    # the tool's own progress bar is drawn only when it reports some ...
    assert bars == [2, 1]
    # ... and its slot stays when it does not, so nothing after it moves
    assert shapes[0] == shapes[1]


def test_no_progress_still_takes_its_place(tmp_path, monkeypatch):
    monkeypatch.setenv("PANEL_WORKFLOW_DIR", str(tmp_path))
    at = AppTest.from_function(_script)
    at.run()
    assert not at.exception
    assert len(at.main.children) == 1
