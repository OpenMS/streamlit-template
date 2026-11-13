"""The "Want to contribute?" prompt and the skill it points at."""

import pytest
from pathlib import Path

from src.common.contribute import SKILL_URL, app_repository, contribute_prompt

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "contribute" / "SKILL.md"


def test_prompt_names_the_app_and_its_repository():
    prompt = contribute_prompt(
        {"app-name": "FLASHApp", "github-user": "OpenMS", "repository-name": "FLASHApp"}
    )
    assert SKILL_URL in prompt
    assert "FLASHApp (https://github.com/OpenMS/FLASHApp)" in prompt
    assert "streamlit-template" in prompt and "openms-insight" in prompt


def test_prompt_is_one_line():
    for settings in (
        {"app-name": "OpenDDA", "github-user": "OpenMS", "repository-name": "quantms-web"},
        {},
    ):
        assert "\n" not in contribute_prompt(settings)


def test_template_itself_names_two_repositories():
    prompt = contribute_prompt(
        {"app-name": "OpenMS WebApp Template", "github-user": "OpenMS",
         "repository-name": "streamlit-template"}
    )
    assert "the OpenMS web app template (https://github.com/OpenMS/streamlit-template)" in prompt
    assert "the template and openms-insight" in prompt


def test_missing_settings_fall_back_to_the_template():
    assert app_repository({}) == "OpenMS/streamlit-template"


def test_prompt_points_at_the_skill_in_this_repository():
    # The prompt reads the skill from the template's main branch by URL.
    assert SKILL_URL.endswith(".claude/skills/contribute/SKILL.md")
    assert SKILL.is_file()
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\nname: contribute\n")
    for repo in ("OpenMS/streamlit-template", "t0mdavid-m/OpenMS-Insight"):
        assert repo in text


def test_readme_shows_the_templates_prompt():
    import json

    settings = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
    if (settings.get("github-user"), settings.get("repository-name")) != (
        "OpenMS",
        "streamlit-template",
    ):
        # An app keeps its own README; only the template's shows this prompt.
        pytest.skip("README prompt is checked in the template only")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert contribute_prompt(settings) in readme


def test_community_line_names_the_app():
    from src.common.contribute import community_line

    line = community_line(
        {"app-name": "FLASHApp", "github-user": "OpenMS", "repository-name": "FLASHApp"}
    )
    assert line.startswith("FLASHApp is a community effort")
    assert "Everyone is welcome" in line
    assert community_line({}).startswith("The OpenMS web app framework")
