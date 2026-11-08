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
import platform
import plistlib
import re
import sys
import sysconfig
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


LICENSES_DIR = Path(__file__).resolve().parents[2] / "static" / "licenses"

# Qt's core library as OpenMS ships it: in the desktop payload (openms/bin on
# Windows, openms/lib elsewhere, a dylib or framework on macOS), bundled into
# the pyOpenMS wheel, or from the system's packages in the full Docker image.
_QT_CORE = ("Qt6Core*.dll", "Qt5Core*.dll", "libQt6Core.so*", "libQt5Core.so*",
            "libQt6Core-*.so*", "libQt5Core-*.so*", "libQt6Core*.dylib",
            "libQt5Core*.dylib", "QtCore.framework")
_QT_MAJOR = re.compile(r"Qt([56])Core")


def _system_qt_dirs() -> list[Path]:
    """Where pyOpenMS and the system keep Qt: the wheel's own folders, the
    environment's lib/ and the system's library folder."""
    dirs: list[Path] = []
    try:
        package = Path(metadata.distribution("pyopenms").locate_file("pyopenms"))
        dirs += [package, package.parent / "pyopenms.libs", package / ".dylibs"]
    except metadata.PackageNotFoundError:
        pass
    multiarch = sysconfig.get_config_var("MULTIARCH") or ""
    return dirs + [Path(sys.prefix, "lib"), Path("/usr/lib", multiarch)]


def _qt_dirs(env: dict) -> list[Path]:
    """Folders next to the OpenMS installation that OPENMS_DATA_PATH names:
    an OpenMS install (bin, lib, Frameworks) or the desktop payload, which
    keeps share/OpenMS beside openms/bin and openms/lib."""
    dirs: list[Path] = []
    data_path = env.get("OPENMS_DATA_PATH")
    if data_path:
        root = Path(data_path).parent.parent
        dirs += [root / "bin", root / "lib", root / "Frameworks"]
        dirs += [root / "openms" / "bin", root / "openms" / "lib"]
    return dirs + _system_qt_dirs()


def _framework_major(framework: Path) -> str:
    """The Qt major of a QtCore.framework, from its Info.plist or Versions/<n>."""
    for plist in (framework / "Resources" / "Info.plist",
                  *sorted(framework.glob("Versions/*/Resources/Info.plist"))):
        try:
            with plist.open("rb") as handle:
                info = plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException, ValueError):
            continue
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            major = str(info.get(key, "")).split(".")[0]
            if major in ("5", "6"):
                return major
    for version in sorted(framework.glob("Versions/[56]")):
        return version.name
    return ""


def _qt_major(hit: Path) -> str | None:
    """The Qt major of a core library match; None when it is no Qt library
    (a framework folder without its QtCore binary)."""
    if hit.name == "QtCore.framework":
        binaries = [hit / "QtCore", *hit.glob("Versions/*/QtCore")]
        if not any(p.exists() for p in binaries):
            return None
        return _framework_major(hit)
    match = _QT_MAJOR.search(hit.name)
    return match.group(1) if match else ""


def qt_libraries(env: dict | None = None) -> list[Component]:
    """Qt, which OpenMS and pyOpenMS link as a shared library, once per Qt
    major found (an OpenMS install and a pyOpenMS wheel may bring different
    ones), in search order."""
    env = os.environ if env is None else env
    majors: list[str] = []
    for folder in _qt_dirs(env):
        if not folder.is_dir():
            continue
        for pattern in _QT_CORE:
            for hit in sorted(folder.glob(pattern)):
                major = _qt_major(hit)
                if major is not None and major not in majors:
                    majors.append(major)
    # An unknown major says no more than a known one.
    if len(majors) > 1:
        majors = [m for m in majors if m]
    files = [LICENSES_DIR / name for name in ("LGPL-3.0.txt", "GPL-3.0.txt")]
    files = [f for f in files if f.is_file()]
    return [Component(name="Qt", version=f"{m}.x" if m else "", license="LGPL-3.0-only",
                      files=list(files)) for m in majors]


def qt_library(env: dict | None = None) -> Component | None:
    """The first Qt that ``qt_libraries`` finds, or None."""
    found = qt_libraries(env)
    return found[0] if found else None


def python_interpreter() -> Component:
    """The Python interpreter the app runs on, with the PSF license it ships."""
    candidates = [Path(sysconfig.get_paths()["stdlib"], "LICENSE.txt"), Path(sys.base_prefix, "LICENSE.txt")]
    files = [p for p in candidates if p.is_file()][:1]
    return Component(name="Python", version=platform.python_version(), license="PSF-2.0", files=files)


def libraries(env: dict | None = None) -> list[Component]:
    """The runtime the app is built on: Python and, with OpenMS, Qt."""
    return [python_interpreter()] + qt_libraries(env)


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
