"""The Streamlit launcher preloads heavy libraries on the main thread."""

import importlib.util
import sys
import threading
import types
from pathlib import Path

from src import streamlit_launcher


def test_preload_imports_on_the_calling_thread(monkeypatch):
    seen = []
    module = types.ModuleType("fake_preloaded")
    monkeypatch.setitem(sys.modules, "fake_preloaded", module)
    real_import = streamlit_launcher.importlib.import_module

    def spy(name):
        seen.append((name, threading.current_thread() is threading.main_thread()))
        return real_import(name)

    monkeypatch.setattr(streamlit_launcher.importlib, "import_module", spy)
    assert streamlit_launcher.preload(("fake_preloaded",)) == ["fake_preloaded"]
    assert seen == [("fake_preloaded", True)]


def test_preload_skips_missing_modules():
    assert streamlit_launcher.preload(("no_such_module_xyz",)) == []


def test_main_preloads_then_runs_streamlit(monkeypatch):
    order = []
    monkeypatch.setattr(streamlit_launcher, "preload", lambda: order.append("preload"))
    from streamlit.web import cli

    def fake_main():
        order.append(("streamlit", list(sys.argv)))
        return 0

    monkeypatch.setattr(cli, "main", fake_main)
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    assert streamlit_launcher.main(["run", "app.py", "local"]) == 0
    assert order == ["preload", ("streamlit", ["streamlit", "run", "app.py", "local"])]


def test_settings_preload_reads_the_list(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"preload": ["scipy.stats", "", 3, "sklearn"]}')
    assert streamlit_launcher.settings_preload(path) == ["scipy.stats", "sklearn"]


def test_settings_preload_ignores_a_bad_file(tmp_path):
    assert streamlit_launcher.settings_preload(tmp_path / "missing.json") == []
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert streamlit_launcher.settings_preload(path) == []
    path.write_text('{"preload": "scipy"}')
    assert streamlit_launcher.settings_preload(path) == []


def test_preload_modules_keeps_polars_first_and_each_once(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"preload": ["pandas", "scipy.stats", "scipy.stats"]}')
    modules = streamlit_launcher.preload_modules(path)
    assert modules[0] == "polars"
    assert modules[: len(streamlit_launcher.DEFAULT_PRELOAD)] == streamlit_launcher.DEFAULT_PRELOAD
    assert modules.count("pandas") == 1
    assert modules[-1] == "scipy.stats" and modules.count("scipy.stats") == 1


def test_preload_skips_a_module_that_fails_to_import(monkeypatch):
    real_import = streamlit_launcher.importlib.import_module

    def failing(name):
        if name == "broken_module":
            raise RuntimeError("boom")
        return real_import(name)

    monkeypatch.setattr(streamlit_launcher.importlib, "import_module", failing)
    lines = []
    loaded = streamlit_launcher.preload(("broken_module", "json"), log=lines.append)
    assert loaded == ["json"]
    assert any("broken_module failed to import" in line for line in lines)


def test_every_preload_in_settings_is_installed():
    """A module named in settings.json must be importable, or it is a typo."""
    for name in streamlit_launcher.settings_preload("settings.json"):
        assert importlib.util.find_spec(name) is not None, name


def test_containers_start_streamlit_through_the_launcher():
    for path in ("docker/entrypoint.sh", "k8s/base/streamlit-deployment.yaml"):
        text = Path(path).read_text(encoding="utf-8")
        assert "python -m src.streamlit_launcher run app.py" in text, path
        assert "exec streamlit run" not in text, path
