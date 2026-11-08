"""The MCP endpoint for AI assistants (src/agent_access), against a real server.

Tool calls go over HTTP to the sync service's /sync/mcp route as raw JSON-RPC,
the way an MCP client sends them, and over the stdio transport.
"""

import time
import asyncio
import base64
import io
import json
import socket
import threading
from pathlib import Path

import pytest
import requests

tornado = pytest.importorskip("tornado")
import tornado.ioloop  # noqa: E402

from src.agent_access import describe, protocol, runner  # noqa: E402
from src.agent_access.config import agent_settings  # noqa: E402
from src.agent_access.stdio import serve  # noqa: E402
from src.agent_access.tools import Tools  # noqa: E402
from src.sync import server, tokens  # noqa: E402

WF = "topp-workflow"

def _has_example():
    try:
        import src.Workflow as example
    except Exception:  # an app may need packages these tests do not install
        return False
    return hasattr(example, "Workflow")


# Tests that run the template's example workflow and pages: an app made from
# the template replaces those, so they are skipped there.
example_app = pytest.mark.skipif(not _has_example(), reason="needs the template's example workflow")
SETTINGS = {
    "app-name": "Test App", "version": "1.2.3", "online_deployment": True,
    "agent_access": {"enabled": True, "developer_only": False, "calls_per_minute": 1000, "workflows": {
        WF: {"class": "src.Workflow:Workflow",
             "configure_page": "content/topp_workflow_parameter.py",
             "run_page": "content/topp_workflow_execution.py",
             "results_page": "content/topp_workflow_results.py"}}},
}

INI = """<?xml version="1.0" encoding="ISO-8859-1"?>
<PARAMETERS version="1.7.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NODE name="FeatureFinderMetabo" description="">
    <ITEM name="version" value="3.6.0" type="string" description="" />
    <NODE name="1" description="">
      <ITEM name="in" value="" type="input-file" description="" />
      <ITEM name="threads" value="1" type="int" description="" />
      <NODE name="algorithm" description="">
        <NODE name="common" description="">
          <ITEM name="noise_threshold_int" value="10.0" type="double" description="Noise" restrictions="0.0:" />
          <ITEM name="chrom_fwhm" value="5.0" type="double" description="FWHM" advanced="true" />
        </NODE>
        <NODE name="epd" description="">
          <ITEM name="width_filtering" value="fixed" type="string" description="Width" restrictions="off,fixed,auto" />
          <ITEM name="enabled" value="true" type="string" description="On" restrictions="true,false" />
        </NODE>
      </NODE>
    </NODE>
  </NODE>
</PARAMETERS>
"""


def _workspace(root: Path, name="ws-agent") -> Path:
    """A workspace whose workflow was configured once (params.json and an .ini)."""
    ws = root / name
    wf = ws / WF
    (wf / "ini").mkdir(parents=True)
    (wf / "ini" / "FeatureFinderMetabo.ini").write_text(INI)
    (wf / "input-files" / "mzML-files").mkdir(parents=True)
    describe.write_params(wf, {"mzML-files": [], "FeatureFinderMetabo": {}})
    from src.workflow.RunManager import FINISHED, RunManager
    runs = RunManager(wf)
    run_id = runs.new_run("First run")
    runs.finish(run_id, FINISHED)
    results = runs.results_dir(run_id) / "feature-linking"
    results.mkdir(parents=True)
    (results / "features.tsv").write_text("id\tmz\trt\n" + "".join(f"{i}\t{100 + i}\t{i * 2}\n" for i in range(10)))
    (results / "notes.log").write_text("all good\n")
    return ws


@pytest.fixture
def mcp(tmp_path):
    root = tmp_path / "online"
    ws = _workspace(root)
    agent = agent_settings(SETTINGS)
    config = server.sync_settings({"workspace_sync": {"enabled": True}})
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    started, holder = threading.Event(), {}

    def run():
        asyncio.set_event_loop(asyncio.new_event_loop())
        loop = tornado.ioloop.IOLoop.current()
        holder["loop"] = loop
        server.make_app(root, config, agent=agent).listen(
            port, "127.0.0.1", max_body_size=server.MAX_REQUEST_BYTES)
        loop.add_callback(started.set)
        loop.start()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert started.wait(10)
    token, _ = tokens.issue(root, ws.name, 1, kind=tokens.AGENT)
    yield {"root": root, "ws": ws, "url": f"http://127.0.0.1:{port}/sync/mcp",
           "base": f"http://127.0.0.1:{port}/sync", "token": token}
    holder["loop"].add_callback(holder["loop"].stop)
    t.join(5)


def _rpc(mcp, method, params=None, token=None, id_=1):
    body = {"jsonrpc": "2.0", "method": method, "id": id_}
    if params is not None:
        body["params"] = params
    return requests.post(mcp["url"], json=body, timeout=30,
                         headers={"Authorization": f"Bearer {token or mcp['token']}"})


