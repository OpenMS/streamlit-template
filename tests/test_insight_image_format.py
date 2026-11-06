"""OpenMS-Insight image downloads follow the sidebar's "image export format".

page_setup() hands the selectbox value to openms_insight.set_image_format().
The template does not depend on openms-insight, so the package is replaced
here by a fake module in ``sys.modules`` (restored by monkeypatch after each
test), and the call must be a no-op when the package is missing or is a
release without set_image_format. It runs unchanged in every app: the page
is page_setup() alone, and the expected format is the app's default.
"""

import json
import sys
import types
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


# The page is page_setup() alone: an app's own pages may import openms_insight,
# directly or through their modules, and the fake below cannot serve them.
PAGE = "from src.common.common import page_setup\npage_setup()\n"


DEFAULT = json.loads((ROOT / "default-parameters.json").read_text(encoding="utf-8"))["image-format"]
OTHER = "png" if DEFAULT != "png" else "svg"


@pytest.fixture
def app(tmp_path):
    at = AppTest.from_string(PAGE)
    with open(ROOT / "settings.json", "r", encoding="utf-8") as f:
        at.session_state.settings = json.load(f)
    at.session_state.settings["test"] = True
    # Keep the workspace this test writes out of the real workspaces folder.
    at.session_state.settings["workspaces_dir"] = str(tmp_path)
    at.secrets["workspace"] = "test"
    return at


def test_sidebar_format_reaches_insight(app, monkeypatch):
    calls = []
    fake = types.ModuleType("openms_insight")
    fake.set_image_format = calls.append
    monkeypatch.setitem(sys.modules, "openms_insight", fake)

    app.run(timeout=60)
    assert not app.exception
    assert calls and calls[-1] == app.session_state["image-format"] == DEFAULT

    app.selectbox(key="image-format").set_value(OTHER).run(timeout=60)
    assert not app.exception
    assert calls[-1] == OTHER


def test_insight_release_without_setting(app, monkeypatch):
    # An older release: the package imports, the function does not exist
    monkeypatch.setitem(sys.modules, "openms_insight", types.ModuleType("openms_insight"))
    app.run(timeout=60)
    assert not app.exception


def test_insight_not_installed(app, monkeypatch):
    # None in sys.modules makes any import of the name raise ImportError
    monkeypatch.setitem(sys.modules, "openms_insight", None)
    app.run(timeout=60)
    assert not app.exception


def test_options_follow_insight_list(app, monkeypatch):
    # The sidebar offers exactly the formats Insight lists, in its order
    fake = types.ModuleType("openms_insight")
    fake.IMAGE_FORMATS = ("png", "svg")
    fake.set_image_format = lambda fmt: None
    monkeypatch.setitem(sys.modules, "openms_insight", fake)
    app.run(timeout=60)
    assert not app.exception
    box = app.selectbox(key="image-format")
    assert box.options == ["png", "svg"]
    assert box.value == DEFAULT


def test_saved_format_insight_dropped(app, monkeypatch):
    # A saved format Insight no longer lists falls back to its first one
    fake = types.ModuleType("openms_insight")
    fake.IMAGE_FORMATS = ("png",)
    fake.set_image_format = lambda fmt: None
    monkeypatch.setitem(sys.modules, "openms_insight", fake)
    app.run(timeout=60)
    assert not app.exception
    assert app.selectbox(key="image-format").value == "png"
