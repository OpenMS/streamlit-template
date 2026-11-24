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


def test_many_files_are_all_seeded_and_keep_their_times(demos, tmp_path):
    """Every file arrives, and copies keep their modification time."""
    run = demos / "default" / "cache" / "files" / "many"
    run.mkdir(parents=True)
    for i in range(200):
        f = run / f"part-{i}.tsv"
        f.write_text(str(i))
        os.utime(f, (1_000_000, 1_000_000))
    target = tmp_path / "ws"
    common._symlink_tree(demos / "default", target)
    copied = sorted((target / "cache" / "files" / "many").iterdir())
    assert len(copied) == 200
    assert all(not f.is_symlink() for f in copied)
    assert (target / "cache" / "files" / "many" / "part-7.tsv").read_text() == "7"
    assert int(copied[0].stat().st_mtime) == 1_000_000


def test_folders_named_in_settings_are_linked_whole(demos, tmp_path):
    """One link per result folder, however many files it holds."""
    many = demos / "default" / "cache" / "files" / "many"
    many.mkdir()
    for i in range(50):
        (many / f"part-{i}.tsv").write_text(str(i))
    target = tmp_path / "ws"
    common._symlink_tree(demos / "default", target, ["cache/files/*"])
    for name in ("run", "many"):
        linked = target / "cache" / "files" / name
        assert linked.is_symlink() and linked.resolve() == (demos / "default" / "cache" / "files" / name).resolve()
    assert (target / "cache" / "files" / "many" / "part-7.tsv").read_text() == "7"
    # Everything else is seeded as before
    assert not (target / "cache" / "files").is_symlink()
    assert not (target / "cache" / "cache.db").is_symlink()
    assert (target / "wf" / "input-files" / "mzML-files" / "a.mzML").is_symlink()
    assert not (target / "wf" / "input-files" / "mzML-files").is_symlink()


def test_new_workspace_links_the_folders_settings_name(demos, tmp_path):
    _settings(demos)
    common.st.session_state["settings"]["demo_workspaces"]["link_folders"] = ["cache/files/*"]
    workspace = tmp_path / "workspaces" / "0f1e"
    common.seed_new_workspace(workspace, "online")
    assert (workspace / "cache" / "files" / "run").is_symlink()


def test_workspace_appears_only_when_complete(demos, tmp_path, monkeypatch):
    """A failed setup leaves neither the workspace nor its staging folder."""
    _settings(demos)
    parent = tmp_path / "workspaces"
    parent.mkdir()

    def broken(item, target_item):
        raise OSError("storage gone")

    monkeypatch.setattr(common, "_seed_file", broken)
    assert common.copy_demo_workspace("default", parent / "0f1e") is False
    assert list(parent.iterdir()) == []


def test_seeding_leaves_no_staging_folder(demos, tmp_path):
    _settings(demos)
    parent = tmp_path / "workspaces"
    common.seed_new_workspace(parent / "0f1e", "online")
    assert [p.name for p in parent.iterdir()] == ["0f1e"]


def test_linked_folder_in_the_demo_becomes_a_real_folder(demos, tmp_path):
    """Small files under a linked demo folder are copies, not shared files."""
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "params.json").write_text("{}")
    (demos / "default" / "linked").symlink_to(shared, target_is_directory=True)
    target = tmp_path / "ws"
    common._symlink_tree(demos / "default", target)
    assert not (target / "linked").is_symlink()
    assert not (target / "linked" / "params.json").is_symlink()


def test_unreadable_demo_folder_fails_the_setup(demos, tmp_path, monkeypatch):
    real_walk = os.walk

    def walk(top, onerror=None, **kwargs):
        if onerror is not None:
            onerror(PermissionError("cannot list"))
        yield from real_walk(top, **kwargs)

    monkeypatch.setattr(common.os, "walk", walk)
    _settings(demos)
    parent = tmp_path / "workspaces"
    parent.mkdir()
    assert common.copy_demo_workspace("default", parent / "0f1e") is False
    assert list(parent.iterdir()) == []


def test_workspace_set_up_meanwhile_by_another_session_is_kept(demos, tmp_path, monkeypatch):
    _settings(demos)
    workspace = tmp_path / "workspaces" / "0f1e"
    real_tree = common._symlink_tree

    def other_session_first(source, target, *args):
        real_tree(source, target, *args)
        workspace.mkdir(parents=True)
        (workspace / "mine.mzML").write_text("added by the user")

    monkeypatch.setattr(common, "_symlink_tree", other_session_first)
    assert common.copy_demo_workspace("default", workspace) is True
    assert (workspace / "mine.mzML").read_text() == "added by the user"
    assert [p.name for p in workspace.parent.iterdir()] == ["0f1e"]
