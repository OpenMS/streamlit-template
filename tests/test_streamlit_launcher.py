"""The desktop app's Streamlit launcher imports polars on the main thread."""

import sys
import threading
import types

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