def _call(mcp, name, **arguments):
    r = _rpc(mcp, "tools/call", {"name": name, "arguments": arguments})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_token_kinds_are_separate(tmp_path):
    root = tmp_path / "root"
    (root / "ws").mkdir(parents=True)
    sync_token, _ = tokens.issue(root, "ws", 1)
    agent_token, _ = tokens.issue(root, "ws", 1, kind=tokens.AGENT)
    assert tokens.resolve(root, sync_token) == "ws"
    assert tokens.resolve(root, agent_token) is None
    assert tokens.resolve(root, agent_token, tokens.AGENT) == "ws"
    assert tokens.active_count(root, "ws", tokens.AGENT) == 1
    tokens.revoke(root, "ws", tokens.AGENT)
    assert tokens.resolve(root, agent_token, tokens.AGENT) is None
    assert tokens.resolve(root, sync_token) == "ws"


def test_http_handshake_and_errors(mcp):
    r = _rpc(mcp, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "test", "version": "1"}})
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "test-app"
    assert "tools" in result["capabilities"]

    note = requests.post(mcp["url"], json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                         headers={"Authorization": f"Bearer {mcp['token']}"}, timeout=10)
    assert note.status_code == 202

    tools = _rpc(mcp, "tools/list").json()["result"]["tools"]
    assert len(tools) == 23
    assert {"upload_file", "start_run", "read_result"} <= {t["name"] for t in tools}

    assert _rpc(mcp, "nope").json()["error"]["code"] == protocol.METHOD_NOT_FOUND
    unknown = _rpc(mcp, "tools/call", {"name": "nope", "arguments": {}}).json()
    assert "error" in unknown or unknown["result"]["isError"]

    assert requests.post(mcp["url"], json={"jsonrpc": "2.0", "method": "ping", "id": 1},
                         timeout=10).status_code == 401
    sync_token, _ = tokens.issue(mcp["root"], mcp["ws"].name, 1)
    assert _rpc(mcp, "ping", token=sync_token).status_code == 401
    assert requests.get(mcp["url"], headers={"Authorization": f"Bearer {mcp['token']}"},
                        timeout=10).status_code == 405
    bad = requests.post(mcp["url"], data="{not json", timeout=10,
                        headers={"Authorization": f"Bearer {mcp['token']}"})
    assert bad.json()["error"]["code"] == protocol.PARSE_ERROR


def test_rate_limit(mcp, tmp_path):
    root = tmp_path / "limited"
    _workspace(root)
    agent = agent_settings({**SETTINGS, "agent_access": {**SETTINGS["agent_access"], "calls_per_minute": 3}})
    app = server.make_app(root, server.sync_settings({}), agent=agent)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    started, holder = threading.Event(), {}

    def run():
        asyncio.set_event_loop(asyncio.new_event_loop())
        holder["loop"] = tornado.ioloop.IOLoop.current()
        app.listen(port, "127.0.0.1")
        holder["loop"].add_callback(started.set)
        holder["loop"].start()

    threading.Thread(target=run, daemon=True).start()
    assert started.wait(10)
    token, _ = tokens.issue(root, "ws-agent", 1, kind=tokens.AGENT)
    codes = [requests.post(f"http://127.0.0.1:{port}/sync/mcp", timeout=10,
                           json={"jsonrpc": "2.0", "method": "ping", "id": i},
                           headers={"Authorization": f"Bearer {token}"}).status_code
             for i in range(5)]
    holder["loop"].add_callback(holder["loop"].stop)
    assert codes[:3] == [200, 200, 200] and codes[-1] == 429


def test_upload_in_parts_and_list(mcp):
    data = b"<mzML>" + b"x" * 1000 + b"</mzML>"
    first, second = data[:500], data[500:]
    part = _call(mcp, "upload_file", workflow=WF, key="mzML-files", filename="a.mzML",
                 content_base64=base64.b64encode(first).decode(), complete=False)
    assert not part["isError"] and part["structuredContent"]["received"] == 500
    done = _call(mcp, "upload_file", workflow=WF, key="mzML-files", filename="a.mzML",
                 content_base64=base64.b64encode(second).decode(), append=True)
    assert done["structuredContent"]["size"] == len(data)
    assert (mcp["ws"] / WF / "input-files" / "mzML-files" / "a.mzML").read_bytes() == data

    wrong = _call(mcp, "upload_file", workflow=WF, key="mzML-files", filename="a.txt",
                  content_base64=base64.b64encode(b"x").decode())
    assert wrong["isError"]
    sneaky = _call(mcp, "upload_file", workflow=WF, key="mzML-files", filename="../a.mzML",
                   content_base64=base64.b64encode(b"x").decode())
    assert sneaky["isError"]

    files = _call(mcp, "list_files", workflow=WF)["structuredContent"]["inputs"]["mzML-files"]
    assert [f["name"] for f in files] == ["a.mzML"]
    assert not _call(mcp, "delete_file", workflow=WF, key="mzML-files", filename="a.mzML")["isError"]
    assert _call(mcp, "list_files", workflow=WF)["structuredContent"]["inputs"]["mzML-files"] == []

    log = (mcp["ws"] / ".agent-activity.jsonl").read_text().splitlines()
    assert json.loads(log[-1])["tool"] == "list_files"


