"""The helper that skips the example app's tests in an app that replaced it."""
import json

import pytest

import _example_app


def test_template_has_the_example():
    settings = json.loads((_example_app.ROOT / "settings.json").read_text())
    if settings.get("repository-name") != "streamlit-template":
        pytest.skip("only the template ships the example app")
    assert _example_app.has_example("content/topp_workflow_parameter.py")


def test_an_app_workflow_is_not_the_example(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Workflow.py").write_text("class TopDownWorkflow(WorkflowManager):\n    pass\n")
    monkeypatch.setattr(_example_app, "ROOT", tmp_path)
    monkeypatch.setattr(_example_app, "WORKFLOW", tmp_path / "src" / "Workflow.py")
    assert not _example_app.has_example()


def test_missing_workflow_or_page(tmp_path, monkeypatch):
    monkeypatch.setattr(_example_app, "ROOT", tmp_path)
    monkeypatch.setattr(_example_app, "WORKFLOW", tmp_path / "src" / "Workflow.py")
    assert not _example_app.has_example()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Workflow.py").write_text("class Workflow(WorkflowManager):\n    pass\n")
    assert _example_app.has_example()
    assert not _example_app.has_example("content/topp_workflow_parameter.py")
