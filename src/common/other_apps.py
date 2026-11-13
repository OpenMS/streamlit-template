"""Links to the other OpenMS web apps, in the sidebar and on a front page.

The list is ``src/common/other-apps.json`` (template-owned), so every app
gets the same list through the template sync and a new app is added there
once. An app never lists itself: an entry whose ``repository`` is the app's
own ``github-user``/``repository-name`` from settings.json is left out.

settings.json may switch the section off or narrow it::

    "other_apps": {"enabled": false}
    "other_apps": {"hide": ["NASEWEIS"]}

``hide`` takes app names or repositories. Streamlit is imported only by the
two render functions, so ``load`` works without it.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

APPS_FILE = Path(__file__).with_name("other-apps.json")
SETTINGS_FILE = Path("settings.json")
DEFAULT_TITLE = "Other OpenMS web apps"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _key(value: Any) -> str:
    return str(value or "").strip().lower()


def load(settings: dict[str, Any] | None = None, apps_file: Path = APPS_FILE) -> dict[str, Any] | None:
    """Title and apps to show, or None when there is nothing to show."""
    settings = settings if settings is not None else _read_json(SETTINGS_FILE)
    options = settings.get("other_apps", {})
    if not isinstance(options, dict):
        options = {}
    if not options.get("enabled", True):
        return None
    own = _key(f"{settings.get('github-user', '')}/{settings.get('repository-name', '')}")
    hidden = {_key(h) for h in options.get("hide", []) if h}
    data = _read_json(apps_file)
    apps = []
    for app in data.get("apps", []):
        if not isinstance(app, dict):
            continue
        name, url = app.get("name"), app.get("url")
        if not name or not isinstance(url, str) or not url.startswith("https://"):
            continue
        repo = _key(app.get("repository"))
        if repo == own or _key(name) in hidden or (repo and repo in hidden):
            continue
        description = app.get("description")
        if not isinstance(description, str):
            description = ""
        apps.append({"name": name, "url": url, "description": description})
    if not apps:
        return None
    return {"title": data.get("title") or DEFAULT_TITLE, "apps": apps}


def sidebar_markdown(content: dict[str, Any]) -> str:
    """One line per app: its name as a link, then what it does."""
    return "\n".join(
        f"- [**{a['name']}**]({a['url']})"
        + (f"  \n  <small>{html.escape(a['description'])}</small>" if a["description"] else "")
        for a in content["apps"]
    )


def render_other_apps_sidebar(settings: dict[str, Any] | None = None) -> None:
    """A collapsed sidebar box listing the other apps."""
    content = load(settings)
    if content is None:
        return
    import streamlit as st

    with st.expander(f"**{content['title']}**", icon=":material/apps:"):
        st.markdown(sidebar_markdown(content), unsafe_allow_html=True)


def render_other_apps(settings: dict[str, Any] | None = None, columns: int = 3) -> None:
    """A front-page section: one card per app with a button that opens it."""
    content = load(settings)
    if content is None:
        return
    import streamlit as st

    st.markdown(f"## 🧭 {content['title']}")
    apps = content["apps"]
    for start in range(0, len(apps), columns):
        cols = st.columns(columns)
        for col, app in zip(cols, apps[start : start + columns]):
            with col.container(border=True):
                st.markdown(f"**{app['name']}**")
                if app["description"]:
                    st.caption(app["description"])
                st.link_button("Open", app["url"], icon=":material/open_in_new:")
