"""The configure page's Run button starts the workflow on the Run page.

``show_run_button`` sets a one-shot session flag and switches pages;
``show_execution_section`` pops it and hands it to the UI as ``autostart``,
so a reload of the Run page never starts a second run.
"""

import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("pyopenms")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow import WorkflowManager as wm_module
from src.workflow.WorkflowManager import WorkflowManager


def _workflow(tmp_path, running=False):
    wf = object.__new__(WorkflowManager)
    wf.workflow_dir = Path(tmp_path, "my-workflow")
    wf.multi_run = False
    wf.ui = mock.MagicMock()
    wf.parameter_manager = mock.MagicMock()
    wf.get_workflow_status = lambda: {"running": running}
    wf.start_workflow = mock.MagicMock()
    wf.stop_workflow = mock.MagicMock()
    wf._run_online = lambda name_key: False
    return wf


def test_run_button_saves_sets_flag_and_switches(tmp_path):
    wf = _workflow(tmp_path)
    st = mock.MagicMock()
    st.session_state = {}
    st.button.return_value = True
    with mock.patch.object(wm_module, "st", st):
        wf.show_run_button("content/run.py")
    wf.parameter_manager.save_parameters.assert_called_once()
    assert st.session_state == {"my-workflow-autostart": True}
    st.switch_page.assert_called_once_with("content/run.py")


def test_run_button_while_running_only_opens_run_page(tmp_path):
    wf = _workflow(tmp_path, running=True)
    st = mock.MagicMock()
    st.session_state = {}
    st.button.return_value = True
    with mock.patch.object(wm_module, "st", st):
        wf.show_run_button("content/run.py")
    assert st.button.call_args.args[0] == "Follow the running analysis"
    wf.parameter_manager.save_parameters.assert_not_called()
    assert st.session_state == {}
    st.switch_page.assert_called_once_with("content/run.py")


def test_execution_section_autostarts_once(tmp_path):
    wf = _workflow(tmp_path)
    st = mock.MagicMock()
    st.session_state = {"my-workflow-autostart": True}
    with mock.patch.object(wm_module, "st", st):
        wf.show_execution_section(results_page="content/results.py", results_label="Explore results")
        first = wf.ui.execution_section.call_args.kwargs
        wf.show_execution_section(results_page="content/results.py")
        second = wf.ui.execution_section.call_args.kwargs
    assert first["autostart"] is True
    assert first["results_page"] == "content/results.py"
    assert first["results_label"] == "Explore results"
    assert second["autostart"] is False
    assert "my-workflow-autostart" not in st.session_state


def test_results_button_asks_for_the_newest_result(tmp_path):
    from src.workflow import StreamlitUI as ui_module
    from src.workflow.StreamlitUI import StreamlitUI, latest_results_key

    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = Path(tmp_path, "my-workflow")
    st = mock.MagicMock()
    st.session_state = {}
    st.button.return_value = True
    with mock.patch.object(ui_module, "st", st):
        ui._results_link("content/results.py", "Explore results")
    assert st.session_state == {latest_results_key(ui.workflow_dir): True}
    assert latest_results_key(ui.workflow_dir) == "my-workflow-show-latest-results"
    st.switch_page.assert_called_once_with("content/results.py")


def test_results_button_runs_its_callback_before_switching(tmp_path):
    from src.workflow import StreamlitUI as ui_module
    from src.workflow.StreamlitUI import StreamlitUI

    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = Path(tmp_path, "my-workflow")
    st = mock.MagicMock()
    st.session_state = {}
    st.button.return_value = True
    order = []
    st.switch_page.side_effect = lambda page: order.append("switch")
    with mock.patch.object(ui_module, "st", st):
        ui._results_link("content/results.py", "Explore results", lambda: order.append("select"))
    assert order == ["select", "switch"]


def test_multi_run_results_button_selects_the_newest_run(tmp_path):
    from src.workflow import run_widgets
    from src.workflow.RunManager import RunManager

    wf = _workflow(tmp_path)
    wf.multi_run = True
    wf.runs = RunManager(Path(tmp_path, "my-workflow"))
    old = wf.runs.new_run("Old")
    wf.runs.finish(old, "finished")
    time.sleep(1.1)
    new = wf.runs.new_run("New")
    wf.runs.finish(new, "finished")
    st = mock.MagicMock()
    st.session_state = {run_widgets.selected_run_key(wf.runs): old}
    with mock.patch.object(run_widgets, "st", st):
        wf._select_newest_run()
    assert st.session_state[run_widgets.selected_run_key(wf.runs)] == new


