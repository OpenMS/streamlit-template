"""The Run page tells a user in another tab that a run has ended."""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow import run_notice


def test_ask_button_asks_only_on_a_click_and_hides_when_answered():
    html = run_notice.ask_html()
    assert f'id="{run_notice.ASK_ID}"' in html
    assert "display:none" in html  # shown by the script, only when it can ask
    assert "Notification.permission!=='default')return" in html
    assert "b.onclick=function(){Notification.requestPermission()" in html
    # Still undecided (the prompt was dismissed): the button stays.
    assert "if(p!=='default')b.style.display='none'" in html


@pytest.mark.parametrize("outcome, mark, words", [
    ("finished", "✓", "finished"),
    ("cancelled", "■", "was cancelled"),
    ("error", "✗", "failed"),
    ("something else", "✗", "failed"),
])
def test_notice_names_the_workflow_and_its_outcome(outcome, mark, words):
    html = run_notice.notice_html(outcome, "Quantification")
    assert f'"Quantification {words}."' in html
    assert f'"{mark} "' in html
    # A tab in view changes nothing; a notification needs the user's yes.
    assert "if(!d.hidden)return;" in html
    assert "Notification.permission==='granted'" in html


def test_notice_cannot_end_its_script_early():
    html = run_notice.notice_html("finished", "a</script><b>")
    assert html.count("</script>") == 1


def _section(tmp_path, running, log=None, status=None):
    """Draw execution_section once with Streamlit mocked; return the mock."""
    pytest.importorskip("streamlit")
    pytest.importorskip("pyopenms")
    from src.workflow import StreamlitUI as ui_module
    from src.workflow.StreamlitUI import StreamlitUI

    workflow_dir = Path(tmp_path, "wf")
    (workflow_dir / "logs").mkdir(parents=True, exist_ok=True)
    if log is not None:
        (workflow_dir / "logs" / "minimal.log").write_text(log)
    ui = object.__new__(StreamlitUI)
    ui.workflow_dir = workflow_dir
    ui.executor = mock.MagicMock()
    ui.executor.pid_dir = Path(workflow_dir, "pids")
    ui.export_parameters_markdown = lambda: ""
    ui._show_run_progress = lambda: None
    ui._show_run_summary = lambda **kw: None
    st = _section.st
    st.html.reset_mock()
    cols = [mock.MagicMock(), mock.MagicMock()]
    for c in cols:
        c.button.return_value = False
        c.selectbox.side_effect = lambda label, options, **kw: options[0]
    st.columns.return_value = cols
    with mock.patch.object(ui_module, "st", st), \
            mock.patch.object(ui_module, "time"), \
            mock.patch.object(ui_module, "report_buttons"):
        ui.execution_section(lambda: None,
                             lambda: {"running": running, **(status or {})},
                             name="Quantification")
    return [c.args[0] for c in st.html.call_args_list]


class _State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


@pytest.fixture
def streamlit_mock():
    st = mock.MagicMock()
    st.session_state = _State()
    _section.st = st
    return st


def test_a_watched_run_sends_one_notice_when_it_ends(tmp_path, streamlit_mock):
    drawn = _section(tmp_path, running=True)
    assert drawn == [run_notice.ask_html()]
    finished = "...\nWORKFLOW FINISHED\n"
    drawn = _section(tmp_path, running=False, log=finished)
    assert drawn == [run_notice.notice_html("finished", "Quantification")]
    # A reload, or the next rerun, does not send it again.
    assert _section(tmp_path, running=False, log=finished) == []


def test_a_run_ended_before_the_page_was_opened_sends_nothing(tmp_path, streamlit_mock):
    assert _section(tmp_path, running=False, log="WORKFLOW FINISHED\n") == []


def test_a_failed_run_says_it_failed(tmp_path, streamlit_mock):
    _section(tmp_path, running=True)
    drawn = _section(tmp_path, running=False, log="Error: tool crashed\n")
    assert drawn == [run_notice.notice_html("error", "Quantification")]


def test_a_failed_queued_job_is_not_reported_by_old_logs(tmp_path, streamlit_mock):
    _section(tmp_path, running=True)
    drawn = _section(tmp_path, running=False, log="WORKFLOW FINISHED\n",
                     status={"status": "failed", "job_id": "j"})
    assert run_notice.notice_html("error", "Quantification") in drawn


def test_the_notice_names_the_run_label_else_the_workflow(tmp_path):
    pytest.importorskip("streamlit")
    pytest.importorskip("pyopenms")
    from src.workflow import WorkflowManager as wm_module
    from src.workflow.WorkflowManager import WorkflowManager

    wf = object.__new__(WorkflowManager)
    wf.name = "TOPP Workflow"
    wf.workflow_dir = Path(tmp_path, "wf")
    wf.multi_run = False
    wf.ui = mock.MagicMock()
    wf.get_workflow_status = lambda: {"running": False}
    wf._run_online = lambda name_key: False
    wf.input_problems = lambda: ""
    st = mock.MagicMock()
    st.session_state = {}
    with mock.patch.object(wm_module, "st", st):
        wf.show_execution_section()
        assert wf.ui.execution_section.call_args.kwargs["name"] == "TOPP Workflow"
        wf.run_label = "My analysis"
        wf.show_execution_section()
        assert wf.ui.execution_section.call_args.kwargs["name"] == "My analysis"
