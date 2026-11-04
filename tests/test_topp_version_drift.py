"""
A TOPP tool upgraded underneath stored workflow state.

Reported from a deployment after a release: the web pods ran the new image, the
rq-worker pods still the old one. The page wrote ``ini/<Tool>.ini`` and
``params.json`` for the new TOPP tool, the old worker ran its old tool with
them, and the tool aborted with "Parameters passed to 'FLASHDeconv' are
invalid" (exit code 6). Three guards, one per way the versions drift apart:

  - the worker refuses a job queued by a page that runs other code
    (``src/workflow/app_build.py``, ``tasks.execute_workflow``);
  - a cached .ini older than the tool executable is written again
    (``ParameterManager.create_ini``), since workspaces outlive images;
  - ``run_topp`` leaves out a stored parameter the installed tool does not have.
"""
import json
import os
import stat
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Same import dance as tests/test_topp_flag_parameters.py: streamlit and
# pyopenms mocked while the modules under test are imported, then restored.
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_original_streamlit = sys.modules.get("streamlit")
_original_pyopenms = sys.modules.get("pyopenms")
sys.modules["streamlit"] = mock_streamlit
if _original_pyopenms is None:
    sys.modules["pyopenms"] = MagicMock()

from src.workflow.ParameterManager import (  # noqa: E402
    INI_TOOL_MISSING,
    ParameterManager,
    param_paths_from_param_xml_ini,
    bool_param_paths_from_param_xml_ini,
)
from src.workflow.CommandExecutor import CommandExecutor  # noqa: E402
from src.workflow import app_build  # noqa: E402

if _original_streamlit is not None:
    sys.modules["streamlit"] = _original_streamlit
else:
    sys.modules.pop("streamlit", None)
if _original_pyopenms is None:
    sys.modules.pop("pyopenms", None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


TOOL = "FakeDeconv"


def ini_xml(tool: str, items: dict) -> str:
    """A minimal ParamXML file with ``items`` ({path: type}) under Tool:1."""

    def nodes(prefix_items):
        out = []
        sections = {}
        for path, typ in prefix_items.items():
            head, _, rest = path.partition(":")
            if rest:
                sections.setdefault(head, {})[rest] = typ
            elif typ == "stringlist":
                out.append(f'<ITEMLIST name="{head}" type="string"></ITEMLIST>')
            else:
                value = "false" if typ == "bool" else "1"
                out.append(f'<ITEM name="{head}" value="{value}" type="{typ}"/>')
        for name, sub in sections.items():
            out.append(f'<NODE name="{name}">{"".join(nodes(sub))}</NODE>')
        return out

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<PARAMETERS version="1.7.0">'
        f'<NODE name="{tool}"><ITEM name="version" value="1" type="string"/>'
        f'<NODE name="1">{"".join(nodes(items))}</NODE></NODE></PARAMETERS>'
    )


OLD_ITEMS = {"ida_log": "string", "max_charge": "int", "write_detail": "bool"}
NEW_ITEMS = {
    "max_charge": "int",
    "write_detail": "bool",
    "scan_commands": "string",
    "SD:tol": "stringlist",
}


@pytest.fixture(autouse=True)
def reset_session_state():
    mock_streamlit.session_state = {}
    yield
    mock_streamlit.session_state = {}


@pytest.fixture
def fake_tool(tmp_path, monkeypatch):
    """Put an executable ``FakeDeconv`` on PATH whose -write_ini writes NEW_ITEMS."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    payload = ini_xml(TOOL, NEW_ITEMS)
    exe = bindir / TOOL
    exe.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import sys
            if sys.argv[1] == "-write_ini":
                open(sys.argv[2], "w").write({payload!r})
            """
        )
    )
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return exe


def write_old_ini(pm: ParameterManager, age_s: float) -> Path:
    ini = Path(pm.ini_dir, f"{TOOL}.ini")
    ini.write_text(ini_xml(TOOL, OLD_ITEMS))
    then = time.time() - age_s
    os.utime(ini, (then, then))
    return ini


# ------------------------------ ini parsing --------------------------------


def test_param_paths_lists_items_and_itemlists(tmp_path):
    ini = tmp_path / "t.ini"
    ini.write_text(ini_xml(TOOL, NEW_ITEMS))
    assert param_paths_from_param_xml_ini(ini, TOOL) == {
        "version", "max_charge", "write_detail", "scan_commands", "SD:tol",
    }
    assert bool_param_paths_from_param_xml_ini(ini, TOOL) == {"write_detail"}


def test_param_paths_of_unreadable_file_is_empty(tmp_path):
    bad = tmp_path / "bad.ini"
    bad.write_text("<not xml")
    assert param_paths_from_param_xml_ini(bad, TOOL) == set()


# ------------------------------ stale .ini ---------------------------------


@pytest.mark.skipif(os.name == "nt", reason="shebang executable")
def test_ini_older_than_tool_is_rewritten(tmp_path, fake_tool):
    pm = ParameterManager(tmp_path / "wf")
    ini = write_old_ini(pm, age_s=3600)  # written before the tool was installed

    assert pm.create_ini(TOOL)
    assert "scan_commands" in ini.read_text()
    assert "ida_log" not in ini.read_text()
    assert not [p for p in Path(pm.ini_dir).iterdir() if p.name.startswith(".")]


