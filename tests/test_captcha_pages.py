"""Online, the captcha guards the workflow pages only: pages that explain the
app (Quick Start, Documentation) open without it."""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


def _online(page, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACES_DIR", str(tmp_path))
    app = AppTest.from_file(page)
    settings = json.loads(Path("settings.json").read_text())
    settings["online_deployment"] = True
    for tracker in settings["analytics"].values():
        tracker["enabled"] = False
    app.session_state.settings = settings
    return app


@pytest.mark.parametrize("page", ["content/documentation.py"])
def test_explaining_pages_open_without_captcha(page, monkeypatch, tmp_path):
    app = _online(page, monkeypatch, tmp_path)
    app.run(timeout=30)
    assert not app.exception
    assert app.title and app.title[0].value == "Documentation"
    assert "controllo" not in app.session_state  # never asked


def test_quickstart_and_documentation_skip_captcha():
    for page in ("content/quickstart.py", "content/documentation.py"):
        assert "captcha=False" in Path(page).read_text(), page


def test_workflow_page_still_asks(monkeypatch, tmp_path):
    app = _online("content/topp_workflow_parameter.py", monkeypatch, tmp_path)
    app.run(timeout=30)
    assert not app.exception
    # the captcha was asked and is not solved yet
    assert app.session_state["controllo"] is False