@example_app
def test_describe_and_settings(tmp_path):
    ws = _workspace(tmp_path)
    tools = Tools(Path.cwd(), ws, agent_settings({**SETTINGS, "online_deployment": False}))
    info = tools.call("describe_workflow", {"workflow": WF})
    ffm = info["tools"]["FeatureFinderMetabo"]
    params = ffm["parameters"]
    assert "in" not in params and "threads" not in params
    assert params["algorithm:common:noise_threshold_int"]["min"] == 0.0
    assert params["algorithm:epd:width_filtering"]["choices"] == ["off", "fixed", "auto"]
    assert params["algorithm:epd:enabled"]["type"] == "bool"
    assert "algorithm:common:chrom_fwhm" not in params and ffm["advanced_hidden"] == 1

    changed = tools.call("update_settings", {"workflow": WF, "settings": {
        "FeatureFinderMetabo:algorithm:common:noise_threshold_int": 500,
        "FeatureFinderMetabo:1:algorithm:epd:width_filtering": "auto"}})
    assert len(changed["changed"]) == 2
    stored = describe.read_params(ws / WF)["FeatureFinderMetabo"]
    assert stored["algorithm:common:noise_threshold_int"] == 500
    assert stored["algorithm:epd:width_filtering"] == "auto"

    from src.agent_access.tools import ToolError
    for bad in ({"FeatureFinderMetabo:algorithm:epd:width_filtering": "wide"},
                {"FeatureFinderMetabo:algorithm:common:noise_threshold_int": -1},
                {"FeatureFinderMetabo:algorithm:common:noise_threshold_inn": 1},
                {"_defaults": {}}):
        with pytest.raises(ToolError):
            tools.call("update_settings", {"workflow": WF, "settings": bad})
    with pytest.raises(ToolError, match="Unknown workflow"):
        tools.call("describe_workflow", {"workflow": "other"})


@example_app
def test_start_run_needs_files(tmp_path):
    ws = _workspace(tmp_path)
    tools = Tools(Path.cwd(), ws, agent_settings({**SETTINGS, "online_deployment": False}))
    from src.agent_access.tools import ToolError
    with pytest.raises(ToolError, match="No files chosen"):
        tools.call("start_run", {"workflow": WF})
    with pytest.raises(ToolError, match="No file"):
        tools.call("start_run", {"workflow": WF, "inputs": {"mzML-files": ["missing.mzML"]}})


@example_app
def test_read_results_and_download(mcp):
    listed = _call(mcp, "list_results", workflow=WF)["structuredContent"]["files"]
    paths = {f["path"] for f in listed}
    assert "feature-linking/features.tsv" in paths
    table = _call(mcp, "read_result", workflow=WF, path="feature-linking/features.tsv",
                  offset=2, limit=3, columns=["mz"])["structuredContent"]
    assert table["columns"] == ["id", "mz", "rt"] and table["rows"] == [{"mz": 102}, {"mz": 103}, {"mz": 104}]
    assert table["total_rows"] == 10
    text = _call(mcp, "read_result", workflow=WF, path="feature-linking/notes.log")["structuredContent"]
    assert text["text"] == "all good\n"
    assert _call(mcp, "read_result", workflow=WF, path="../params.json")["isError"]

    r = requests.get(table["download"], headers={"Authorization": f"Bearer {mcp['token']}"}, timeout=10)
    assert r.status_code == 200 and r.content.startswith(b"id\tmz")


def test_stdio_transport(tmp_path):
    ws = _workspace(tmp_path)
    tools = Tools(Path.cwd(), ws, agent_settings({**SETTINGS, "online_deployment": False}))
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "get_app_info", "arguments": {}}},
    ]
    out = io.StringIO()
    serve(tools, io.StringIO("\n".join(json.dumps(m) for m in lines) + "\nnot json\n"), out)
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a.get("id") for a in answers] == [1, 2, None]
    assert answers[0]["result"]["protocolVersion"] == "2025-11-25"
    info = answers[1]["result"]["structuredContent"]
    assert WF in [w["workflow"] for w in info["workflows"]]
    assert answers[2]["error"]["code"] == protocol.PARSE_ERROR


def test_an_assistant_starts_a_run_as_the_run_button_does(tmp_path, monkeypatch):
    """One start for all (src/workflow/start.py): the run folder keeps the
    settings and the run they follow, so the processing report reads the same."""
    from src.workflow import start
    from src.workflow.RunManager import RunManager
    from src.workflow.processing_report import report_for

    launched = []
    monkeypatch.setattr(start, "launch_local", lambda *a, **k: launched.append((a, k)))
    workflow_dir = Path(tmp_path, "wf")
    workflow_dir.mkdir()
    params = {"mzML-files": ["a.mzML"], "_follow_up": {"run": "r0", "name": "First run",
                                                        "note": "noise threshold 500"}}
    runner.start(Path.cwd(), tmp_path, "wf", "src.Workflow:Workflow", params,
                 "By the assistant", online=False, multi_run=True)
    runs = RunManager(workflow_dir)
    (run_id,) = [r["id"] for r in runs.list_runs()]
    assert runs.get(run_id)["name"] == "By the assistant"
    assert launched[0][0][1:] == ("Workflow", "src.Workflow", run_id)
    assert launched[0][1]["detach"] is True
    # The next settings start fresh; the run keeps which run it follows
    assert "_follow_up" not in json.loads(Path(workflow_dir, "params.json").read_text())
    assert runs.params(run_id)["_follow_up"]["name"] == "First run"
    assert report_for(workflow_dir, run_id)["run"]["follows"] == "First run"


