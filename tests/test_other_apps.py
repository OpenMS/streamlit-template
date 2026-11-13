"""The list of other OpenMS web apps (src/common/other_apps.py)."""

import json

from src.common import other_apps

TEMPLATE = {"github-user": "OpenMS", "repository-name": "streamlit-template"}


def names(content):
    return [a["name"] for a in content["apps"]]


def test_template_lists_every_app():
    content = other_apps.load(TEMPLATE)
    assert names(content) == ["FLASHApp", "NASEWEIS", "OpenDDA"]
    assert all(a["url"].startswith("https://") for a in content["apps"])


def test_an_app_does_not_list_itself():
    for repo, name in [("FLASHApp", "FLASHApp"), ("nase-weis", "NASEWEIS"), ("quantms-web", "OpenDDA")]:
        content = other_apps.load({"github-user": "OpenMS", "repository-name": repo})
        assert name not in names(content)
        assert len(content["apps"]) == 2


def test_own_entry_matched_regardless_of_case():
    content = other_apps.load({"github-user": "openms", "repository-name": "flashapp"})
    assert "FLASHApp" not in names(content)


def test_switched_off_or_hidden():
    assert other_apps.load({**TEMPLATE, "other_apps": {"enabled": False}}) is None
    content = other_apps.load({**TEMPLATE, "other_apps": {"hide": ["naseweis", "OpenMS/quantms-web"]}})
    assert names(content) == ["FLASHApp"]


def test_nothing_left_shows_nothing(tmp_path):
    f = tmp_path / "apps.json"
    f.write_text(json.dumps({"apps": [{"name": "X", "repository": "OpenMS/x", "url": "https://x"}]}))
    assert other_apps.load({"github-user": "OpenMS", "repository-name": "x"}, f) is None


def test_bad_entries_are_skipped(tmp_path):
    f = tmp_path / "apps.json"
    f.write_text(json.dumps({"apps": [
        {"name": "NoUrl"},
        {"name": "Js", "url": "javascript:alert(1)"},
        "nonsense",
        {"name": "Ok", "url": "https://ok.example", "description": "<b>x</b>"},
    ]}))
    content = other_apps.load(TEMPLATE, f)
    assert names(content) == ["Ok"]
    assert content["title"] == other_apps.DEFAULT_TITLE
    assert "&lt;b&gt;" in other_apps.sidebar_markdown(content)


def test_missing_file_shows_nothing(tmp_path):
    assert other_apps.load(TEMPLATE, tmp_path / "missing.json") is None


def test_non_text_description_is_dropped(tmp_path):
    apps_file = tmp_path / "apps.json"
    apps_file.write_text(json.dumps({"apps": [
        {"name": "A", "url": "https://a.example", "description": 5},
        {"name": "B", "url": "https://b.example"},
    ]}))
    content = other_apps.load(TEMPLATE, apps_file=apps_file)
    assert [a["description"] for a in content["apps"]] == ["", ""]
    assert "<small>" not in other_apps.sidebar_markdown(content)
