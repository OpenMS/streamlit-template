"""A value restored from params.json must survive reruns of input_widget.

On Streamlit < 1.50 a widget's initial-value argument is hashed into its
element id. Passing it on the first render only still changed the id once,
and the following rerun reset the widget: a restored multiselect came back
empty and was saved as empty.
"""
from streamlit.testing.v1 import AppTest


def _script():
    from types import SimpleNamespace

    from src.workflow.StreamlitUI import StreamlitUI

    ui = object.__new__(StreamlitUI)
    ui.params = {"files": ["a", "b"], "mode": "y", "n": 3}
    ui.parameter_manager = SimpleNamespace(param_prefix="p-", save_parameters=lambda: None)
    for key, widget_type, options in (
        ("files", "multiselect", ["a", "b", "c"]),
        ("mode", "selectbox", ["x", "y"]),
        ("n", "number", None),
    ):
        ui._input_widget_impl(
            key, None, key, None, widget_type, options, None, None, 1, True, None
        )


def test_restored_values_survive_reruns():
    at = AppTest.from_function(_script)
    at.run()
    for _ in range(2):
        assert at.multiselect(key="p-files").value == ["a", "b"]
        assert at.selectbox(key="p-mode").value == "y"
        assert at.number_input(key="p-n").value == 3
        at.run()
    assert not at.exception


def test_user_change_is_kept():
    at = AppTest.from_function(_script)
    at.run()
    at.multiselect(key="p-files").unselect("a").run()
    at.run()
    assert at.multiselect(key="p-files").value == ["b"]
