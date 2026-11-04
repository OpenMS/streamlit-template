"""input_TOPP() labels the parameters named in parameter-names.json with those
names, on the page and in the "All parameters" dialog, whose filter finds a
parameter by either name. Parameters without an entry keep the tool's name."""
import json
import os

import pytest
from streamlit.testing.v1 import AppTest

pytest.importorskip("pyopenms")

NAMES = {
    "DemoTool": {
        "algo:tol": {"name": "Mass tolerance (ppm)", "help": "How far apart, in ppm."},
        "algo:min_charge": "Lowest charge",
        "algo": {"name": "Algorithm settings", "help": "How peaks are matched."},
    }
}


def _script():
    import os
    from pathlib import Path

    import pyopenms as poms
    import streamlit as st

    from src.workflow.ParameterManager import ParameterManager
    from src.workflow.StreamlitUI import StreamlitUI

    root = Path(os.environ["PARAMETER_NAMES_TEST_DIR"])
    os.chdir(root)
    workflow_dir = root / "demo"
    pm = ParameterManager(workflow_dir)
    ini = pm.ini_dir / "DemoTool.ini"
    if not ini.exists():
        param = poms.Param()
        param.setValue("DemoTool:1:algo:tol", 10.0, "Tolerance for matching peaks.")
        param.setValue("DemoTool:1:algo:min_charge", 1, "Minimum charge state.")
        param.setValue("DemoTool:1:algo:max_charge", 30, "Maximum charge state.")
        param.setValue("DemoTool:1:algo:hidden", 2, "An advanced one.", ["advanced"])
        poms.ParamXMLFile().store(str(ini), param)
    ui = StreamlitUI(workflow_dir, None, None, pm)
    advanced = [a for a in os.environ.get("PARAMETER_NAMES_TEST_ADVANCED", "").split(",") if a]
    ui.input_TOPP("DemoTool", reactive=True, advanced_parameters=advanced)
    if os.environ.get("PARAMETER_NAMES_TEST_DIALOG"):
        # The dialog's body, drawn on the page so that it stays across reruns
        ui._all_parameters_dialog("DemoTool", "DemoTool", [])


@pytest.fixture
def app(tmp_path, monkeypatch):
    (tmp_path / "parameter-names.json").write_text(json.dumps(NAMES), encoding="utf-8")
    monkeypatch.setenv("PARAMETER_NAMES_TEST_DIR", str(tmp_path))
    cwd = os.getcwd()
    at = AppTest.from_function(_script, default_timeout=30)
    at.run()
    yield at
    os.chdir(cwd)


def key(name):
    return f"demo-TOPP-DemoTool:1:algo:{name}"


def test_page_uses_display_names(app):
    assert not app.exception
    tol = app.number_input(key=key("tol"))
    assert tol.label == "Mass tolerance (ppm)"
    # The help is the app's, and keeps the tool's own name
    assert "How far apart, in ppm." in tol.help
    assert "`algo:tol`" in tol.help and "DemoTool" in tol.help
    min_charge = app.number_input(key=key("min_charge"))
    assert min_charge.label == "Lowest charge"
    assert "Minimum charge state." in min_charge.help
    # No entry: the tool's name and description
    max_charge = app.number_input(key=key("max_charge"))
    assert max_charge.label == "max_charge"
    assert max_charge.help == "Maximum charge state."


def test_values_are_stored_under_the_tool_name(app):
    app.number_input(key=key("tol")).set_value(5.0).run()
    stored = json.loads(
        open(os.path.join(os.environ["PARAMETER_NAMES_TEST_DIR"], "demo", "params.json")).read()
    )
    assert stored["DemoTool"]["algo:tol"] == 5.0


def test_dialog_shows_and_finds_both_names(tmp_path, monkeypatch):
    (tmp_path / "parameter-names.json").write_text(json.dumps(NAMES), encoding="utf-8")
    monkeypatch.setenv("PARAMETER_NAMES_TEST_DIR", str(tmp_path))
    monkeypatch.setenv("PARAMETER_NAMES_TEST_DIALOG", "1")
    cwd = os.getcwd()
    try:
        at = AppTest.from_function(_script, default_timeout=30)
        at.run()
        assert not at.exception

        def shown():
            return " ".join(m.value for m in at.markdown)

        assert "**Mass tolerance (ppm)**" in shown() and "algo:tol" in shown()
        assert "**max_charge**" in shown()

        def search(text):
            at.text_input(key="_all_params_filter").set_value(text).run()
            assert not at.exception
            return shown()

        found = search("lowest")
        assert "**Lowest charge**" in found and "**max_charge**" not in found
        # The tool's own name and description still find it
        assert "**Lowest charge**" in search("min_charge")
        found = search("tolerance for matching")
        assert "**Mass tolerance (ppm)**" in found and "**Lowest charge**" not in found
        assert "**Mass tolerance (ppm)**" in search("how far apart")
    finally:
        os.chdir(cwd)


def test_section_heading_uses_display_name(app):
    headings = [m for m in app.markdown if m.value == "**Algorithm settings**"]
    assert len(headings) == 1
    assert "How peaks are matched." in headings[0].help
    assert "`algo`" in headings[0].help


def test_advanced_parameters_move_to_the_dialog(tmp_path, monkeypatch):
    (tmp_path / "parameter-names.json").write_text(json.dumps(NAMES), encoding="utf-8")
    monkeypatch.setenv("PARAMETER_NAMES_TEST_DIR", str(tmp_path))
    monkeypatch.setenv("PARAMETER_NAMES_TEST_ADVANCED", "max_charge")
    monkeypatch.setenv("PARAMETER_NAMES_TEST_DIALOG", "1")
    cwd = os.getcwd()
    try:
        at = AppTest.from_function(_script, default_timeout=30)
        at.run()
        assert not at.exception
        page_keys = {w.key for w in at.number_input}
        assert key("tol") in page_keys and key("max_charge") not in page_keys
        # Still one of the tool's parameters: counted by the dialog button,
        # shown in the dialog and found by its filter
        assert any(b.label.startswith("All 4 parameters") for b in at.button)
        assert "**max_charge**" in " ".join(m.value for m in at.markdown)
        at.text_input(key="_all_params_filter").set_value("max_charge").run()
        assert not at.exception
        assert "**max_charge**" in " ".join(m.value for m in at.markdown)
    finally:
        os.chdir(cwd)
