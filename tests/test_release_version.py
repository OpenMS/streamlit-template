"""The release tag and `version` in settings.json (.github/scripts/release_version.py)."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "release_version.py"
spec = importlib.util.spec_from_file_location("release_version", SCRIPT)
rv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rv)


@pytest.mark.parametrize(
    "tag, version",
    [
        ("v2.4.0", "2.4.0"),
        ("refs/tags/v2.4.0", "2.4.0"),
        ("2.0.0-alpha.15", "2.0.0-alpha.15"),
        ("OpenDDA-1.3.0", "1.3.0"),
        ("OpenDDA-2.0.0-alpha.1", "2.0.0-alpha.1"),
        ("FLASHApp-1.1.0", "1.1.0"),
        ("v-1.1", "1.1"),
        ("0.1.4", "0.1.4"),
        ("v2.0.0-full", "2.0.0"),
    ],
)
def test_version_from_tag(tag, version):
    assert rv.version_from_tag(tag) == version


@pytest.mark.parametrize("tag", ["latest", "nightly", "release-notes"])
def test_tag_without_version(tag):
    with pytest.raises(ValueError):
        rv.version_from_tag(tag)


def test_same_version():
    assert rv.same_version("1.1", "1.1.0")
    assert rv.same_version("2.0.0-alpha.15", "2.0.0a15")
    assert not rv.same_version("2.0.0-alpha.13", "2.0.0-alpha.15")
    assert not rv.same_version("1.3.0", "2.0.0-alpha.1")


def test_order():
    keys = [rv.version_key(v) for v in ["1.3.0", "2.0.0-alpha.1", "2.0.0-alpha.15", "2.0.0-beta.1", "2.0.0", "2.1"]]
    assert keys == sorted(keys)


def _settings(tmp_path, version):
    p = tmp_path / "settings.json"
    p.write_text('{\n    "app-name": "X",\n    "version": "%s",\n    "nested": {"version": "keep"}\n}\n' % version)
    return p


def test_check(tmp_path, capsys):
    p = _settings(tmp_path, "2.0.0-alpha.13")
    assert rv.main(["check", "2.0.0-alpha.15", str(p)]) == 1
    assert "says '2.0.0-alpha.13'" in capsys.readouterr().out
    assert rv.main(["check", "2.0.0-alpha.13", str(p)]) == 0


def test_set_keeps_the_layout(tmp_path):
    p = _settings(tmp_path, "1.2.0")
    before = p.read_text()
    assert rv.main(["set", "OpenDDA-1.3.0", str(p)]) == 0
    after = p.read_text()
    assert after == before.replace('"version": "1.2.0"', '"version": "1.3.0"')
    assert json.loads(after)["nested"]["version"] == "keep"


def test_template_settings_version_is_a_version():
    settings = Path(__file__).resolve().parents[1] / "settings.json"
    rv.version_from_tag(json.loads(settings.read_text())["version"])


def test_set_skips_a_nested_version_before_the_top_level_one(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{\n    "meta": {\n        "version": "keep"\n    },\n    "version": "1.0.0"\n}\n')
    assert rv.main(["set", "v2.0.0", str(p)]) == 0
    data = json.loads(p.read_text())
    assert data["version"] == "2.0.0"
    assert data["meta"]["version"] == "keep"
    assert '"meta": {\n' in p.read_text()  # layout kept
