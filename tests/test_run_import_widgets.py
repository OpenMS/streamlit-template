"""
The message after a run import (run_widgets.show_import_notice) and how the
"All parameters" dialog reads list values (StreamlitUI._as_str_list).
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from streamlit.testing.v1 import AppTest  # noqa: E402


def _notice_app(workflow_dir, notice):
    def app(workflow_dir, notice):
        import streamlit as st

        from src.workflow.RunManager import RunManager
        from src.workflow.run_widgets import show_import_notice

        runs = RunManager(workflow_dir)
        if "seeded" not in st.session_state:
            st.session_state.seeded = True
            st.session_state[f"_runs-{runs.workflow_dir.name}-imported"] = notice
        show_import_notice(runs)
        show_import_notice(runs)

    return AppTest.from_function(app, args=(str(workflow_dir), notice))


def test_notice_depends_on_whether_the_run_is_shown(tmp_path):
    at = _notice_app(tmp_path / "my-workflow", {"name": "Run 1", "shown": True}).run()
    assert [s.value for s in at.success] == [
        "Imported **Run 1**. It is shown on the results pages."
    ]
    assert not at.warning

    at = _notice_app(tmp_path / "my-workflow", {"name": "Run 2", "shown": False}).run()
    assert not at.success
    assert len(at.warning) == 1 and "did not finish" in at.warning[0].value

    # Shown once, and gone on the next rerun
    at.run()
    assert not at.success and not at.warning


def test_list_values_as_str_lists():
    from src.workflow.StreamlitUI import _as_str_list

    assert _as_str_list([b"a", "b", 3]) == ["a", "b", "3"]
    # Empty entries stay: run_topp() passes them to the tool
    assert _as_str_list("a\nb\n") == ["a", "b", ""]
    assert _as_str_list(0) == ["0"]
    assert _as_str_list(b"a\nb") == ["a", "b"]
    assert _as_str_list("") == [] and _as_str_list(None) == []