@example_app
def test_download_of_a_linked_result(mcp, tmp_path):
    # Demo workspaces link their results into the demo's source, outside the workspace.
    source = tmp_path / "demo-source" / "linked.tsv"
    source.parent.mkdir()
    source.write_text("a\tb\n1\t2\n")
    results = next(mcp["ws"].glob(f"{WF}/runs/*/results/feature-linking"))
    (results / "linked.tsv").symlink_to(source)
    info = _call(mcp, "read_result", workflow=WF, path="feature-linking/linked.tsv")["structuredContent"]
    assert info["download"]
    r = requests.get(info["download"], headers={"Authorization": f"Bearer {mcp['token']}"}, timeout=10)
    assert r.status_code == 200 and r.content == b"a\tb\n1\t2\n"


def _routes(app) -> list[str]:
    return [rule.matcher.regex.pattern for rule in app.wildcard_router.rules]


def test_download_route_without_workspace_sync(tmp_path):
    agent = agent_settings(SETTINGS)
    routes = _routes(server.make_app(tmp_path, server.sync_settings({}), agent=agent))
    assert sum("download" in r for r in routes) == 1 and any("mcp" in r for r in routes)
    both = _routes(server.make_app(tmp_path, server.sync_settings({"workspace_sync": {"enabled": True}}),
                                   agent=agent))
    assert sum("download" in r for r in both) == 1
    assert not any("download" in r for r in _routes(server.make_app(tmp_path, server.sync_settings({}))))


def test_stdio_with_a_relative_settings_path(tmp_path, monkeypatch):
    from src.agent_access import stdio
    app = tmp_path / "app"
    app.mkdir()
    (app / "settings.json").write_text(json.dumps({**SETTINGS, "online_deployment": False}))
    seen = {}
    monkeypatch.setattr(stdio, "serve", lambda tools: seen.setdefault("tools", tools))
    monkeypatch.chdir(tmp_path)
    assert stdio.main(["--settings", "app/settings.json", "--workspaces-dir", str(tmp_path / "ws"),
                       "--workspace", "w1"]) == 0
    assert Path.cwd() == app.resolve() and (tmp_path / "ws" / "w1").is_dir()
    assert seen["tools"].workspace == tmp_path / "ws" / "w1"


def test_local_snippets_set_pythonpath(tmp_path):
    from src.agent_access.ui import local_snippets
    snippets = local_snippets(agent_settings(SETTINGS), tmp_path / "default", "")
    root = str(Path("settings.json").resolve().parent)
    assert f"-e PYTHONPATH={root} --" in snippets["Claude Code"]
    config = json.loads(snippets["Other MCP clients (JSON)"])
    assert next(iter(config["mcpServers"].values()))["env"] == {"PYTHONPATH": root}


@example_app
def test_show_in_app(tmp_path):
    from src.agent_access import show
    from src.agent_access.tools import ToolError
    from src.workflow.RunManager import RunManager
    ws = _workspace(tmp_path)
    tools = Tools(Path.cwd(), ws, agent_settings(SETTINGS), app_url="https://app.example")
    run_id = RunManager(ws / WF).latest()
    out = tools.call("show_in_app", {"workflow": WF, "run_id": run_id,
                                     "note": "  The features of the first run.  "})
    assert out["link"] == "https://app.example/topp_workflow_results?workspace=ws-agent"
    request = show.latest(ws)
    assert request["id"] == out["id"]
    assert request["page_file"] == "content/topp_workflow_results.py"
    assert request["run_id"] == run_id and request["note"] == "The features of the first run."
    with pytest.raises(ToolError, match="No run"):
        tools.call("show_in_app", {"workflow": WF, "run_id": "nope"})
    with pytest.raises(ToolError, match="page must be"):
        tools.call("show_in_app", {"workflow": WF, "page": "elsewhere"})
    assert any(t["name"] == "show_in_app" for t in tools.definitions())


def _follow_page():
    import streamlit as st
    from src.agent_access import ui
    ui.follow()
    st.write("page")


def test_app_opens_what_the_assistant_shows(tmp_path):
    from streamlit.testing.v1 import AppTest
    from src.agent_access import activity, show, ui
    from src.workflow import run_widgets
    from src.workflow.RunManager import RunManager
    ws = _workspace(tmp_path)
    run_id = RunManager(ws / WF).latest()
    activity.record(ws, "get_app_info")
    show.write(ws, {"workflow": WF, "page": "results", "page_file": "", "run_id": None,
                    "note": "old"})

    at = AppTest.from_function(_follow_page)
    at.session_state.settings = {**SETTINGS, "online_deployment": False}
    at.session_state.workspace = ws
    at.session_state.location = "local"
    at.run()
    assert not at.exception and not at.toast
    # What was shown before the session opened is not opened again.
    assert at.session_state[ui._SEEN] == show.latest(ws)["id"]

    show.write(ws, {"workflow": WF, "page": "results", "page_file": "", "run_id": run_id,
                    "note": "Look at the features."})
    at.run()  # the page's own rerun: the watcher sees the new request
    assert not at.exception
    key = run_widgets.selected_run_key(RunManager(ws / WF))
    assert at.session_state[key] == run_id
    assert [t.value for t in at.toast] == ["Look at the features."]


