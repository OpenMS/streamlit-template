"""
Tests for get_branding() in src/common/common.py.

get_branding() picks the browser tab icon, the sidebar logo, the collapsed
sidebar icon and the app icon from the optional "branding" object in
settings.json, per light or dark theme, falling back to the OpenMS logo.
Streamlit is mocked before import, as in tests/test_legal_links.py.
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

from src.common.common import get_branding, DEFAULT_LOGO  # noqa: E402

# Restore the real modules (or remove ones that weren't present) so that other
# test modules get the genuine packages.
for _name, _orig in _saved_modules.items():
    if _orig is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _orig
# Restore the original cached common module (the real-streamlit-bound one, if
# any) so AppTest-based test modules keep getting the genuine package.
# get_branding keeps working: it holds a reference to the freshly-imported
# mock-bound module's globals (and the same `mock_streamlit` object the tests
# mutate).
if _saved_common is None:
    sys.modules.pop("src.common.common", None)
else:
    sys.modules["src.common.common"] = _saved_common


def setup_function(_):
    """Reset session_state before each test for isolation."""
    mock_streamlit.session_state = FakeSessionState()


def _settings(branding):
    mock_streamlit.session_state = FakeSessionState({"settings": {"branding": branding}})


def test_openms_logo_without_branding():
    """No branding key: every image is the OpenMS logo, at the medium size."""
    mock_streamlit.session_state = FakeSessionState({"settings": {}})
    for theme in ("light", "dark"):
        assert get_branding(theme) == {
            "page_icon": DEFAULT_LOGO,
            "logo": DEFAULT_LOGO,
            "logo_icon": DEFAULT_LOGO,
            "app_icon": DEFAULT_LOGO,
            "logo_size": "medium",
        }


def test_openms_logo_when_settings_not_loaded():
    assert get_branding("light")["logo"] == DEFAULT_LOGO


def test_theme_specific_images():
    _settings(
        {
            "page_icon": "assets/tab.svg",
            "logo": {"light": "assets/logo-light.svg", "dark": "assets/logo-dark.svg"},
            "logo_icon": {"light": "assets/icon-light.svg", "dark": "assets/icon-dark.svg"},
            "logo_size": "large",
        }
    )
    light, dark = get_branding("light"), get_branding("dark")
    assert light["logo"] == "assets/logo-light.svg"
    assert dark["logo"] == "assets/logo-dark.svg"
    assert light["logo_icon"] == "assets/icon-light.svg"
    assert dark["logo_icon"] == "assets/icon-dark.svg"
    assert light["page_icon"] == dark["page_icon"] == "assets/tab.svg"
    assert light["logo_size"] == "large"


def test_one_path_serves_both_themes():
    _settings({"logo": "assets/logo.svg"})
    assert get_branding("light")["logo"] == get_branding("dark")["logo"] == "assets/logo.svg"


def test_missing_theme_uses_the_other():
    _settings({"logo": {"light": "assets/logo-light.svg"}})
    assert get_branding("dark")["logo"] == "assets/logo-light.svg"


def test_logo_icon_follows_app_icon_then_logo():
    _settings({"logo": "assets/logo.svg", "app_icon": "assets/app.svg"})
    assert get_branding("light")["logo_icon"] == "assets/app.svg"
    _settings({"logo": "assets/logo.svg"})
    assert get_branding("light")["logo_icon"] == "assets/logo.svg"
    assert get_branding("light")["app_icon"] == "assets/logo.svg"


def test_unknown_theme_is_light_and_bad_size_is_medium():
    _settings(
        {
            "logo": {"light": "assets/l.svg", "dark": "assets/d.svg"},
            "logo_size": "huge",
        }
    )
    assert get_branding("custom")["logo"] == "assets/l.svg"
    assert get_branding("custom")["logo_size"] == "medium"


def test_empty_values_fall_back_to_openms():
    _settings({"page_icon": "", "logo": {"light": "", "dark": None}})
    branding = get_branding("dark")
    assert branding["page_icon"] == DEFAULT_LOGO
    assert branding["logo"] == DEFAULT_LOGO
