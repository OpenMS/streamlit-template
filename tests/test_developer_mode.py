"""Developer mode gates workspace sync when ``developer_only`` is set."""
import hashlib
from types import SimpleNamespace

import pytest

from src.common import developer, workspace_sync


class _State(dict):
    __getattr__ = dict.__getitem__


@pytest.fixture
def state(monkeypatch):
    s = _State(settings={
        "enable_workspaces": True,
        "developer_mode": {"password_sha256": hashlib.sha256(b"open sesame").hexdigest()},
        "workspace_sync": {"enabled": True, "developer_only": True},
    })
    fake = SimpleNamespace(session_state=s)
    monkeypatch.setattr(developer, "st", fake)
    monkeypatch.setattr(workspace_sync, "st", fake)
    return s


def test_password_is_checked_against_the_hash(state):
    assert developer.verify_password("open sesame")
    assert not developer.verify_password("open")
    assert not developer.verify_password("")
    state["settings"]["developer_mode"] = {}
    assert not developer.verify_password("open sesame")


def test_sync_is_hidden_until_developer_mode_is_unlocked(state):
    assert not workspace_sync.sync_enabled()
    state["developer-mode-password"] = "wrong"
    developer._unlock()
    assert not workspace_sync.sync_enabled() and state["developer-mode-failed"]
    state["developer-mode-password"] = "open sesame"
    developer._unlock()
    assert workspace_sync.sync_enabled()
    assert "developer-mode-password" not in state


def test_sync_without_developer_only_and_when_disabled(state):
    state["settings"]["workspace_sync"]["developer_only"] = False
    assert workspace_sync.sync_enabled()
    state["settings"]["workspace_sync"]["enabled"] = False
    state["developer-mode"] = True
    assert not workspace_sync.sync_enabled()


def test_environment_overrides_the_settings_hash(state, monkeypatch):
    monkeypatch.setenv("DEVELOPER_PASSWORD_SHA256", hashlib.sha256(b"per deployment").hexdigest())
    assert developer.verify_password("per deployment")
    assert not developer.verify_password("open sesame")
    monkeypatch.setenv("DEVELOPER_PASSWORD_SHA256", "none")
    assert not developer.verify_password("open sesame")
