"""
Tests for new workspaces started from a demo (src/common/common.py).

``demo_workspaces.new_workspace`` names the demo every new workspace starts
from. Its large files are linked, not copied, so the first page of a new
session does not wait for the example data to be copied; small files (settings,
the cache index, file lists) are copied, so writing them never changes the
demo other visitors share. Streamlit is mocked before import, as in
tests/test_branding.py.
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

_saved_common = sys.modules.pop("src.common.common", None)

import src.common.common as common  # noqa: E402

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


import pytest  # noqa: E402


@pytest.fixture
def demos(tmp_path, monkeypatch):
    """A demo source folder with one demo 'default' and one 'other'."""
    source = tmp_path / "demos"
    big = b"x" * common.LINK_MIN_BYTES
    default = source / "default"
    (default / "cache" / "files" / "run").mkdir(parents=True)
    (default / "params.json").write_text("{}")
    (default / "cache" / "cache.db").write_bytes(b"sqlite")
    (default / "cache" / "files" / "run" / "data.pq").write_bytes(big)
    (default / "wf" / "input-files" / "mzML-files").mkdir(parents=True)
    (default / "wf" / "input-files" / "mzML-files" / "a.mzML").write_bytes(big)
    (default / "wf" / "input-files" / "mzML-files" / "external_files.txt").write_text("")
    (source / "other").mkdir()
    (source / "other" / "params.json").write_text("{}")
    monkeypatch.setattr(common, "LINK_EXAMPLE_FILES", True)
    return source


def _settings(source, new_workspace="default"):
    demo = {"enabled": True, "source_dirs": [str(source)]}
    if new_workspace is not None:
        demo["new_workspace"] = new_workspace
    common.st.session_state = FakeSessionState({"settings": {"demo_workspaces": demo}})


def test_large_files_are_linked_small_ones_copied(demos, tmp_path):
    target = tmp_path / "ws"
    common._symlink_tree(demos / "default", target)
    assert (target / "cache" / "files" / "run" / "data.pq").is_symlink()
    assert (target / "wf" / "input-files" / "mzML-files" / "a.mzML").is_symlink()
    for small in ("params.json", "cache/cache.db",
                  "wf/input-files/mzML-files/external_files.txt"):
        assert (target / small).is_file() and not (target / small).is_symlink(), small
    # Writing a copied file leaves the demo as it is
    (target / "cache" / "cache.db").write_bytes(b"changed")
    assert (demos / "default" / "cache" / "cache.db").read_bytes() == b"sqlite"


def test_online_workspace_starts_from_the_demo(demos, tmp_path):
    _settings(demos)
    workspace = tmp_path / "workspaces" / "0f1e"
    common.seed_new_workspace(workspace, "online")
    assert (workspace / "cache" / "files" / "run" / "data.pq").is_symlink()
    assert (workspace / "params.json").is_file()
    assert not (tmp_path / "workspaces" / "other").exists()


def test_local_default_workspace_gets_every_demo(demos, tmp_path):
    _settings(demos)
    workspace = tmp_path / "workspaces" / "default"
    common.seed_new_workspace(workspace, "local")
    assert (workspace / "wf" / "input-files" / "mzML-files" / "a.mzML").exists()
    assert (tmp_path / "workspaces" / "other" / "params.json").is_file()


def test_local_named_workspace_starts_empty(demos, tmp_path):
    _settings(demos)
    workspace = tmp_path / "workspaces" / "mine"
    common.seed_new_workspace(workspace, "local")
    assert not workspace.exists()


@pytest.mark.parametrize("name", [None, "missing"])
def test_without_a_demo_a_workspace_starts_empty(demos, tmp_path, name):
    _settings(demos, new_workspace=name)
    workspace = tmp_path / "workspaces" / "0f1e"
    common.seed_new_workspace(workspace, "online")
    assert not workspace.exists()
