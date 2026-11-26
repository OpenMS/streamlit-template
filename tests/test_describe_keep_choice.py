"""A segmented choice keeps its value when the picked option is clicked again."""

import sys
from unittest.mock import MagicMock


def test_keep_choice_restores_last_value(monkeypatch):
    st = MagicMock()
    st.session_state = {}
    # Modules other code already holds (src.Workflow, an earlier AppTest's
    # src.workflow) must stay the ones in sys.modules afterwards; dropping
    # them all made a later test patch a ParameterManager the app no longer used.
    before = {m: sys.modules[m] for m in sys.modules if m.startswith("src.workflow")}
    monkeypatch.setitem(sys.modules, "streamlit", st)
    sys.modules.pop("src.workflow.describe_ui", None)
    import importlib

    describe_ui = importlib.import_module("src.workflow.describe_ui")

    try:
        st.session_state.update({"w": "a", describe_ui._last_key("w"): "a"})
        describe_ui._keep_choice("w")
        assert st.session_state["w"] == "a"
        st.session_state["w"] = None
        describe_ui._keep_choice("w")
        assert st.session_state["w"] == "a"
        st.session_state["w"] = "b"
        describe_ui._keep_choice("w")
        assert st.session_state["w"] == "b"
    finally:
        for name in [m for m in sys.modules if m.startswith("src.workflow")]:
            if name not in before:
                del sys.modules[name]
        sys.modules.update(before)
