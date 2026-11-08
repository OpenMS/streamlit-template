"""The listing behind the About dialog: app license, bundled programs, packages."""

import os
import platform
from pathlib import Path

from src.common import third_party


def _tool(root: Path, name: str, *files: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    for f in files:
        (folder / f).write_text(f"text of {f}")
    return folder


def test_app_license_reads_the_first_license_file(tmp_path):
    assert third_party.app_license(tmp_path) == ""
    (tmp_path / "LICENSE.md").write_text("  BSD 3-Clause\n")
    assert third_party.app_license(tmp_path) == "BSD 3-Clause"


def test_tools_under_openms_data_path_and_on_path(tmp_path):
    data = tmp_path / "share" / "OpenMS"
    _tool(data / "THIRDPARTY", "Comet", "LICENSE.txt", "comet.exe")
    docker = tmp_path / "thirdparty"
    _tool(docker, "Sage", "LICENSE", "sage")
    other = _tool(tmp_path / "bin", "notatool")
    env = {"OPENMS_DATA_PATH": str(data), "PATH": os.pathsep.join([str(docker / "Sage"), str(other)])}

    programs = third_party.third_party_programs(env)
    assert [p.name for p in programs] == ["Comet", "Sage"]
    assert [f.name for f in programs[0].files] == ["LICENSE.txt"]
    assert third_party.license_text(programs[1]) == "text of LICENSE"


def test_a_folder_on_path_and_in_the_data_path_is_listed_once(tmp_path):
    data = tmp_path / "share" / "OpenMS"
    comet = _tool(data / "THIRDPARTY", "Comet", "LICENSE")
    env = {"OPENMS_DATA_PATH": str(data), "PATH": str(comet)}
    assert [p.name for p in third_party.third_party_programs(env)] == ["Comet"]


def test_thermo_notice_only_when_rawfilereader_is_shipped(tmp_path):
    data = tmp_path / "share" / "OpenMS"
    _tool(data / "THIRDPARTY", "Comet", "LICENSE")
    env = {"OPENMS_DATA_PATH": str(data), "PATH": ""}
    assert third_party.thermo_notice(env) == ""
    _tool(data / "THIRDPARTY", "ThermoRawFileParser", "THERMO_LICENSE", "LICENSE")
    assert third_party.thermo_notice(env) == third_party.THERMO_NOTICE
    thermo = [p for p in third_party.third_party_programs(env) if p.name == "ThermoRawFileParser"][0]
    assert sorted(f.name for f in thermo.files) == ["LICENSE", "THERMO_LICENSE"]


def test_no_tools_without_data_path_or_path():
    assert third_party.third_party_programs({}) == []
    assert third_party.thermo_notice({}) == ""


def test_python_interpreter_has_its_version_and_license():
    python = third_party.python_interpreter()
    assert python.name == "Python" and python.license == "PSF-2.0"
    assert python.version == platform.python_version()
    assert third_party.libraries({})[0] == python


def test_qt_is_found_in_the_desktop_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(third_party, "_system_qt_dirs", lambda: [])
    data = tmp_path / "share" / "OpenMS"
    data.mkdir(parents=True)
    env = {"OPENMS_DATA_PATH": str(data), "PATH": ""}
    assert third_party.qt_library(env) is None
    (tmp_path / "openms" / "bin").mkdir(parents=True)
    (tmp_path / "openms" / "bin" / "Qt6Core.dll").write_text("")
    qt = third_party.qt_library(env)
    assert (qt.name, qt.version, qt.license) == ("Qt", "6.x", "LGPL-3.0-only")
    assert [f.name for f in qt.files] == ["LGPL-3.0.txt", "GPL-3.0.txt"]
    assert "LESSER GENERAL PUBLIC LICENSE" in third_party.license_text(qt)
    assert [c.name for c in third_party.libraries(env)] == ["Python", "Qt"]


def test_qt_in_a_linux_lib_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(third_party, "_system_qt_dirs", lambda: [tmp_path])
    (tmp_path / "libQt6Core.so.6").write_text("")
    assert third_party.qt_library({}).version == "6.x"


def test_qt_dylib_on_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(third_party, "_system_qt_dirs", lambda: [])
    data = tmp_path / "share" / "OpenMS"
    data.mkdir(parents=True)
    (tmp_path / "openms" / "lib").mkdir(parents=True)
    (tmp_path / "openms" / "lib" / "libQt6Core.6.dylib").write_text("")
    assert third_party.qt_library({"OPENMS_DATA_PATH": str(data)}).version == "6.x"


def test_installed_packages_have_names_and_licenses():
    packages = {p.name.lower(): p for p in third_party.python_packages()}
    assert "pytest" in packages
    pytest_pkg = packages["pytest"]
    assert pytest_pkg.version
    assert "MIT" in pytest_pkg.license
    assert pytest_pkg.files and "MIT" in third_party.license_text(pytest_pkg)
