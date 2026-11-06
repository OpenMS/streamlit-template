"""What the app ships besides its own code, and under which licenses.

Read by the About dialog (src/common/about.py): the app's own license, the
third-party programs that come with OpenMS (the THIRDPARTY folders the desktop
apps and the full Docker image put on PATH), and the installed Python packages
with their license texts. Thermo's RawFileReader (in the ThermoRawFileParser
folder FileConverter runs for .raw files) requires its copyright notice in the
About box, so ``thermo_notice()`` says whether to show it.

Streamlit-free, so it can be tested on its own.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import metadata
from pathlib import Path

THERMO_FOLDER = "ThermoRawFileParser"
THERMO_NOTICE = (
    "RawFileReader reading tool. Copyright © 2016 by Thermo Fisher Scientific, Inc. "
    "All rights reserved."
)

APP_LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt")
_LICENSE_FILE = re.compile(r"(licen[cs]e|copying|notice|copyright|authors)", re.IGNORECASE)
_LICENSE_EXT = {"", ".txt", ".md", ".rst", ".html", ".htm"}


@dataclass
class Component:
    """A program or package the app ships, with the files holding its terms."""

    name: str
    version: str = ""
    license: str = ""
    files: list[Path] = field(default_factory=list)


def app_license(root: Path | str = ".") -> str:
    """The app's own license text, or "" when the app has no LICENSE file."""
    for name in APP_LICENSE_NAMES:
        path = Path(root, name)
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _is_license_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _LICENSE_EXT and bool(_LICENSE_FILE.search(path.name))


def tool_folders(env: dict | None = None) -> list[Path]:
    """Folders of the third-party programs that come with the app.

    The desktop apps keep them in ``<OPENMS_DATA_PATH>/THIRDPARTY/<tool>``, the
    full Docker image in ``/thirdparty/<tool>``; both put every folder on PATH.
    """
    env = os.environ if env is None else env
    found: dict[str, Path] = {}
    candidates: list[Path] = []
    data_path = env.get("OPENMS_DATA_PATH")
    if data_path and Path(data_path, "THIRDPARTY").is_dir():
        candidates += sorted(p for p in Path(data_path, "THIRDPARTY").iterdir() if p.is_dir())
    for entry in env.get("PATH", "").split(os.pathsep):
        if entry and Path(entry).parent.name.lower() == "thirdparty" and Path(entry).is_dir():
            candidates.append(Path(entry))
    for folder in candidates:
        found.setdefault(str(folder.resolve()), folder)
    return sorted(found.values(), key=lambda p: p.name.lower())


def third_party_programs(env: dict | None = None) -> list[Component]:
    """The third-party programs and the license files in their folders."""
    programs = []
    for folder in tool_folders(env):
        files = [p for p in sorted(folder.iterdir()) if _is_license_file(p)]
        programs.append(Component(name=folder.name, files=files))
    return programs


FONTS = (
    ("Raleway", "raleway"),
    ("Montserrat Alternates", "montserrat-alternates"),
    ("JetBrains Mono", "jetbrains-mono"),
)


def fonts(root: Path | str = ".") -> list[Component]:
    """The typefaces the app serves from ``static/fonts``, with their licenses."""
    found = []
    for name, slug in FONTS:
        path = Path(root, "static", "fonts", f"LICENSE-{slug}.txt")
        if path.is_file():
            found.append(Component(name=name, license="OFL-1.1", files=[path]))
    return found


def thermo_notice(env: dict | None = None) -> str:
    """Thermo's notice when the app ships RawFileReader, else ""."""
    shipped = any(p.name == THERMO_FOLDER for p in tool_folders(env))
    return THERMO_NOTICE if shipped else ""


def _package_license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::") and c.strip() != "License :: OSI Approved"
    ]
    if classifiers:
        return "; ".join(dict.fromkeys(classifiers))
    text = (meta.get("License") or "").strip()
    # Some packages put the whole license text in this field.
    if text and "\n" not in text and len(text) <= 60:
        return text
    return "see license text" if text else ""


def _package_files(dist: metadata.Distribution) -> list[Path]:
    """License files in the package's .dist-info folder; when it has none,
    license files at the top of the package's own folders."""
    meta_files, other_files = [], []
    for f in dist.files or []:
        parts = Path(str(f)).parts
        if not _LICENSE_FILE.search(parts[-1]) and "licenses" not in parts:
            continue
        if parts[0].endswith((".dist-info", ".egg-info")):
            meta_files.append(f)
        elif len(parts) <= 2:
            other_files.append(f)
    paths = [Path(dist.locate_file(f)) for f in meta_files or other_files]
    return [p for p in paths if _is_license_file(p)]


@lru_cache(maxsize=1)
def python_packages() -> tuple[Component, ...]:
    """The installed Python packages with their license and license files."""
    packages: dict[str, Component] = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if not name or name.lower() in packages:
            continue
        packages[name.lower()] = Component(
            name=name,
            version=dist.version or "",
            license=_package_license(dist),
            files=_package_files(dist),
        )
    return tuple(sorted(packages.values(), key=lambda c: c.name.lower()))


def license_text(component: Component) -> str:
    """The texts of a component's license files, one after another."""
    parts = []
    for path in component.files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        parts.append(f"==> {path.name} <==\n{text}" if len(component.files) > 1 else text)
    return "\n\n".join(parts)
