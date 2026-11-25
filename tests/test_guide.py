"""The four steps of a workflow and the Describe experiment helpers."""
from types import SimpleNamespace

import pytest

from src.workflow import guide
from src.workflow.describe_ui import numbered


@pytest.fixture
def session(monkeypatch):
    """guide reads st.session_state; give it a plain dict."""
    state = {}
    monkeypatch.setattr(guide, "st", SimpleNamespace(session_state=state))
    return state


def test_step_titles_local(session):
    session["location"] = "local"
    assert [guide.step_title(s) for s in guide.ORDER] == [
        "Describe experiment", "Run analysis", "Explore results", "Export results"]
    assert guide.step_icon(guide.EXPORT) == "📤"


def test_export_is_download_online(session):
    session["location"] = "online"
    assert guide.step_title(guide.EXPORT) == "Download results"
    assert guide.step_icon(guide.EXPORT) == "⬇️"


def test_online_from_settings_without_location(session):
    session["settings"] = {"online_deployment": True}
    assert guide.step_title(guide.EXPORT) == "Download results"


def test_workflow_pages_reads_class_attributes():
    class Wf:
        configure_page = "content/a.py"
        run_page = "content/b.py"
        results_page = None
        export_page = "content/d.py"

    assert guide.workflow_pages(Wf) == {"describe": "content/a.py", "run": "content/b.py",
                                        "export": "content/d.py"}


def test_example_workflow_names_its_four_pages():
    from src.Workflow import Workflow
    assert list(guide.workflow_pages(Workflow)) == list(guide.ORDER)


def test_component_groups_in_order():
    assert guide.COMPONENT_GROUPS == ("MS data", "Features and masses", "Identification", "Quantification")


def test_example_components_use_the_groups():
    from src.Workflow import Workflow
    assert {c["group"] for c in Workflow.COMPONENTS} <= set(guide.COMPONENT_GROUPS)


def test_numbered_step_labels():
    assert numbered(["Samples", "Search"]) == ["**1 · Samples**", "**2 · Search**"]
