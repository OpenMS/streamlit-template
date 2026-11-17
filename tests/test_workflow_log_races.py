"""Concurrent log creation, rotation and parameter import keep the UI usable."""

import builtins
import importlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.workflow.Logger import Logger
from src.workflow.StreamlitUI import _read_workflow_log


def test_simultaneous_first_log_writes_keep_both_messages(tmp_path, monkeypatch):
    folder = tmp_path / "workflow" / "logs"
    folder.parent.mkdir()
    barrier = threading.Barrier(2)
    mkdir = Path.mkdir

    def together(path, *args, **kwargs):
        if path == folder:
            barrier.wait(timeout=5)
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", together)
    logger = Logger(folder.parent)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(logger.log, f"native message {number}") for number in range(2)]
        for future in futures:
            future.result(timeout=5)
    for name in ("minimal.log", "commands-and-run-times.log", "all.log"):
        text = (folder / name).read_text()
        assert text.count("native message 0") == text.count("native message 1") == 1


def test_logger_retains_real_storage_errors(tmp_path, monkeypatch):
    mkdir = Path.mkdir

    def denied(path, *args, **kwargs):
        if path == tmp_path / "logs":
            raise PermissionError("storage is read-only")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(PermissionError, match="read-only"):
        Logger(tmp_path).log("native evidence")


def test_log_snapshot_tolerates_disappearance_before_open(tmp_path, monkeypatch):
    path = tmp_path / "minimal.log"
    path.write_text("WORKFLOW FINISHED\n")
    opening = builtins.open

    def removed(file, *args, **kwargs):
        if Path(file) == path:
            path.unlink()
        return opening(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", removed)
    assert _read_workflow_log(path) is None


def test_log_snapshot_uses_the_open_files_metadata_when_path_rotates(tmp_path, monkeypatch):
    path = tmp_path / "minimal.log"
    previous = tmp_path / "previous.log"
    previous.write_text("WORKFLOW CANCELLED\n")
    path.write_text("STARTING WORKFLOW\n")
    opening = builtins.open
    stat = Path.stat

    def rotated(file, *args, **kwargs):
        # The caller opened the old file just before the named path changed.
        return opening(previous if Path(file) == path else file, *args, **kwargs)

    def unavailable(path_value, *args, **kwargs):
        if path_value == path:
            raise FileNotFoundError("log was rotated")
        return stat(path_value, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", rotated)
    monkeypatch.setattr(Path, "stat", unavailable)
    created, lines = _read_workflow_log(path)
    assert created == previous.stat().st_ctime
    assert lines == ["WORKFLOW CANCELLED\n"]


EXECUTION = """
from pathlib import Path
from types import SimpleNamespace
import streamlit as st
from src.workflow.StreamlitUI import StreamlitUI
ui = object.__new__(StreamlitUI)
ui.workflow_dir = Path(st.session_state.folder)
ui.executor = SimpleNamespace(pid_dir=ui.workflow_dir / 'pids')
ui.export_parameters_markdown = lambda: 'Saved scientific settings'
ui.execution_section(lambda: None, get_status_function=lambda: {'running': st.session_state.running})
"""


@pytest.mark.parametrize("running", [False, True])
@pytest.mark.parametrize("error", [FileNotFoundError("rotated"), PermissionError("permission denied"), UnicodeError("invalid text")])
def test_execution_poll_recovers_from_changed_or_unreadable_log(tmp_path, monkeypatch, running, error):
    module = importlib.import_module("src.workflow.StreamlitUI")
    monkeypatch.setattr(module, "_read_workflow_log", lambda _path: (_ for _ in ()).throw(error) if not isinstance(error, FileNotFoundError) else None)
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 0, sleep=lambda _seconds: None))
    monkeypatch.setattr(st, "rerun", lambda: None)
    app = AppTest.from_string(EXECUTION)
    app.session_state.folder, app.session_state.running = str(tmp_path), running
    app.run(timeout=30)
    assert not app.exception
    assert not app.error
    assert not app.success
    if not isinstance(error, FileNotFoundError):
        assert any("temporarily unavailable" in message.value for message in app.info)
    assert any(button.label == ("Stop Workflow" if running else "Start Workflow") for button in app.button)


