"""Release assets found for the app's installers and its command line tools."""

from types import SimpleNamespace

import pytest

from src.common import installers
from src.common.download_tracking import INSTALLER_EXTENSIONS

ASSETS = {
    "FLASHApp-2.0.0-Setup.exe": "https://example.org/FLASHApp-2.0.0-Setup.exe",
    "FLASHApp-2.0.0-macOS-arm64.dmg": "https://example.org/app.dmg",
    "FLASHApp-2.0.0-Linux-x86_64.AppImage": "https://example.org/app.AppImage",
    "FLASHApp-command-line-tools-Windows-x86_64.exe": "https://example.org/tools.exe",
    "FLASHApp-command-line-tools-macOS-arm64.pkg": "https://example.org/tools.pkg",
    "FLASHApp-command-line-tools-Linux-x86_64.deb": "https://example.org/tools.deb",
    "_release_page": "https://example.org/release",
}


@pytest.fixture
def release(monkeypatch):
    state = {"settings": {"github-user": "OpenMS", "repository-name": "FLASHApp"}}
    monkeypatch.setattr(installers, "st", SimpleNamespace(session_state=state))
    assets = dict(ASSETS)
    monkeypatch.setattr(installers, "latest_release_assets", lambda user, repo: assets)
    return assets


def test_app_installers_leave_out_the_tools(release):
    found = installers.find_installers()
    assert found == {
        "windows": "https://example.org/FLASHApp-2.0.0-Setup.exe",
        "macos": "https://example.org/app.dmg",
        "linux": "https://example.org/app.AppImage",
        "release": "https://example.org/release",
    }


def test_tool_installers(release):
    assert installers.find_tool_installers() == {
        "windows": "https://example.org/tools.exe",
        "macos": "https://example.org/tools.pkg",
        "linux": "https://example.org/tools.deb",
        "release": "https://example.org/release",
    }


def test_release_without_tools(release):
    for name in [n for n in release if "command-line-tools" in n]:
        del release[name]
    assert installers.find_tool_installers() == {"release": "https://example.org/release"}


def test_no_release(monkeypatch):
    monkeypatch.setattr(installers, "st", SimpleNamespace(session_state={"settings": {}}))
    assert installers.find_tool_installers() == {}


def test_tool_names_never_look_like_app_installers():
    # The Dockerfile bundles the release asset ending in -Setup.exe.
    for _, _, tool_suffix, _ in installers.TOOL_PLATFORMS:
        assert not any(tool_suffix.endswith(s) for _, _, s, _ in installers.PLATFORMS)


def test_tool_downloads_are_tracked():
    for _, _, suffix, _ in installers.TOOL_PLATFORMS:
        assert suffix.rsplit(".", 1)[1] in INSTALLER_EXTENSIONS


class _FakeSt:
    """Records what render_tool_installer_line() writes."""

    def __init__(self, state):
        self.session_state = state
        self.html = []

    def markdown(self, text, **_):
        self.html.append(text)


def _fake_st(monkeypatch, location):
    fake = _FakeSt({"location": location, "settings": {"github-user": "OpenMS", "repository-name": "FLASHApp"}})
    monkeypatch.setattr(installers, "st", fake)
    return fake


def test_tool_line_links_the_release(release, monkeypatch):
    fake = _fake_st(monkeypatch, "online")
    assert installers.render_tool_installer_line()
    (line,) = fake.html
    for url in ("https://example.org/tools.exe", "https://example.org/tools.pkg", "https://example.org/tools.deb"):
        assert f'href="{url}"' in line
    assert line.index("Windows") < line.index("macOS") < line.index("Linux")


def test_no_tool_line_without_tools_or_offline(release, monkeypatch):
    fake = _fake_st(monkeypatch, "local")
    assert not installers.render_tool_installer_line()
    for name in [n for n in release if "command-line-tools" in n]:
        del release[name]
    fake = _fake_st(monkeypatch, "online")
    assert not installers.render_tool_installer_line()
    assert fake.html == []


def test_no_download_box_offline(release, monkeypatch):
    fake = _fake_st(monkeypatch, "local")
    assert not installers.render_download_box()
    assert fake.html == []
