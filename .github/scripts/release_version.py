#!/usr/bin/env python3
"""Keep `version` in settings.json and the release tags of an app in step.

Used by .github/workflows/release-version.yml, build-image.yml and
build-desktop-app.yaml, in the template and in every app made from it.
Standard library only.

    python .github/scripts/release_version.py version <tag>
        prints the version a release tag stands for
    python .github/scripts/release_version.py set <tag> [settings.json]
        writes that version into settings.json (what a build from a tag ships)
    python .github/scripts/release_version.py check <tag> [settings.json]
        exits 1 when settings.json says another version than the tag

Release tags carry the version with an optional prefix: `v2.4.0`, `v-1.1`,
`OpenDDA-1.3.0`, `FLASHApp-1.1.0`, `2.0.0-alpha.15`. An image suffix
(`-full`, `-simple`) is not part of the version. Versions compare as release
numbers, so `1.1` and `1.1.0` are the same version and `2.0.0-alpha.15` is
`2.0.0a15`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# An app name followed by "-", or "v", "v-": everything before the first digit.
TAG_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9_.]*?-)?(?:v-?)?(?P<version>\d[^\s]*)$")
IMAGE_SUFFIX_RE = re.compile(r"-(?:full|simple)$")
PRE_RE = re.compile(r"^[-._]?(a|alpha|b|beta|rc|c|pre|preview)[-._]?(\d*)$", re.I)
PRE_ORDER = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}


def version_from_tag(tag: str) -> str:
    """The version a release tag stands for (ValueError when it has none)."""
    tag = tag.strip()
    if tag.startswith("refs/tags/"):
        tag = tag[len("refs/tags/"):]
    m = TAG_RE.match(IMAGE_SUFFIX_RE.sub("", tag))
    if not m:
        raise ValueError(f"release tag {tag!r} holds no version")
    return m.group("version")


def version_key(version: str):
    """A sortable key: release numbers without trailing zeros, then the pre-release."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)(.*)$", version.strip())
    if not m:
        return ((), (9, 0), version)
    release = [int(x) for x in m.group(1).split(".")]
    while len(release) > 1 and release[-1] == 0:
        release.pop()
    rest = m.group(2)
    if not rest:
        pre = (9, 0)  # a final release sorts after its pre-releases
    else:
        p = PRE_RE.match(rest)
        pre = (PRE_ORDER[p.group(1).lower()], int(p.group(2) or 0)) if p else (8, rest)
    return (tuple(release), pre, "")


def same_version(a: str, b: str) -> bool:
    return version_key(a) == version_key(b)


def read_version(settings: Path) -> str:
    return str(json.loads(settings.read_text(encoding="utf-8")).get("version", ""))


def write_version(settings: Path, version: str) -> None:
    """Replace the value of the top-level "version" in place, keeping the layout."""
    text = settings.read_text(encoding="utf-8")
    data = json.loads(text)
    new = None
    # The first "version" line may belong to a nested object: take the first
    # one whose replacement sets the top-level value and leaves the rest.
    for m in re.finditer(r'^(\s*"version"\s*:\s*)"[^"]*"', text, flags=re.M):
        candidate = text[:m.start()] + m.group(1) + json.dumps(version) + text[m.end():]
        expected = dict(data, version=version)
        if json.loads(candidate) == expected:
            new = candidate
            break
    if new is None:
        data["version"] = version
        new = json.dumps(data, indent=4, ensure_ascii=False) + "\n"
    settings.write_text(new, encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("version", "set", "check"):
        print(__doc__, file=sys.stderr)
        return 2
    command, tag = argv[0], argv[1]
    settings = Path(argv[2] if len(argv) > 2 else "settings.json")
    try:
        version = version_from_tag(tag)
    except ValueError as e:
        print(f"::error::{e}")
        return 1
    if command == "version":
        print(version)
        return 0
    if command == "set":
        write_version(settings, version)
        print(f"{settings}: version {version} (from tag {tag})")
        return 0
    if not settings.is_file():
        print(f"::error::{settings} not found, so the version of {tag} cannot be checked")
        return 1
    current = read_version(settings)
    if same_version(current, version):
        print(f"{settings} says {current}, as tag {tag} does.")
        return 0
    print(
        f"::error file={settings}::Release {tag} is version {version}, "
        f"but {settings} says {current!r}. Bump the version in a PR and merge "
        f"it before the release is created."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