def _feature_matrix(ws: Path) -> str:
    """A consensus feature table in the latest run, as the workflow writes it."""
    from src.workflow.RunManager import RunManager
    run_id = RunManager(ws / WF).latest()
    out = RunManager(ws / WF).results_dir(run_id) / "feature-linking" / "feature_matrix.tsv"
    out.write_text("id\tcharge\tmz\tRT\tquality\tA.mzML\tB.mzML\n" + "".join(
        f"{i}\t1\t{100 + i}\t{i * 2}\t0.5\t{1000 * (i + 1)}\t{500 * (i + 1)}\n" for i in range(12)))
    return run_id


@example_app
def test_result_views_and_components(tmp_path):
    from src.agent_access.tools import ToolError
    ws = _workspace(tmp_path)
    run_id = _feature_matrix(ws)
    tools = Tools(Path.cwd(), ws, agent_settings(SETTINGS))
    views = tools.call("list_result_views", {"workflow": WF})
    assert views["run_id"] == run_id and views["open_view"] == "features"
    by_name = {c["name"]: c for c in views["components"]}
    assert by_name["features"]["run_has_it"]
    assert by_name["intensities"]["shown_with"] == "features"
    # The run was processed without the custom Python tool
    assert not by_name["top_features"]["run_has_it"]
    assert by_name["top_features"]["needs"] == ["the custom Python tool"]
    assert [v["name"] for v in views["views"]] == ["features", "top", "all"]

    seen = tools.call("look_at_results", {"workflow": WF, "rows": 3})
    assert set(seen["components"]) == {"features", "intensities"}
    shows = seen["components"]["features"]["shows"]
    assert {"type": "metric", "label": "number of consensus features", "value": "12",
            "delta": None} in shows
    table = next(i for i in shows if i["type"] == "table")
    assert table["rows"] == 12 and len(table["first_rows"]) == 3
    assert table["numbers"]["mz"]["max"] == 111
    key = table["select_key"]
    assert seen["components"]["intensities"]["shows"][0]["type"] == "info"

    # Rows picked in the table: the plot that follows the selection
    picked = tools.call("look_at_results", {"workflow": WF, "components": ["features", "intensities"],
                                             "select": {key: [0, 2]}})
    plot = picked["components"]["intensities"]["shows"][0]
    assert plot["type"] == "plot" and plot["y_axis"] == "intensity"
    assert [t["name"] for t in plot["traces"]] == ["A.mzML", "B.mzML"]
    assert plot["traces"][0]["y"] == [1000, 3000]
    with pytest.raises(ToolError, match="Unknown components"):
        tools.call("look_at_results", {"workflow": WF, "components": ["nope"]})
    with pytest.raises(ToolError, match="select maps"):
        tools.call("look_at_results", {"workflow": WF, "select": {key: "0"}})


