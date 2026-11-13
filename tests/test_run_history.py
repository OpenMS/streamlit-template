"""The History of a run: how it came about, its settings, Start again."""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.workflow.RunManager import FINISHED, RunManager
from src.workflow.run_history import changed_settings, timeline


def _run(runs, params_file, name, values, adds_to=None):
    params_file.write_text(json.dumps(values))
    run_id = runs.new_run(name, params_file, adds_to=adds_to)
    runs.finish(run_id, FINISHED)
    return run_id


def test_timeline_names_what_a_run_follows(tmp_path):
    runs = RunManager(tmp_path)
    params = Path(tmp_path, "params.json")
    first = _run(runs, params, "First", {"mzML-files": ["a.mzML"]})
    again = _run(runs, params, "Again", {
        "mzML-files": ["a.mzML"],
        "_follow_up": {"run": first, "name": "First", "note": "to start again"},
    })
    more = _run(runs, params, "More", {
        "mzML-files": ["b.mzML"], "_follow_up": {"run": first, "name": "First", "adds_to": first},
    }, adds_to=first)

    plain = timeline(runs, first)
    assert plain[0].startswith("Started ") and plain[0].endswith(".")
    assert plain[1].startswith("Finished ")
    assert "Files were added to it by **More**." in plain
    assert "from the settings of **First** (to start again)" in timeline(runs, again)[0]
    assert "adding files to **First**" in timeline(runs, more)[0]
    assert timeline(runs, "missing") == []


def test_changed_settings_lists_each_tool_setting_once():
    report = {
        "settings": {"peak-width": "5"},
        "steps": [
            {"tool": "FeatureFinderMetabo", "params": {"algorithm:noise": "100"}},
            {"tool": "FeatureFinderMetabo", "params": {"algorithm:noise": "100"}},
            {"tool": "FeatureLinkerUnlabeledKD", "params": {}},
        ],
    }
    assert changed_settings(report) == [
        ["Workflow", "peak-width", "5"],
        ["FeatureFinderMetabo", "algorithm:noise", "100"],
    ]
    assert changed_settings({}) == []


def _history_script(workflow_dir: str):
    from pathlib import Path

    import streamlit as st

    from src.workflow.RunManager import RunManager
    from src.workflow.run_widgets import run_manager_section

    def again(run_id):
        st.session_state["again"] = run_id

    run_manager_section(RunManager(Path(workflow_dir)), on_start_again=again)


def test_history_dialog_starts_again(tmp_path):
    runs = RunManager(tmp_path)
    mzml = Path(tmp_path, "a.mzML")
    mzml.write_text("")
    run_id = _run(runs, Path(tmp_path, "params.json"), "First", {"mzML-files": [str(mzml)], "peak-width": 5})
    slug = Path(tmp_path).name

    at = AppTest.from_function(_history_script, args=(str(tmp_path),)).run(timeout=30)
    assert not at.exception
    at.button(key=f"runs-{slug}-history-{run_id}").click().run(timeout=30)
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "How this run came about" in text
    table = at.dataframe[0].value
    assert table.to_dict("records") == [{"Tool": "Workflow", "Parameter": "peak-width", "This run": "5"}]
    assert at.button(key=f"runs-{slug}-history-{run_id}-again")


def _section_script(workflow_dir: str, run_id: str):
    from pathlib import Path

    import streamlit as st

    from src.workflow.RunManager import RunManager
    from src.workflow.run_widgets import run_history_section

    def again(picked):
        st.session_state["again"] = picked

    run_history_section(RunManager(Path(workflow_dir)), run_id, key="h", on_start_again=again)


def test_start_again_button_calls_back_with_the_run(tmp_path):
    runs = RunManager(tmp_path)
    run_id = _run(runs, Path(tmp_path, "params.json"), "First", {"x": 1})
    at = AppTest.from_function(_section_script, args=(str(tmp_path), run_id)).run(timeout=30)
    assert not at.exception
    at.button(key="h-again").click().run(timeout=30)
    assert not at.exception
    assert at.session_state["again"] == run_id


def test_start_again_restores_the_run_settings(tmp_path, monkeypatch):
    from src.workflow import WorkflowManager as wm_module
    from src.workflow.WorkflowManager import WorkflowManager

    params = Path(tmp_path, "params.json")
    runs = RunManager(tmp_path)
    run_id = _run(runs, params, "First", {"mzML-files": ["a.mzML"], "x": 1})
    params.write_text(json.dumps({"mzML-files": ["z.mzML"], "x": 2}))

    wf = object.__new__(WorkflowManager)
    wf.multi_run = True
    wf.runs = runs
    wf.workflow_dir = Path(tmp_path)
    wf.configure_page = "configure.py"
    reloaded = []
    wf._reload_settings = reloaded.append
    assert wf.start_again(run_id)
    restored = json.loads(params.read_text())
    assert restored["mzML-files"] == ["a.mzML"] and restored["x"] == 1
    assert restored["_follow_up"]["note"] == "to start again"
    assert reloaded == ["configure.py"]

    toasts = []
    monkeypatch.setattr(wm_module.st, "toast", lambda *a, **k: toasts.append(a))
    assert not wf.start_again("missing") and toasts
