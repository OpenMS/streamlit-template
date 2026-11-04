"""
editor_table(): the table a data editor is drawn from stays the same while the
editor is on the page, so a saved edit does not replace the editor and drop
the next edit (every second condition typed in the experimental design table
and confirmed with Tab or Enter vanished).
"""
import os
import sys

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

import pytest  # noqa: E402


@pytest.fixture(autouse=True, scope="module")
def _real_streamlit_ui():
    """Import the real StreamlitUI for these tests only. Later test modules
    mock streamlit before importing src.workflow, so drop it again."""
    yield
    for name in [m for m in sys.modules if m.startswith("src.workflow")]:
        del sys.modules[name]


def editor_table(*args, **kwargs):
    from src.workflow.StreamlitUI import editor_table as real

    return real(*args, **kwargs)

KEY = "_design-wf-mzML-files-0"


def _design(*conditions):
    return pd.DataFrame({
        "file": [f"{i}.mzML" for i in range(len(conditions))],
        "condition": list(conditions),
    })


def _drawn(state, table):
    """What the browser sends back for an editor that was drawn: its edits."""
    state[KEY] = {"edited_rows": {}}
    return table


def test_saved_edit_keeps_the_first_table():
    state = {}
    first = _drawn(state, editor_table(state, KEY, _design("", "")))
    # The next run reads the design as saved after the edit
    again = editor_table(state, KEY, _design("ctrl", ""))
    assert again is first


def test_table_read_again_when_editor_was_not_drawn():
    state = {}
    _drawn(state, editor_table(state, KEY, _design("", "")))
    del state[KEY]  # another page in between: Streamlit forgets the editor
    shown = editor_table(state, KEY, lambda: _design("ctrl", "treat"))
    assert list(shown["condition"]) == ["ctrl", "treat"]


def test_table_read_again_when_rows_change_or_key_is_new():
    state = {}
    _drawn(state, editor_table(state, KEY, _design("", "")))
    three = _design("ctrl", "", "")
    shown = editor_table(state, KEY, three, fits=lambda t: len(t) == len(three))
    assert shown is three

    new_key = "_design-wf-mzML-files-1"
    imported = _design("a", "b")
    assert editor_table(state, new_key, imported) is imported


def test_callable_is_only_called_when_needed():
    calls = []

    def load():
        calls.append(1)
        return _design("")

    state = {}
    _drawn(state, editor_table(state, KEY, load))
    editor_table(state, KEY, load)
    assert len(calls) == 1
