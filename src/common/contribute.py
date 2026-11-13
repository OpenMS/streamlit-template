"""The "Want to contribute?" section of an app's front page.

It offers one prompt to paste into Claude Desktop (Claude Code works too). The prompt makes the agent read the ``contribute`` skill from the
template's repository and follow it: Git, a GitHub SSH key, forks and clones
of the app, the template and openms-insight, and the order in which to open
pull requests. The skill is read by URL because the person has nothing
cloned yet; it is template-owned, so every app points at the same file.
``"contribute": {"enabled": false}`` in settings.json hides the section.
"""

from __future__ import annotations

from typing import Any

SKILL_URL = (
    "https://raw.githubusercontent.com/OpenMS/streamlit-template/main/"
    ".claude/skills/contribute/SKILL.md"
)
SKILL_PAGE = (
    "https://github.com/OpenMS/streamlit-template/blob/main/"
    ".claude/skills/contribute/SKILL.md"
)
TEMPLATE_REPO = "OpenMS/streamlit-template"


def app_repository(settings: dict[str, Any]) -> str:
    """``owner/repo`` of the app, from ``github-user`` and ``repository-name``."""
    owner = str(settings.get("github-user") or "OpenMS").strip()
    repo = str(settings.get("repository-name") or "streamlit-template").strip()
    return f"{owner}/{repo}"


def contribute_prompt(settings: dict[str, Any]) -> str:
    """The prompt for this app, on one line.

    One line, because a terminal without bracketed paste submits at the first
    newline and would send half of it.
    """
    repo = app_repository(settings)
    if repo.lower() == TEMPLATE_REPO.lower():
        target = f"the OpenMS web app template (https://github.com/{TEMPLATE_REPO})"
        clones = "the template and openms-insight"
    else:
        name = str(settings.get("app-name") or repo.split("/")[-1]).strip()
        target = f"{name} (https://github.com/{repo})"
        clones = f"{name}, the OpenMS streamlit-template it is built on, and openms-insight"
    return (
        f"Read {SKILL_URL} and follow it to set me up to contribute to {target}: "
        f"Git, an SSH key for GitHub, forks and clones of {clones}, and how to open "
        "pull requests. Ask me before you install or change anything."
    )


def community_line(settings: dict[str, Any]) -> str:
    """The sentence that opens the section, naming the app."""
    name = str(settings.get("app-name") or "").strip()
    if not name or app_repository(settings).lower() == TEMPLATE_REPO.lower():
        name = "The OpenMS web app framework"
    return f"{name} is a community effort, carried by the open source community. Everyone is welcome."


def contribute_enabled(settings: dict[str, Any]) -> bool:
    """False when settings.json has ``"contribute": {"enabled": false}``."""
    return bool(settings.get("contribute", {}).get("enabled", True))


def render_contribute() -> None:
    """Draw the section; ``render_contributors()`` puts it at the top of its strip."""
    import streamlit as st

    settings = st.session_state.get("settings") or {}
    if not contribute_enabled(settings):
        return
    st.markdown("##### 🛠️ Want to contribute?")
    st.markdown(community_line(settings))
    st.caption(
        "Paste this prompt into **Claude Desktop** to get started. "
        "No programming experience required."
    )
    st.code(contribute_prompt(settings), language="text", wrap_lines=True)
    st.caption(f"[Read the instructions it follows]({SKILL_PAGE})")
