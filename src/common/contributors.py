"""Contributors section for an app's front page.

Two data files feed it:

- ``src/common/framework-contributors.json`` (template-owned): everyone who
  contributed to the OpenMS web app framework. Every app gets it through the
  template sync, so the framework group is the same in all apps.
- ``contributors.json`` in the repository root (app-owned): the app's own
  groups, for example the app itself, the OpenMS tools it runs and the
  visualizations it uses. Its ``repository`` must match ``repository-name``
  in settings.json; a copy that belongs to another repository (the
  template's example, for instance) is ignored, so an app without its own
  file shows the framework group only. The framework group comes after the
  app's own groups, or before them with ``"framework": "first"`` (the
  template does this, since the framework is what it shows).

People are listed by GitHub handle; the picture is loaded from GitHub, not
stored in the repository. ``python -m utils.contributors`` refreshes every
group that names a ``github`` repository from that repository's
contributors.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

FRAMEWORK_FILE = Path(__file__).with_name("framework-contributors.json")
APP_FILE = Path("contributors.json")
SETTINGS_FILE = Path("settings.json")

DEFAULT_LEAD = "{name} is open source, built on OpenMS and the OpenMS web app framework."
AVATAR_URL = "https://avatars.githubusercontent.com/{login}?s=80"
PROFILE_URL = "https://github.com/{login}"

_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")

CSS = """
<style>
.ctb h3{margin:.2rem 0}
.ctb .lead{opacity:.75;margin:0 0 .6rem 0}
.ctb .grp{font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;opacity:.65;margin:12px 0 6px 0}
.ctb .grid{display:flex;flex-wrap:wrap;gap:12px 4px}
.ctb a{color:inherit;text-decoration:none}
.ctb .p{width:104px;text-align:center;font-size:.66rem;line-height:1.2;opacity:.9}
.ctb .p .n{font-size:.74rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctb .p .h{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctb .p img{width:40px;height:40px;border-radius:50%;display:block;margin:0 auto 3px auto;background:rgba(128,128,128,.2)}
.ctb.compact h3{font-size:1.05rem}
.ctb.compact .lead{font-size:.8rem}
.ctb.compact .grp{font-size:.66rem;margin:10px 0 4px 0}
.ctb.compact .grid{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px}
.ctb.compact .c{display:flex;align-items:center;gap:7px;min-width:0;font-size:.74rem;line-height:1.15}
.ctb.compact .c span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctb.compact img.a{width:26px;height:26px;flex:none;border-radius:50%;display:block;background:rgba(128,128,128,.2)}
</style>
"""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _valid_login(login: Any) -> bool:
    return isinstance(login, str) and bool(_LOGIN.match(login))


def load(
    settings: dict[str, Any] | None = None,
    app_file: Path = APP_FILE,
    framework_file: Path = FRAMEWORK_FILE,
) -> dict[str, Any] | None:
    """The section's content: lead sentence, groups and names.

    Returns None when the section is switched off in settings.json
    (``"contributors": {"enabled": false}``) or there is nobody to show.
    """
    settings = settings if settings is not None else _read_json(SETTINGS_FILE)
    if not settings.get("contributors", {}).get("enabled", True):
        return None
    framework = _read_json(framework_file)
    app = _read_json(app_file)
    if app.get("repository") != settings.get("repository-name"):
        app = {}

    names: dict[str, str] = {}
    names.update(framework.get("names", {}))
    names.update(app.get("names", {}))

    if app.get("framework") == "first":
        ordered = list(framework.get("groups", [])) + list(app.get("groups", []))
    else:
        ordered = list(app.get("groups", [])) + list(framework.get("groups", []))
    groups = []
    for group in ordered:
        people = [p for p in dict.fromkeys(group.get("people", [])) if _valid_login(p)]
        if people and group.get("title"):
            groups.append({"title": group["title"], "people": people})
    if not groups:
        return None

    app_name = app.get("name") or settings.get("app-name", "This app")
    lead = app.get("lead") or DEFAULT_LEAD.format(name=app_name)
    return {"lead": lead, "groups": groups, "names": names}


def _person(login: str, name: str) -> str:
    login_e = html.escape(login)
    name_e = html.escape(name) if name else "&nbsp;"
    return (
        f'<a href="{PROFILE_URL.format(login=login_e)}" target="_blank" rel="noopener">'
        f'<div class="p"><img src="{AVATAR_URL.format(login=login_e)}" alt="" loading="lazy">'
        f'<div class="n">{name_e}</div><div class="h">@{login_e}</div></div></a>'
    )


def _avatar(login: str, name: str) -> str:
    login_e = html.escape(login)
    tip = html.escape(f"{name} (@{login})" if name else f"@{login}")
    label = html.escape(name or f"@{login}")
    return (
        f'<a class="c" href="{PROFILE_URL.format(login=login_e)}" target="_blank" rel="noopener" title="{tip}">'
        f'<img class="a" src="{AVATAR_URL.format(login=login_e)}" alt="" loading="lazy">'
        f"<span>{label}</span></a>"
    )


def to_html(content: dict[str, Any], compact: bool = False) -> str:
    """The section as HTML; ``compact`` lists small pictures with names in two columns, the handle on hover."""
    person = _avatar if compact else _person
    parts = [
        CSS,
        f'<div class="ctb{" compact" if compact else ""}">',
        "<h3>🤝 Contributors</h3>",
        f'<p class="lead">{html.escape(content["lead"])}</p>',
    ]
    for group in content["groups"]:
        parts.append(f'<div class="grp">{html.escape(group["title"])}</div><div class="grid">')
        parts.extend(person(p, content["names"].get(p, "")) for p in group["people"])
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


STRIP_KEY = "openms-side-strip"


def render_contributors(contribute: bool = True) -> None:
    """Draw the contributors in a strip on the right of the page.

    Call it once on the front page, anywhere: on a wide window the strip is
    fixed to the right edge (``.st-key-openms-side-strip`` in
    ``src/common/theme.css``) and stays in view while the page scrolls; on a
    narrow one it is drawn where it is called. ``contribute`` puts the
    "Want to contribute?" prompt (``src/common/contribute.py``) at its top.
    """
    import streamlit as st

    from src.common.contribute import contribute_enabled, render_contribute

    content = load(st.session_state.get("settings"))
    show_contribute = contribute and contribute_enabled(
        st.session_state.get("settings") or {}
    )
    if not content and not show_contribute:
        return
    with st.container(key=STRIP_KEY):
        if show_contribute:
            render_contribute()
        if content:
            st.html(to_html(content, compact=True))