@pytest.mark.skipif(os.name == "nt", reason="shebang executable")
def test_ini_newer_than_tool_is_kept(tmp_path, fake_tool):
    pm = ParameterManager(tmp_path / "wf")
    ini = write_old_ini(pm, age_s=0)
    future = time.time() + 60
    os.utime(ini, (future, future))

    assert pm.create_ini(TOOL)
    assert "ida_log" in ini.read_text()


def test_ini_kept_when_tool_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    pm = ParameterManager(tmp_path / "wf")
    ini = write_old_ini(pm, age_s=3600)

    assert pm.create_ini(TOOL)
    assert "ida_log" in ini.read_text()


# ------------------------- why an .ini is missing --------------------------


def test_missing_tool_is_reported_as_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    pm = ParameterManager(tmp_path / "wf")

    assert not pm.create_ini(TOOL)
    assert pm.ini_errors[TOOL] == INI_TOOL_MISSING


@pytest.mark.skipif(os.name == "nt", reason="shebang executable")
def test_failing_tool_keeps_its_output(tmp_path, monkeypatch):
    """An installed tool whose -write_ini fails is not reported as missing."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / TOOL
    exe.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "sys.stderr.write('error while loading shared libraries: libQt6Core.so.6\\n')\n"
        "sys.exit(127)\n"
    )
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    pm = ParameterManager(tmp_path / "wf")

    assert not pm.create_ini(TOOL)
    reason = pm.ini_errors[TOOL]
    assert "exited with code 127" in reason
    assert "libQt6Core.so.6" in reason
    assert not list(Path(pm.ini_dir).iterdir())


@pytest.mark.skipif(os.name == "nt", reason="shebang executable")
def test_success_clears_an_earlier_failure(tmp_path, fake_tool):
    pm = ParameterManager(tmp_path / "wf")
    pm.ini_errors[TOOL] = "earlier failure"

    assert pm.create_ini(TOOL)
    assert TOOL not in pm.ini_errors


def test_known_params_without_ini_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    pm = ParameterManager(tmp_path / "wf")
    assert pm.known_topp_params(TOOL) is None


# --------------------- run_topp and parameters it lacks ---------------------


def build_command(tmp_path, params_json, *, ini_items=None, custom_params=None):
    workflow_dir = tmp_path / "wf"
    pm = ParameterManager(workflow_dir)
    params_json = dict(params_json)
    params_json.setdefault("max_threads", 1)
    pm.params_file.write_text(json.dumps(params_json))
    if ini_items is not None:
        Path(pm.ini_dir, f"{TOOL}.ini").write_text(ini_xml(TOOL, ini_items))
    (tmp_path / "settings.json").write_text(
        json.dumps({"online_deployment": False, "max_threads": {"local": 1, "online": 1}})
    )

    logger = MagicMock()
    executor = CommandExecutor(workflow_dir, logger, pm)
    executor.run_command = MagicMock(return_value=True)
    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        executor.run_topp(
            TOOL, {"in": ["a.mzML"], "out": ["a.tsv"]}, custom_params=custom_params or {}
        )
    finally:
        os.chdir(previous)
    return executor.run_command.call_args.args[0], logger


def test_stored_parameter_the_tool_lacks_is_left_out(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    cmd, logger = build_command(
        tmp_path,
        {TOOL: {"ida_log": "x.log", "max_charge": 30}},
        ini_items=NEW_ITEMS,
    )
    assert "-ida_log" not in cmd
    assert cmd[cmd.index("-max_charge") + 1] == "30"
    messages = " ".join(str(c.args[0]) for c in logger.log.call_args_list)
    assert "ida_log" in messages and "WARNING" in messages


def test_without_ini_nothing_is_left_out(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    cmd, _ = build_command(tmp_path, {TOOL: {"ida_log": "x.log"}})
    assert cmd[cmd.index("-ida_log") + 1] == "x.log"


def test_custom_params_are_never_left_out(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    cmd, _ = build_command(
        tmp_path, {}, ini_items=NEW_ITEMS, custom_params={"ion_type": ["b", "y"]}
    )
    assert cmd[cmd.index("-ion_type") + 1: cmd.index("-ion_type") + 3] == ["b", "y"]


# ------------------------- worker vs. page build ---------------------------


def make_src(root: Path, body: str) -> Path:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "Workflow.py").write_text(body)
    return src


def test_app_build_changes_with_the_code(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"version": "1.1.0"}))
    a = app_build.app_build(str(settings), make_src(tmp_path / "a", "x = 1\n"))
    b = app_build.app_build(str(settings), make_src(tmp_path / "b", "x = 2\n"))
    assert a["version"] == b["version"] == "1.1.0"
    assert a["code"] and b["code"] and a["code"] != b["code"]


def test_mismatch_names_both_builds():
    msg = app_build.build_mismatch(
        {"version": "1.1.0", "code": "aaaa"}, {"version": "1.0.2", "code": "bbbb"}
    )
    assert "1.1.0" in msg and "1.0.2" in msg and "Restart the workers" in msg


@pytest.mark.parametrize(
    "expected, actual",
    [
        (None, {"version": "1", "code": "bbbb"}),  # job from an older page
        ({"version": "1", "code": "aaaa"}, {"version": "1", "code": "aaaa"}),
        ({"version": "1", "code": ""}, {"version": "1", "code": "bbbb"}),
        ({"version": "1", "code": "aaaa"}, {"version": "1", "code": ""}),
    ],
)
def test_no_mismatch_when_equal_or_unknown(expected, actual):
    assert app_build.build_mismatch(expected, actual) is None
