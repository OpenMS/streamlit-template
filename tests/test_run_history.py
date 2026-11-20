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


def _left_out_run(runs, params_file, name="First", files=("a.mzML", "b.raw", "c.mzML")):
    """A finished run whose tool failed on b (converted to b.mzML) and went on."""
    from src.workflow.progress import RunProgress

    params_file.write_text(json.dumps({"mzML-files": [str(Path("/data", f)) for f in files]}))
    run_id = runs.new_run(name, params_file)
    progress = RunProgress(runs.run_dir(run_id))
    step = progress.start_step("FeatureFinderMetabo", ["a.mzML", "b.mzML", "c.mzML"], allow_failed=True)
    progress.file_finished(step, 0, True)
    progress.file_finished(step, 1, False, returncode=1, output=["Error: no spectra"])
    progress.file_finished(step, 2, True)
    progress.end_step(step)
    # A failure of a step that did not go on is not a left-out file
    other = progress.start_step("Other", ["c.mzML"])
    progress.file_finished(other, 0, False, returncode=1)
    runs.finish(run_id, FINISHED)
    return run_id


def test_left_out_files_are_not_part_of_the_experiment(tmp_path):
    runs = RunManager(tmp_path)
    params = Path(tmp_path, "params.json")
    run_id = _left_out_run(runs, params)

    assert runs.left_out_files(run_id, "mzML-files") == ["/data/b.raw"]
    assert runs.experiment_files(run_id, "mzML-files") == ["/data/a.mzML", "/data/c.mzML"]
    assert runs.left_out_files("missing", "mzML-files") == []

    # Adding them again preselects exactly those files
    assert runs.restore_settings(run_id, add_files="mzML-files", files=["/data/b.raw"])
    restored = json.loads(params.read_text())
    assert restored["mzML-files"] == ["/data/b.raw"]
    assert restored["_follow_up"]["adds_to"] == run_id
    assert restored["_follow_up"]["files"] == ["/data/a.mzML", "/data/c.mzML"]


def _left_out_script(workflow_dir: str, run_id: str):
    from pathlib import Path

    import streamlit as st

    from src.workflow.RunManager import RunManager
    from src.workflow.run_widgets import run_history_section

    def process(picked):
        st.session_state["left-out"] = picked

    run_history_section(RunManager(Path(workflow_dir)), run_id, key="h",
                        files_key="mzML-files", on_process_left_out=process)


def test_history_names_left_out_files_and_processes_them(tmp_path):
    runs = RunManager(tmp_path)
    run_id = _left_out_run(runs, Path(tmp_path, "params.json"))
    at = AppTest.from_function(_left_out_script, args=(str(tmp_path), run_id)).run(timeout=30)
    assert not at.exception
    assert "b.raw" in at.warning[0].value
    at.button(key="h-left-out").click().run(timeout=30)
    assert at.session_state["left-out"] == run_id


def test_history_without_left_out_files_offers_nothing(tmp_path):
    runs = RunManager(tmp_path)
    run_id = _run(runs, Path(tmp_path, "params.json"), "First", {"mzML-files": ["a.mzML"]})
    at = AppTest.from_function(_left_out_script, args=(str(tmp_path), run_id)).run(timeout=30)
    assert not at.exception
    assert not at.warning
    assert not [b for b in at.button if b.key == "h-left-out"]


def test_process_left_out_adds_them_to_the_experiment(tmp_path, monkeypatch):
    from src.workflow import WorkflowManager as wm_module
    from src.workflow.WorkflowManager import WorkflowManager

    params = Path(tmp_path, "params.json")
    runs = RunManager(tmp_path)
    run_id = _left_out_run(runs, params)

    wf = object.__new__(WorkflowManager)
    wf.multi_run = True
    wf.runs = runs
    wf.workflow_dir = Path(tmp_path)
    wf.configure_page = "configure.py"
    wf.input_files_key = "mzML-files"
    reloaded = []
    wf._reload_settings = reloaded.append
    assert wf.process_left_out(run_id)
    restored = json.loads(params.read_text())
    assert restored["mzML-files"] == ["/data/b.raw"]
    assert restored["_follow_up"]["note"] == "to process the files it left out"
    assert reloaded == ["configure.py"]

    plain = _run(runs, params, "Plain", {"mzML-files": ["a.mzML"]})
    toasts = []
    monkeypatch.setattr(wm_module.st, "toast", lambda *a, **k: toasts.append(a))
    assert not wf.process_left_out(plain) and toasts
