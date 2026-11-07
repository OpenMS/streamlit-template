"""The MCP endpoint for AI assistants (src/agent_access), against a real server.

Tool calls go over HTTP to the sync service's /sync/mcp route as raw JSON-RPC,
the way an MCP client sends them, and over the stdio transport.
"""

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
SETTINGS = {
    "app-name": "Test App", "version": "1.2.3", "online_deployment": True,
    "agent_access": {"enabled": True, "calls_per_minute": 1000, "workflows": {
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
    assert len(tools) == 17
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


def test_start_run_needs_files(tmp_path):
    ws = _workspace(tmp_path)
    tools = Tools(Path.cwd(), ws, agent_settings({**SETTINGS, "online_deployment": False}))
    from src.agent_access.tools import ToolError
    with pytest.raises(ToolError, match="No files chosen"):
        tools.call("start_run", {"workflow": WF})
    with pytest.raises(ToolError, match="No file"):
        tools.call("start_run", {"workflow": WF, "inputs": {"mzML-files": ["missing.mzML"]}})


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


def test_run_command_matches_workflow_manager():
    import ast
    tree = ast.parse(Path("src/workflow/WorkflowManager.py").read_text())
    value = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                 and any(getattr(t, "id", "") == "_RUN_WORKFLOW" for t in node.targets))
    assert ast.literal_eval(value) == runner._RUN_WORKFLOW