@example_app
def test_assistant_views(tmp_path):
    from src.agent_access.tools import ToolError
    from src.layout_manager.layout import load_views
    from src.workflow.RunManager import FINISHED, RunManager
    from src.Workflow import Workflow
    ws = _workspace(tmp_path)
    tools = Tools(Path.cwd(), ws, agent_settings(SETTINGS))
    path = ws / WF / Workflow.RESULTS_LAYOUT
    runs = RunManager(ws / WF)
    first = runs.latest()
    second = runs.new_run("Higher noise threshold")
    runs.finish(second, FINISHED)

    def state():
        return load_views(path, Workflow.COMPONENTS, Workflow.PRESETS, Workflow.PRESETS[0]["layout"])

    out = tools.call("show_in_app", {"workflow": WF, "view": "all", "note": "Everything."})
    assert out["view"] == "all" and state()["current"] == "all"
    question = "Does the noise threshold change the features?"
    saved = tools.call("save_view", {
        "workflow": WF, "label": "Threshold compared", "components": ["features", "intensities"],
        "runs": [first, second], "side_by_side": True, "question": question,
        "explanation": ["Run 2 keeps 8 of the 10 features of run 1."],
        "defaults": [{"selection": {"feature": 3}, "zoom": {"intensities": {"x": [0, 5]}}}, {}]})
    name = saved["view"]
    assert name == "custom-assistant-1"
    st_ = state()
    view = {v["name"]: v for v in st_["views"]}[name]
    assert st_["current"] == name and st_["experiments"] == 2 and st_["side_by_side"]
    assert view["by"] == "assistant" and view["runs"] == [first, second]
    assert view["rows"] == [["features"], ["intensities"]] and view["question"] == question
    assert view["defaults"] == [{"dataset": first, "selection": {"feature": 3},
                                 "zoom": {"intensities": {"x": [0.0, 5.0]}}}]
    listed = {v["name"]: v for v in tools.call("list_result_views", {"workflow": WF})["views"]}
    assert listed[name]["saved_by_you"] and listed[name]["explanation"]
    # Changing it keeps its name; a second view of the same answer stays in the bar
    tools.call("save_view", {"workflow": WF, "name": name, "label": "Threshold compared",
                             "components": [["features", "intensities"]], "runs": [first, second],
                             "question": question, "explanation": ["Point one.", "Point two."]})
    other = tools.call("save_view", {"workflow": WF, "label": "Run 2 alone", "components": ["features"],
                                     "runs": [second], "question": question,
                                     "explanation": ["Run 2 alone."]})["view"]
    views = {v["name"]: v for v in state()["views"]}
    assert views[name]["rows"] == [["features", "intensities"]] and views[name]["in_bar"]
    assert views[other]["in_bar"]
    # A new question moves the earlier answer's views to More
    newer = tools.call("save_view", {"workflow": WF, "label": "Another answer", "components": ["features"],
                                     "runs": [first], "question": "Something else?",
                                     "explanation": ["One point."]})["view"]
    views = {v["name"]: v for v in state()["views"]}
    assert not views[name]["in_bar"] and not views[other]["in_bar"] and views[newer]["in_bar"]
    # show_in_app picks the view's first run
    out = tools.call("show_in_app", {"workflow": WF, "view": name, "note": "Both runs."})
    assert out["run_id"] == first and state()["current"] == name and state()["experiments"] == 2
    for bad, match in [
        ({"components": [["intensities"]]}, "needs Consensus features"),
        ({"runs": [first, first]}, "different runs"),
        ({"runs": [first], "side_by_side": True}, "exactly two"),
        ({"runs": ["nope"]}, "No run"),
        ({"explanation": ["a"] * 6}, "one to 5"),
        ({"explanation": ["x" * 301]}, "one sentence"),
        ({"label": "All"}, "called"),
        ({"name": "all"}, "not a view you saved"),
    ]:
        args = {"workflow": WF, "label": "Bad", "components": ["features"], "runs": [first],
                "question": question, "explanation": ["One point."], **bad}
        with pytest.raises(ToolError, match=match):
            tools.call("save_view", args)
    with pytest.raises(ToolError, match="not a view you saved"):
        tools.call("delete_view", {"workflow": WF, "name": "all"})
    assert tools.call("delete_view", {"workflow": WF, "name": name}) == {"deleted": name}
    assert name not in {v["name"] for v in state()["views"]} and state()["experiments"] == 1
    with pytest.raises(ToolError, match="No view"):
        tools.call("show_in_app", {"workflow": WF, "view": "nope"})
    with pytest.raises(ToolError, match="results page"):
        tools.call("show_in_app", {"workflow": WF, "page": "configure", "view": "all"})


def test_plots_reach_the_assistant_as_images():
    class Fake:
        def has(self, name):
            return True

        def call(self, name, arguments):
            return {"components": {}, "_images": [{"title": "Plot", "data": "UE5H"}]}

    out = protocol.call_tool({"name": "look_at_results", "arguments": {}}, Fake())
    assert "_images" not in out["structuredContent"]
    assert out["content"][1:] == [{"type": "text", "text": "Image 1: Plot"},
                                  {"type": "image", "data": "UE5H", "mimeType": "image/png"}]


def _panel_page():
    import streamlit as st
    from src.agent_access import ui
    st.write("assistant" if ui.enabled() else "hidden")


def test_assistant_is_a_developer_feature(tmp_path):
    from streamlit.testing.v1 import AppTest
    settings = {**SETTINGS, "agent_access": {**SETTINGS["agent_access"], "developer_only": True}}
    at = AppTest.from_function(_panel_page)
    at.session_state.settings = settings
    at.session_state["developer-mode"] = False
    at.run()
    assert at.markdown[0].value == "hidden"
    at.session_state["developer-mode"] = True
    at.run()
    assert at.markdown[0].value == "assistant"
    assert agent_settings({"agent_access": {"enabled": True}})["developer_only"] is True


def _assistant_tools(tmp_path, monkeypatch):
    """Tools of a local workspace whose first run has settings, and starts recorded, not run."""
    from src.workflow import start
    from src.workflow.RunManager import FINISHED, RunManager
    launched = []
    monkeypatch.setattr(start, "launch_local", lambda *a, **k: launched.append(a))
    ws = _workspace(tmp_path)
    wf = ws / WF
    folder = wf / "input-files" / "mzML-files"
    for name in ("Control.mzML", "Treatment.mzML", "Extra.mzML"):
        (folder / name).write_text("<mzML/>")
    describe.write_params(wf, {"mzML-files": [str(folder / "Control.mzML"), str(folder / "Treatment.mzML")],
                               "FeatureFinderMetabo": {}})
    runs = RunManager(wf)
    base = runs.new_run("Baseline", wf / "params.json")
    runs.finish(base, FINISHED)
    tools = Tools(Path.cwd(), ws, agent_settings({**SETTINGS, "online_deployment": False}))
    return tools, runs, base, launched


