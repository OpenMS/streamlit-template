"""
Tests for local_workspaces_dir() in src/common/common.py.

The Electron desktop build sets LOCAL_WORKSPACES_DIR so workspaces live in the
user profile rather than next to the install folder. Without it, local mode
keeps the settings.json behaviour. Imports are mocked as in test_legal_links.py.
"""
import os
import sys
from unittest.mock import MagicMock

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)


class FakeSessionState(dict):
    """Minimal stand-in for Streamlit's SessionState.

    Supports both attribute access (``state.settings``) and item/membership
    access (``"settings" in state``), exactly like the real SessionState that
    common.py relies on.
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


# Mock streamlit (with a SessionState-like session_state) and the other heavy
# imports pulled in by src/common/common.py, so importing get_legal_links here
# doesn't require a running Streamlit app context.
#
# IMPORTANT: these mocks are installed into sys.modules only for the duration of
# the import below and then restored, so they don't leak into other test modules
# (e.g. the AppTest-based tests that need the real `streamlit` package). This
# mirrors the pattern in tests/test_parameter_presets.py.
mock_streamlit = MagicMock()
mock_streamlit.session_state = FakeSessionState()

_MOCKED_MODULES = {
    "streamlit": mock_streamlit,
    "streamlit.components": MagicMock(),
    "streamlit.components.v1": MagicMock(),
    "streamlit.source_util": MagicMock(),
    "pandas": MagicMock(),
    "psutil": MagicMock(),
    # Local submodules with their own heavy deps (e.g. the captcha image library).
    "src.common.captcha_": MagicMock(),
    "src.common.admin": MagicMock(),
}
_saved_modules = {name: sys.modules.get(name) for name in _MOCKED_MODULES}
sys.modules.update(_MOCKED_MODULES)

# Force a FRESH import of src.common.common under the streamlit mock, even if an
# earlier test module (e.g. test_gui.py) already imported the real-streamlit-bound
# version. Save whatever was cached first so we can restore it afterwards.
_saved_common = sys.modules.pop("src.common.common", None)

from src.common.common import local_workspaces_dir  # noqa: E402

# Restore the real modules (or remove ones that weren't present) so that other
# test modules get the genuine packages.
for _name, _orig in _saved_modules.items():
    if _orig is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _orig
# Restore the original cached common module (the real-streamlit-bound one, if
# any) so AppTest-based test modules keep getting the genuine package.
# local_workspaces_dir keeps working: it holds a reference to the freshly-imported
# mock-bound module's globals (and the same `mock_streamlit` object the tests
# mutate).
if _saved_common is None:
    sys.modules.pop("src.common.common", None)
else:
    sys.modules["src.common.common"] = _saved_common


from pathlib import Path  # noqa: E402

SETTINGS = {"workspaces_dir": "..", "repository-name": "my-app"}


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCAL_WORKSPACES_DIR", str(tmp_path))
    assert local_workspaces_dir(SETTINGS) == tmp_path


def test_settings_dir_without_override(monkeypatch):
    monkeypatch.delenv("LOCAL_WORKSPACES_DIR", raising=False)
    assert local_workspaces_dir(SETTINGS) == Path("..", "workspaces-my-app")


def test_empty_override_is_ignored(monkeypatch):
    monkeypatch.setenv("LOCAL_WORKSPACES_DIR", "")
    assert local_workspaces_dir(SETTINGS) == Path("..", "workspaces-my-app")


def test_parent_dir_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("LOCAL_WORKSPACES_DIR", raising=False)
    assert local_workspaces_dir({"workspaces_dir": "", "repository-name": "x"}) == Path("..")
