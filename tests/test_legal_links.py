"""
Tests for get_legal_links() in src/common/common.py.

get_legal_links() resolves the Impressum / Privacy Policy / Terms of Use URLs
shown in the sidebar footer (on every page) and the privacy-policy link wired
into the GDPR consent banner. It merges the optional "legal_links" object from
settings.json over the built-in official-OpenMS defaults so that:

  * apps built from a settings.json without a "legal_links" key still inherit
    working legal links by default,
  * a self-hosting fork can override any or all of the three URLs,
  * an empty/blank override value never erases a default.

Streamlit (and the other heavy runtime deps pulled in by common.py) are mocked
before import so the helper can be unit-tested without a running Streamlit app,
mirroring tests/test_parameter_presets.py.
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

from src.common.common import get_legal_links, DEFAULT_LEGAL_LINKS  # noqa: E402

# Restore the real modules (or remove ones that weren't present) so that other
# test modules get the genuine packages.
for _name, _orig in _saved_modules.items():
    if _orig is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _orig
# Restore the original cached common module (the real-streamlit-bound one, if
# any) so AppTest-based test modules keep getting the genuine package.
# get_legal_links keeps working: it holds a reference to the freshly-imported
# mock-bound module's globals (and the same `mock_streamlit` object the tests
# mutate).
if _saved_common is None:
    sys.modules.pop("src.common.common", None)
else:
    sys.modules["src.common.common"] = _saved_common


def setup_function(_):
    """Reset session_state before each test for isolation."""
    mock_streamlit.session_state = FakeSessionState()


def test_defaults_point_to_openms():
    """The built-in defaults are the official OpenMS pages."""
    assert DEFAULT_LEGAL_LINKS == {
        "impressum": "https://openms.de/impressum",
        "privacy": "https://openms.de/privacy",
        "terms": "https://openms.de/terms",
    }


def test_defaults_when_settings_not_loaded():
    """No settings loaded at all -> defaults, no crash."""
    mock_streamlit.session_state = FakeSessionState()
    assert get_legal_links() == DEFAULT_LEGAL_LINKS


def test_defaults_when_no_legal_links_key():
    """settings present but without 'legal_links' -> all OpenMS defaults."""
    mock_streamlit.session_state = FakeSessionState({"settings": {}})
    assert get_legal_links() == DEFAULT_LEGAL_LINKS


def test_overrides_replace_defaults():
    """A fork's custom legal_links replace every default."""
    mock_streamlit.session_state = FakeSessionState(
        {
            "settings": {
                "legal_links": {
                    "impressum": "https://acme.example/impressum",
                    "privacy": "https://acme.example/privacy",
                    "terms": "https://acme.example/terms",
                }
            }
        }
    )
    assert get_legal_links() == {
        "impressum": "https://acme.example/impressum",
        "privacy": "https://acme.example/privacy",
        "terms": "https://acme.example/terms",
    }


def test_partial_override_keeps_other_defaults():
    """Overriding only one link leaves the others at their OpenMS default."""
    mock_streamlit.session_state = FakeSessionState(
        {"settings": {"legal_links": {"impressum": "https://acme.example/impressum"}}}
    )
    links = get_legal_links()
    assert links["impressum"] == "https://acme.example/impressum"
    assert links["privacy"] == DEFAULT_LEGAL_LINKS["privacy"]
    assert links["terms"] == DEFAULT_LEGAL_LINKS["terms"]


def test_empty_or_none_override_falls_back_to_default():
    """A blank/None override must not erase the default for that key."""
    mock_streamlit.session_state = FakeSessionState(
        {"settings": {"legal_links": {"privacy": "", "impressum": None}}}
    )
    links = get_legal_links()
    assert links["privacy"] == DEFAULT_LEGAL_LINKS["privacy"]
    assert links["impressum"] == DEFAULT_LEGAL_LINKS["impressum"]
    assert links["terms"] == DEFAULT_LEGAL_LINKS["terms"]
