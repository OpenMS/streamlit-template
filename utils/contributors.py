"""Refresh the contributor lists from GitHub.

    python -m utils.contributors                       # both files
    python -m utils.contributors contributors.json     # one file

Every group in the given files (default: the framework list
``src/common/framework-contributors.json`` and the app's ``contributors.json``)
that names a ``github`` repository is rebuilt from that repository's
contributors, ordered by contributions: bots and the logins in ``exclude``
are left out, the logins in ``extra`` are added at the end. Groups without
``github`` are kept as they are. A name is looked up for each new login and
kept when it is already there, so a corrected name is not overwritten.
Set ``GITHUB_TOKEN`` for a higher rate limit.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import requests

API = "https://api.github.com"
DEFAULT_FILES = [Path("src/common/framework-contributors.json"), Path("contributors.json")]


def _get(path: str) -> Any:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(f"{API}{path}", headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def repo_contributors(repo: str, get: Callable[[str], Any] = _get) -> list[str]:
    """Logins of a repository's contributors, most contributions first, bots left out."""
    logins: list[str] = []
    page = 1
    while True:
        batch = get(f"/repos/{repo}/contributors?per_page=100&page={page}")
        if not batch:
            break
        for c in batch:
            if c.get("type") == "Bot" or c.get("login", "").endswith("[bot]"):
                continue
            logins.append(c["login"])
        if len(batch) < 100:
            break
        page += 1
    return logins


def user_name(login: str, get: Callable[[str], Any] = _get) -> str:
    try:
        return get(f"/users/{login}").get("name") or ""
    except requests.RequestException:
        return ""


def refresh(data: dict[str, Any], get: Callable[[str], Any] = _get) -> dict[str, Any]:
    names = data.setdefault("names", {})
    for group in data.get("groups", []):
        repo = group.get("github")
        if not repo:
            continue
        exclude = set(group.get("exclude", []))
        people = [p for p in repo_contributors(repo, get) if p not in exclude]
        people += [p for p in group.get("extra", []) if p not in people]
        group["people"] = people
        for login in people:
            if login not in names:
                name = user_name(login, get)
                if name:
                    names[login] = name
    return data


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] or DEFAULT_FILES
    for path in files:
        if not path.exists():
            print(f"{path}: not found, skipped")
            continue
        data = refresh(json.loads(path.read_text(encoding="utf-8")))
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{path}: refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
