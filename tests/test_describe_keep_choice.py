"""A segmented choice keeps its value when the picked option is clicked again."""

import sys
from unittest.mock import MagicMock


def test_keep_choice_restores_last_value(monkeypatch):
    st = MagicMock()
    st.session_state = {}
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
        sys.modules.pop("src.workflow.describe_ui", None)
        for name in [m for m in sys.modules if m.startswith("src.workflow")]:
            sys.modules.pop(name, None)
