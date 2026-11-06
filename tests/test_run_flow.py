"""The configure page's Run button starts the workflow on the Run page.

``show_run_button`` sets a one-shot session flag and switches pages;
``show_execution_section`` pops it and hands it to the UI as ``autostart``,
so a reload of the Run page never starts a second run.
"""

import os
import sys
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
