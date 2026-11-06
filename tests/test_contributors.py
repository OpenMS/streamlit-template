"""Contributors section: data files, merging and HTML."""

import json
from pathlib import Path

from src.common import contributors as c
from utils import contributors as refresh_mod

SETTINGS = {"repository-name": "my-app", "app-name": "My App"}


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _framework(tmp_path):
    return _write(tmp_path / "fw.json", {
        "groups": [{"title": "Web app framework", "people": ["alice", "bob"]}],
        "names": {"alice": "Alice A."},
    })


def test_shipped_files_are_valid():
    for path in (c.FRAMEWORK_FILE, Path("contributors.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["groups"], path
        for group in data["groups"]:
            assert group["title"]
            assert all(c._valid_login(p) for p in group["people"]), path
        assert all(isinstance(v, str) for v in data.get("names", {}).values())


def test_this_repository_shows_its_groups_then_the_framework():
    settings = json.loads(Path("settings.json").read_text(encoding="utf-8"))
    app = json.loads(Path("contributors.json").read_text(encoding="utf-8"))
    framework = json.loads(c.FRAMEWORK_FILE.read_text(encoding="utf-8"))
    content = c.load(settings)
    titles = [g["title"] for g in content["groups"]]
    own = [g["title"] for g in app["groups"]] if app.get("repository") == settings["repository-name"] else []
    assert titles == own + [g["title"] for g in framework["groups"]]


def test_app_groups_come_first_and_names_merge(tmp_path):
    app = _write(tmp_path / "app.json", {
        "repository": "my-app", "name": "My App",
        "groups": [{"title": "This app", "people": ["carol", "carol", "alice"]}],
        "names": {"carol": "Carol C."},
    })
    content = c.load(SETTINGS, app, _framework(tmp_path))
    assert [g["title"] for g in content["groups"]] == ["This app", "Web app framework"]
    assert content["groups"][0]["people"] == ["carol", "alice"]
    assert content["names"] == {"alice": "Alice A.", "carol": "Carol C."}
    assert content["lead"].startswith("My App is open source")


def test_file_of_another_repository_is_ignored(tmp_path):
    app = _write(tmp_path / "app.json", {
        "repository": "streamlit-template",
        "groups": [{"title": "Tools", "people": ["dave"]}],
    })
    content = c.load(SETTINGS, app, _framework(tmp_path))
    assert [g["title"] for g in content["groups"]] == ["Web app framework"]
    assert content["lead"].startswith("My App")


def test_missing_app_file_and_switch_off(tmp_path):
    fw = _framework(tmp_path)
    assert c.load(SETTINGS, tmp_path / "none.json", fw)["groups"][0]["people"] == ["alice", "bob"]
    off = dict(SETTINGS, contributors={"enabled": False})
    assert c.load(off, tmp_path / "none.json", fw) is None
    assert c.load(SETTINGS, tmp_path / "none.json", tmp_path / "none2.json") is None


def test_html_escapes_and_drops_invalid_logins(tmp_path):
    app = _write(tmp_path / "app.json", {
        "repository": "my-app", "lead": "<b>x</b>",
        "groups": [{"title": "T<script>", "people": ["ok-user", "bad\"><img", "x" * 50]}],
        "names": {"ok-user": "Name <i>"},
    })
    out = c.to_html(c.load(SETTINGS, app, _framework(tmp_path)))
    assert "<script>" not in out and "<b>x</b>" not in out and "Name <i>" not in out
    assert "bad" not in out and "x" * 50 not in out
    assert "https://avatars.githubusercontent.com/ok-user?s=80" in out
    assert "https://github.com/ok-user" in out


def test_refresh_rebuilds_github_groups_only():
    pages = {
        "/repos/o/r/contributors?per_page=100&page=1": [
            {"login": "alice", "type": "User"},
            {"login": "dependabot[bot]", "type": "Bot"},
            {"login": "claude", "type": "User"},
            {"login": "bob", "type": "User"},
        ],
        "/users/bob": {"name": "Bob B."},
        "/users/zed": {"name": None},
    }
    data = {
        "groups": [
            {"title": "F", "github": "o/r", "exclude": ["claude"], "extra": ["zed"], "people": []},
            {"title": "Hand-kept", "people": ["kept"]},
        ],
        "names": {"alice": "Alice (kept)"},
    }
    out = refresh_mod.refresh(data, get=pages.__getitem__)
    assert out["groups"][0]["people"] == ["alice", "bob", "zed"]
    assert out["groups"][1]["people"] == ["kept"]
    assert out["names"] == {"alice": "Alice (kept)", "bob": "Bob B."}