def test_run_button_sits_in_a_sticky_bar_with_its_summary(tmp_path):
    wf = _workflow(tmp_path)
    st = mock.MagicMock()
    st.session_state = {}
    st.button.return_value = False
    st.context.theme.type = "dark"
    st.get_option.return_value = "#123456"
    with mock.patch.object(wm_module, "st", st):
        wf.show_run_button("content/run.py", summary="2 runs, label-free")
    st.container.assert_called_once()
    assert st.container.call_args.kwargs["key"] == "my-workflow-run-button-bar"
    st.caption.assert_called_once_with("2 runs, label-free", width="stretch")
    css = st.html.call_args.args[0]
    assert "div:has(> .st-key-my-workflow-run-button-bar)" in css
    assert "position: sticky" in css and "#123456" in css


def test_run_button_without_sticky_bar(tmp_path):
    wf = _workflow(tmp_path)
    st = mock.MagicMock()
    st.session_state = {}
    st.button.return_value = False
    with mock.patch.object(wm_module, "st", st):
        wf.show_run_button("content/run.py", sticky=False, summary="ignored")
    st.html.assert_not_called()
    st.caption.assert_not_called()


def test_named_run_button_keeps_the_name_for_the_start(tmp_path):
    wf = _workflow(tmp_path)
    wf.name_runs = True
    wf.parameter_manager.read_parameters_strict.return_value = {"a": 1}
    st = mock.MagicMock()
    st.session_state = {"my-workflow-run-button-name": "  Liver, day 3 "}
    st.button.return_value = True
    with mock.patch.object(wm_module, "st", st):
        wf.show_run_button("content/run.py", name_label="Experiment name")
    assert st.text_input.call_args.args[0] == "Experiment name"
    assert st.text_input.call_args.kwargs["key"] == "my-workflow-run-button-name"
    wf.parameter_manager.write_parameters.assert_called_once_with({"a": 1, "_run_name": "Liver, day 3"})
    st.switch_page.assert_called_once_with("content/run.py")


def test_run_button_draws_no_name_field_unless_asked(tmp_path):
    wf = _workflow(tmp_path)
    st = mock.MagicMock()
    st.session_state = {}
    st.button.return_value = True
    with mock.patch.object(wm_module, "st", st):
        wf.show_run_button("content/run.py")
    st.text_input.assert_not_called()
    wf.parameter_manager.write_parameters.assert_not_called()


def test_start_without_run_folders_keeps_its_name_apart(tmp_path):
    wf = _workflow(tmp_path)
    wf.workflow_dir.mkdir(parents=True)
    wf.parameter_manager.read_parameters_strict.return_value = {"a": 1, "_run_name": "Liver"}
    wf._settle_follow_up()
    wf.parameter_manager.write_parameters.assert_called_once_with({"a": 1})
    assert wf.run_name() == "Liver"
    # The next start without a name has none
    wf.parameter_manager.read_parameters_strict.return_value = {"a": 1}
    wf.parameter_manager.write_parameters.reset_mock()
    wf._settle_follow_up()
    wf.parameter_manager.write_parameters.assert_not_called()
    assert wf.run_name() == ""


def test_run_folders_take_the_name_given_beside_the_run_button(tmp_path):
    from src.workflow import run_widgets
    from src.workflow.RunManager import RunManager

    wf = _workflow(tmp_path)
    wf.multi_run = True
    wf.runs = RunManager(Path(tmp_path, "my-workflow"))
    wf.parameter_manager.read_parameters_strict.return_value = {"a": 1, "_run_name": "Liver"}
    wf._use_run = lambda run_id: setattr(wf, "run_id", run_id)
    st = mock.MagicMock()
    st.session_state = {}
    with mock.patch.object(wm_module, "st", st), mock.patch.object(run_widgets, "st", st):
        wf._new_run()
    assert wf.runs.get(wf.run_id)["name"] == "Liver"
    assert wf.run_name() == "Liver"
    wf.parameter_manager.write_parameters.assert_called_once_with({"a": 1})


def test_unreadable_params_start_nothing_and_stay_as_they_are(tmp_path):
    # The class the module under test catches (other tests reload src.workflow)
    InvalidParameterFileError = wm_module.InvalidParameterFileError

    wf = _workflow(tmp_path)
    wf.name_runs = True
    wf.parameter_manager.read_parameters_strict.side_effect = InvalidParameterFileError("unreadable")
    st = mock.MagicMock()
    st.session_state = {"my-workflow-run-button-name": "Liver"}
    st.button.return_value = True
    with mock.patch.object(wm_module, "st", st):
        wf.show_run_button("content/run.py")
    st.error.assert_called_once()
    wf.parameter_manager.write_parameters.assert_not_called()
    assert "my-workflow-autostart" not in st.session_state
    st.switch_page.assert_not_called()
    # A start does not write a tolerant empty read back either
    wf.workflow_dir.mkdir(parents=True)
    wf._settle_follow_up()
    wf.parameter_manager.write_parameters.assert_not_called()
