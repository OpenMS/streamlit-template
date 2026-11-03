#!/usr/bin/env python3
"""Move a repository that follows the OpenMS releases to the newest one.

Used by .github/workflows/openms-release.yml, in the template and in every app
made from it. Standard library only.

A repository *follows the releases* when the OpenMS its full Dockerfile builds
(`ARG OPENMS_BRANCH=` in Dockerfile) is the release just before the newest one.
Such a repository is moved to the newest release. One on an older release, on
develop, or on a branch of a fork has chosen that OpenMS and is left alone.

    python .github/scripts/openms_release.py [--continue] [--workflows]

--continue   the upgrade branch already exists: keep following even though the
             repository may now be two releases behind (an upgrade PR that was
             still open when another release came out).
--workflows  also edit files under .github/workflows/ (the token can push them).

Edits, each only where the old release is written:
  Dockerfile*                     ARG OPENMS_BRANCH=<old ref>  ->  <new ref>
  requirements.txt                pyopenms==<old>              ->  <new>, if on PyPI
  .github/workflows/build-desktop-app.yaml
                                  the default `openms` release ('3.5.0')
  .github/workflows/*.yml         python-version below pyOpenMS's Requires-Python

Writes `key=value` lines to $GITHUB_OUTPUT (or stdout): status (no-release,
up-to-date, not-following, upgraded), old, new, ref, notes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

OPENMS_REPO = "https://github.com/OpenMS/OpenMS"
# release/3.5.0, v3.6.0, Release3.0.0, 3.6.0. No suffix: a pre-release such as
# v3.7.0-rc1 or release/3.7.0-beta is not a release.
RELEASE_RE = re.compile(r"^(?:release/|Release|v)?(\d+)\.(\d+)\.(\d+)$")
ARG_RE = re.compile(r"^(ARG OPENMS_BRANCH=)(\S+)\s*$", re.M)


def parse(ref: str):
    m = RELEASE_RE.match(ref.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def fmt(v) -> str:
    return ".".join(map(str, v))


def release_tags() -> dict:
    """{version: tag name} of every OpenMS release tag."""
    out = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", OPENMS_REPO],
        check=True, capture_output=True, text=True,
    ).stdout
    tags = {}
    for line in out.splitlines():
        name = line.split("refs/tags/", 1)[-1]
        v = parse(name)
        # Prefer the v-tag where both spellings exist (that is what 3.6 uses).
        if v and (v not in tags or name.startswith("v")):
            tags[v] = name
    return tags


def pypi_release(version: str):
    """(has files, minimum Python) of pyopenms <version> on PyPI, or None."""
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/pyopenms/{version}/json", timeout=30) as r:
            data = json.load(r)
    except Exception:  # not published (404) or PyPI unreachable
        return None
    if not data.get("urls"):
        return None
    m = re.search(r">=\s*(\d+)\.(\d+)", data["info"].get("requires_python") or "")
    return (int(m.group(1)), int(m.group(2))) if m else None, True


def ref_like(old_ref: str, tag: str, new) -> str:
    """The new release written the way the repository wrote the old one."""
    if old_ref.startswith("release/"):
        return f"release/{fmt(new)}" if tag.startswith("release/") else tag
    return tag


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--continue", dest="cont", action="store_true")
    ap.add_argument("--workflows", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(args.root)

    out = {}

    def done(status, **kw):
        out.update(status=status, **kw)
        lines = [f"{k}={v}" for k, v in out.items()]
        target = os.environ.get("GITHUB_OUTPUT")
        if target:
            with open(target, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        print("\n".join(lines))
        return 0

    dockerfile = root / "Dockerfile"
    m = ARG_RE.search(dockerfile.read_text()) if dockerfile.is_file() else None
    if not m:
        return done("no-release", notes="Dockerfile has no ARG OPENMS_BRANCH")
    old_ref = m.group(2)
    old = parse(old_ref)
    if not old:
        return done("not-following", old=old_ref, notes=f"builds {old_ref}, not a release")

    tags = release_tags()
    newest = max(tags)
    if old >= newest:
        return done("up-to-date", old=old_ref)
    previous = max((v for v in tags if v < newest), default=None)
    if old != previous and not args.cont:
        return done("not-following", old=old_ref,
                    notes=f"on {fmt(old)}, two or more releases behind {fmt(newest)}")

    new_ref = ref_like(old_ref, tags[newest], newest)
    notes = []

    # Dockerfiles: only those that build the same release as Dockerfile
    # (Dockerfile_simple builds develop for its TOPP tools and stays).
    for f in sorted(root.glob("Dockerfile*")):
        text = f.read_text()
        new_text = ARG_RE.sub(lambda mm: mm.group(1) + new_ref if mm.group(2) == old_ref else mm.group(0), text)
        if new_text != text:
            f.write_text(new_text)
            notes.append(f"{f.name}: OPENMS_BRANCH {old_ref} -> {new_ref}")

    # pyOpenMS from PyPI (Dockerfile_simple, local installs, CI).
    min_python = None
    req = root / "requirements.txt"
    if req.is_file():
        text = req.read_text()
        pin = re.search(r"^pyopenms==(\S+)\s*$", text, re.M)
        if pin and parse(pin.group(1)) == old:
            pypi = pypi_release(fmt(newest))
            if pypi:
                min_python = pypi[0]
                req.write_text(text[:pin.start(1)] + fmt(newest) + text[pin.end(1):])
                notes.append(f"requirements.txt: pyopenms {pin.group(1)} -> {fmt(newest)}")
            else:
                notes.append(f"requirements.txt: pyopenms {fmt(newest)} is not on PyPI yet, pin left at {pin.group(1)}")

    wf = root / ".github" / "workflows"
    if args.workflows and wf.is_dir():
        desktop = wf / "build-desktop-app.yaml"
        if desktop.is_file():
            text = desktop.read_text()
            new_text = text.replace(f"inputs.openms || '{fmt(old)}'", f"inputs.openms || '{fmt(newest)}'")
            if new_text != text:
                desktop.write_text(new_text)
                notes.append(f"build-desktop-app.yaml: desktop OpenMS {fmt(old)} -> {fmt(newest)}")
        if min_python:
            low = re.compile(r'(python-version:\s*\[?\s*")(\d+)\.(\d+)(")')
            want = f"{min_python[0]}.{min_python[1]}"
            for f in sorted(list(wf.glob("*.yml")) + list(wf.glob("*.yaml"))):
                text = f.read_text()
                new_text = low.sub(
                    lambda mm: mm.group(1) + want + mm.group(4)
                    if (int(mm.group(2)), int(mm.group(3))) < min_python else mm.group(0),
                    text)
                if new_text != text:
                    f.write_text(new_text)
                    notes.append(f"{f.name}: python-version raised to {want} (pyOpenMS {fmt(newest)} requires it)")
    elif wf.is_dir():
        notes.append("workflow files not edited: the token cannot push changes to .github/workflows/")

    return done("upgraded", old=old_ref, new=fmt(newest), ref=new_ref, notes=" | ".join(notes))


if __name__ == "__main__":
    sys.exit(main())