@example_app
def test_every_assistant_run_says_why(tmp_path, monkeypatch):
    from src.agent_access.tools import ToolError
    from src.workflow.processing_report import report_for, to_markdown
    tools, runs, _, _ = _assistant_tools(tmp_path, monkeypatch)
    with pytest.raises(ToolError, match="why"):
        tools.call("start_run", {"workflow": WF, "question": "Does Treatment carry more signal?",
                                 "inputs": {"mzML-files": ["Control.mzML"]}})
    out = tools.call("start_run", {"workflow": WF, "question": "Does Treatment carry more signal?",
                                   "why": "First pass, defaults",
                                   "inputs": {"mzML-files": ["Control.mzML", "Treatment.mzML"]}})
    run_id = out["run_id"]
    run = runs.get(run_id)
    assert run["purpose"] == {"by": "AI assistant", "question": "Does Treatment carry more signal?",
                              "why": "First pass, defaults"}
    # The next settings, and so a person's next run, start without it
    assert "_purpose" not in json.loads((runs.workflow_dir / "params.json").read_text())
    md = to_markdown(report_for(runs.workflow_dir, run_id))
    assert "| Started by | AI assistant |" in md
    assert "| Question | Does Treatment carry more signal? |" in md
    assert "| Why this run | First pass, defaults |" in md
    listed = tools.call("list_runs", {"workflow": WF})["runs"]
    assert listed[0]["purpose"]["why"] == "First pass, defaults"


@example_app
def test_follow_up_changes_settings(tmp_path, monkeypatch):
    from src.workflow.processing_report import report_for
    tools, runs, base, _ = _assistant_tools(tmp_path, monkeypatch)
    out = tools.call("follow_up", {
        "workflow": WF, "run_id": base, "question": "Does Treatment carry more signal?",
        "why": "The noise floor of these runs is about 8e3",
        "settings": {"FeatureFinderMetabo:algorithm:common:noise_threshold_int": 10000}})
    run_id = out["run_id"]
    params = runs.params(run_id)
    assert params["FeatureFinderMetabo"]["algorithm:common:noise_threshold_int"] == 10000.0
    assert [Path(f).name for f in params["mzML-files"]] == ["Control.mzML", "Treatment.mzML"]
    report = report_for(runs.workflow_dir, run_id)["run"]
    assert report["follows"] == "Baseline"
    assert report["purpose"]["why"] == "The noise floor of these runs is about 8e3"


@example_app
def test_follow_up_adds_files_or_an_analysis(tmp_path, monkeypatch):
    from src.agent_access.tools import ToolError
    tools, runs, base, _ = _assistant_tools(tmp_path, monkeypatch)
    q = {"workflow": WF, "run_id": base, "question": "q"}
    with pytest.raises(ToolError, match="Already in the experiment"):
        tools.call("follow_up", {**q, "why": "more", "add_files": {"mzML-files": ["Control.mzML"]}})
    with pytest.raises(ToolError, match="not both"):
        tools.call("follow_up", {**q, "why": "x", "keep": ["FeatureFinderMetabo"],
                                 "add_files": {"mzML-files": ["Extra.mzML"]}})
    with pytest.raises(ToolError, match="Not a tool"):
        tools.call("follow_up", {**q, "why": "x", "keep": ["Nope"]})
    added = tools.call("follow_up", {**q, "why": "A third sample",
                                     "add_files": {"mzML-files": ["Extra.mzML"]}})
    run = runs.get(added["run_id"])
    assert run["adds_to"] == base
    assert [Path(f).name for f in runs.params(added["run_id"])["mzML-files"]] == ["Extra.mzML"]
    runs.finish(added["run_id"], "finished")
    kept = tools.call("follow_up", {**q, "why": "Statistics on these features",
                                    "keep": ["FeatureFinderMetabo"]})
    info = runs.params(kept["run_id"])["_follow_up"]
    assert info["kept"] == ["FeatureFinderMetabo"] and info["reuses"] == [base]
    with pytest.raises(ToolError, match="No run"):
        tools.call("follow_up", {**q, "run_id": "nope", "why": "x"})


def test_install_prompt_names_each_agent(tmp_path):
    from src.agent_access import install
    entry = install.server_entry(tmp_path / "default", Path("settings.json"))
    prompt = install.install_prompt("Test App", "default", "test-app", entry)
    assert "claude mcp add --scope user test-app" in prompt
    assert "codex mcp add test-app --env PYTHONPATH=" in prompt and " -- " in prompt
    assert "~/.gemini/settings.json" in prompt
    assert "get_app_info" in prompt and '"default"' in prompt
    assert entry["args"][-2:] == ["--workspace", "default"]