@pytest.mark.parametrize("marker,kind", [("WORKFLOW FINISHED", "success"), ("WORKFLOW CANCELLED", "warning"), ("ERROR: Native failure", "error")])
def test_log_snapshot_keeps_terminal_classification(tmp_path, marker, kind):
    Logger(tmp_path).log(marker)
    app = AppTest.from_string(EXECUTION)
    app.session_state.folder, app.session_state.running = str(tmp_path), False
    app.run(timeout=30)
    assert not app.exception
    assert len(getattr(app, kind)) == 1


IMPORT = """
from pathlib import Path
import streamlit as st
from src.workflow.ParameterManager import ParameterManager
from src.workflow.StreamlitUI import StreamlitUI
manager = ParameterManager(Path(st.session_state.folder))
ui = object.__new__(StreamlitUI)
ui.workflow_dir, ui.parameter_manager = Path(st.session_state.folder), manager
ui.preset_buttons = lambda: None
ui.user_presets = lambda: None
ui.export_parameters_markdown = lambda: 'Saved scientific settings'
ui.parameter_section(lambda: st.text_input('Science setting', key=manager.param_prefix + 'modification'))
"""


def import_app(tmp_path, monkeypatch, payload):
    # AppTest cannot upload a file: supply only that frontend value while the
    # real uploader, parameter section, parser and atomic writer still run.
    uploader = st.file_uploader
    keys = []

    def uploaded(label, *args, **kwargs):
        result = uploader(label, *args, **kwargs)
        if label == "⬆️ Import parameters":
            keys.append(kwargs["key"])
            if kwargs["key"].endswith("-0"):
                return BytesIO(payload)
        return result

    monkeypatch.setattr(st, "file_uploader", uploaded)
    path = tmp_path / "params.json"
    path.write_text(json.dumps({"modification": "m5C", "enable-lfq": False}))
    app = AppTest.from_string(IMPORT)
    app.session_state.folder = str(tmp_path)
    app.session_state.settings = {"online_deployment": True}
    app.session_state[f"{tmp_path.stem}-param-modification"] = "m5C"
    return app, path, keys


@pytest.mark.parametrize("payload", [b'{"incomplete":', b'[]', b'null', b'"string"', b'\xff'])
def test_invalid_import_keeps_scientific_file_and_widget_state(tmp_path, monkeypatch, payload):
    app, path, keys = import_app(tmp_path, monkeypatch, payload)
    original = path.read_bytes()
    app.run(timeout=30)
    assert not app.exception
    assert any("Could not import parameters" in message.value for message in app.error)
    assert path.read_bytes() == original
    assert app.text_input[0].value == "m5C"
    assert len(keys) == 1


def test_import_publishes_complete_json_once_and_resets_upload(tmp_path, monkeypatch):
    expected = {"modification": "Am", "enable-lfq": True, "_defaults": {"NASE": {"setting": [1, 2]}}}
    app, path, keys = import_app(tmp_path, monkeypatch, json.dumps(expected).encode())
    old = json.loads(path.read_text())
    replacing = os.replace
    observed = []

    def inspect_before_publish(source, destination):
        if Path(destination) == path:
            observed.append(json.loads(path.read_text()))
            assert json.loads(Path(source).read_text()) == expected
        return replacing(source, destination)

    monkeypatch.setattr(os, "replace", inspect_before_publish)
    app.run(timeout=30)
    assert not app.exception
    assert not app.error
    assert observed == [old]
    assert json.loads(path.read_text()) == expected
    assert len(keys) == 2 and keys[0] != keys[1]
    app.run(timeout=30)
    assert observed == [old]
    assert json.loads(path.read_text()) == expected


def test_failed_import_replace_keeps_current_settings_and_upload(tmp_path, monkeypatch):
    app, path, keys = import_app(tmp_path, monkeypatch, b'{"modification":"Am"}')
    original = path.read_bytes()
    replacing = os.replace

    def unavailable(source, destination):
        if Path(destination) == path:
            raise PermissionError("file is temporarily locked")
        return replacing(source, destination)

    monkeypatch.setattr(os, "replace", unavailable)
    app.run(timeout=30)
    assert not app.exception
    assert any("temporarily locked" in message.value for message in app.error)
    assert path.read_bytes() == original
    assert app.text_input[0].value == "m5C"
    assert len(keys) == 1
    assert not list(tmp_path.glob(".params.json.*.tmp"))
