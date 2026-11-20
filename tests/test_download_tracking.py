"""Installer download tracking: when it is on, and what the page script does."""

import re
import subprocess
import shutil

import pytest

from src.common.download_tracking import (
    INSTALLER_EXTENSIONS,
    tracker_script,
    tracking_enabled,
)


@pytest.mark.parametrize(
    "settings, expected",
    [
        ({}, False),
        ({"analytics": {"matomo": {"enabled": False}}}, False),
        ({"analytics": {"matomo": {"enabled": True}}}, True),
        ({"analytics": {"matomo": {"enabled": True, "track_downloads": True}}}, True),
        ({"analytics": {"matomo": {"enabled": True, "track_downloads": False}}}, False),
    ],
)
def test_tracking_enabled(settings, expected):
    assert tracking_enabled(settings) is expected


def _script(app="My App"):
    page = tracker_script(app)
    return re.search(r"<script>(.*)</script>", page, re.S).group(1)


def test_script_installs_once_and_names_the_app():
    js = _script('Quote " App')
    assert "__openmsDownloadTracking" in js
    # The app name is passed as JSON, so quotes cannot break the script
    assert '"app": "Quote \\" App"' in js


def test_script_reports_downloads_as_matomo_downloads():
    js = _script()
    assert 'trackLink(target, "download")' in js
    assert '"trackLink", target, "download"' in js
    assert 'event: "download"' in js
    assert '"/download/"' in js


def test_only_installers_are_reported():
    for ext in ("exe", "msi", "dmg", "pkg", "appimage", "deb", "rpm"):
        assert ext in INSTALLER_EXTENSIONS
    for ext in ("csv", "tsv", "xlsx", "zip", "png", "mzml"):
        assert ext not in INSTALLER_EXTENSIONS
    assert "if (!isInstaller(name)) return;" in _script()


def test_middle_click_is_reported():
    js = _script()
    assert 'addEventListener("click", onClick, true)' in js
    assert 'addEventListener("auxclick", onClick, true)' in js
    assert 'ev.type === "auxclick" && ev.button !== 1' in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_script_is_valid_javascript(tmp_path):
    path = tmp_path / "tracker.js"
    path.write_text(_script())
    subprocess.run(["node", "--check", str(path)], check=True)