def test_connect_claude_desktop_keeps_other_servers(tmp_path):
    from src.agent_access import install
    path = tmp_path / "Claude" / "claude_desktop_config.json"
    entry = install.server_entry(tmp_path / "default", Path("settings.json"))
    assert not install.desktop_connected("test-app", entry, path)
    install.connect_claude_desktop("test-app", entry, path)
    assert install.desktop_connected("test-app", entry, path)
    data = json.loads(path.read_text())
    data["mcpServers"]["other"] = {"command": "x"}
    data["theme"] = "dark"
    path.write_text(json.dumps(data))
    install.connect_claude_desktop("test-app", entry, path)
    data = json.loads(path.read_text())
    assert set(data["mcpServers"]) == {"test-app", "other"} and data["theme"] == "dark"
    assert json.loads(path.with_name(path.name + ".bak").read_text())["theme"] == "dark"
    path.write_text("[1, 2]")
    with pytest.raises(ValueError):
        install.connect_claude_desktop("test-app", entry, path)
    assert path.read_text() == "[1, 2]"


@example_app
def test_configure_page_shown_once_even_after_the_upload_page(tmp_path, monkeypatch):
    """The upload page writes params.json (its file selection) and an empty ini
    folder; the workflow's settings still have to come from its configure page."""
    calls = []
    monkeypatch.setattr(describe, "prepare", lambda *a, **k: calls.append(a) or "")
    ws = tmp_path / "ws"
    wf = ws / WF
    (wf / "ini").mkdir(parents=True)
    (wf / "input-files" / "mzML-files").mkdir(parents=True)
    describe.write_params(wf, {"mzML-files": []})
    tools = Tools(Path.cwd(), ws, agent_settings({**SETTINGS, "online_deployment": False}))
    tools.call("describe_workflow", {"workflow": WF})
    assert len(calls) == 1
    (wf / "ini" / "FeatureFinderMetabo.ini").write_text(INI)
    tools.call("describe_workflow", {"workflow": WF})
    assert len(calls) == 1
    # Nothing running: the wait ends at once
    started = time.monotonic()
    assert tools.call("get_run_status", {"workflow": WF, "wait": 30})["running"] is False
    assert time.monotonic() - started < 5


@example_app
def test_sync_sidebar_needs_no_page_registry(tmp_path):
    """The assistant shows a configure page on its own (no navigation); with
    developer mode on, the sync panel's links must not break that page."""
    from streamlit.testing.v1 import AppTest

    settings = json.loads(Path("settings.json").read_text(encoding="utf-8"))
    settings.update(test=True, online_deployment=True)
    settings["workspace_sync"] = {**(settings.get("workspace_sync") or {}),
                                  "enabled": True, "developer_only": True}
    at = AppTest.from_file("content/topp_workflow_parameter.py", default_timeout=120)
    at.session_state.settings = settings
    at.session_state.workspace = tmp_path / "ws"
    at.session_state.location = "online"
    at.session_state.controllo = True
    at.session_state.previous_dir = str(Path.cwd())
    at.session_state.local_dir = ""
    at.session_state["developer-mode"] = True
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""


@example_app
def test_results_kept_elsewhere_through_a_results_store(tmp_path, monkeypatch):
    """An app that keeps its results in a cache of datasets, not run folders,
    lists them as runs through the class's results_store."""
    from src.Workflow import Workflow

    ws = tmp_path / "ws"
    cache = ws / "cache" / "files"
    for name in ("run_a", "run_b"):
        Path(cache, name).mkdir(parents=True)
        Path(cache, name, "masses.tsv").write_text("mass\tintensity\n1000.5\t20\n2000.1\t5\n")

    class Store:
        def __init__(self, workflow_dir):
            self.root = Path(workflow_dir).parent / "cache" / "files"

        def list_runs(self):
            return [{"id": p.name, "name": p.name.upper(), "status": "finished"}
                    for p in sorted(self.root.iterdir())]

        def get(self, run_id):
            return next((r for r in self.list_runs() if r["id"] == run_id), None)

        def latest(self):
            runs = self.list_runs()
            return runs[-1]["id"] if runs else None

        def results_dir(self, run_id):
            return self.root / run_id

    monkeypatch.setattr(Workflow, "results_store", staticmethod(Store), raising=False)
    tools = Tools(Path.cwd(), ws, agent_settings(SETTINGS))
    runs = tools.call("list_runs", {"workflow": WF})
    assert [r["id"] for r in runs["runs"]] == ["run_a", "run_b"]
    assert tools.call("list_results", {"workflow": WF})["run_id"] == "run_b"
    table = tools.call("read_result", {"workflow": WF, "run_id": "run_a", "path": "masses.tsv"})
    assert table["rows"][0]["mass"] == 1000.5
    with pytest.raises(Exception):
        tools.call("read_result", {"workflow": WF, "run_id": "run_c", "path": "masses.tsv"})
    view = tools.call("save_view", {
        "workflow": WF, "label": "Both runs", "components": [["features"]],
        "runs": ["run_a", "run_b"], "side_by_side": True, "question": "Which has more masses?",
        "explanation": ["Both runs side by side."]})
    assert view["runs"] == ["run_a", "run_b"]
    # A page drawn in the browser only: views yes, looking no
    monkeypatch.delattr(Workflow, "renderers")
    assert tools.call("list_result_views", {"workflow": WF, "run_id": "run_a"})["views"]
    with pytest.raises(Exception, match="browser only"):
        tools.call("look_at_results", {"workflow": WF, "run_id": "run_a"})
