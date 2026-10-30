"""End-to-end tests for workspace sync: a real sync server on a free port,
a local workspace laid out like the offline app's, and the client between
them. No Streamlit is involved."""

import asyncio
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

tornado = pytest.importorskip("tornado")
requests = pytest.importorskip("requests")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sync import client, paths, server, tokens

MB = 1024 * 1024


@pytest.fixture
def online(tmp_path):
    """A running sync server over a workspaces root with one workspace."""
    root = tmp_path / "online"
    ws = root / "ws-online"
    ws.mkdir(parents=True)
    config = server.sync_settings({"workspace_sync": {"enabled": True}})
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    started = threading.Event()
    holder = {}

    def run():
        asyncio.set_event_loop(asyncio.new_event_loop())
        loop = tornado.ioloop.IOLoop.current()
        holder["loop"] = loop
        server.make_app(root, config).listen(port, "127.0.0.1", max_body_size=server.MAX_REQUEST_BYTES)
        loop.add_callback(started.set)
        loop.start()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert started.wait(10)
    token, _ = tokens.issue(root, "ws-online", 1)
    yield {"root": root, "ws": ws, "url": f"http://127.0.0.1:{port}/sync", "token": token, "config": config}
    holder["loop"].add_callback(holder["loop"].stop)
    t.join(5)


def _local_workspace(tmp_path) -> Path:
    ws = tmp_path / "local" / "default"
    inputs = ws / "topp-workflow" / "input-files" / "mzML-files"
    inputs.mkdir(parents=True)
    (inputs / "a.mzML").write_bytes(os.urandom(3 * MB + 17))
    # A referenced file and a Bruker-style folder, both outside the workspace.
    ext = tmp_path / "instrument"
    (ext / "run.d" / "sub").mkdir(parents=True)
    (ext / "run.d" / "analysis.tdf").write_bytes(b"tdf" * 1000)
    (ext / "run.d" / "sub" / "x.bin").write_bytes(b"\x01" * 5000)
    (ext / "b.raw").write_bytes(os.urandom(MB))
    (inputs / "external_files.txt").write_text(f"{ext / 'b.raw'}\n{ext / 'run.d'}\n")
    (ws / "topp-workflow" / "params.json").write_text('{"x": 1}')
    (ws / "params.json").write_text("{}")
    (ws / "topp-workflow" / "results").mkdir()
    (ws / "topp-workflow" / "results" / "local-only.tsv").write_text("ignored")
    return ws


def test_path_rules():
    assert paths.is_pushable("params.json")
    assert paths.is_pushable("wf/params.json")
    assert paths.is_pushable("wf/input-files/key/a.mzML")
    assert paths.is_pushable("mzML-files/a.mzML")
    assert paths.is_pushable("wf/input-files/key/run.d/sub/x.bin")
    for bad in ["../x", "/etc/passwd", "wf/results/a.tsv", "wf/input-files/key/external_files.txt",
                "wf/ini/Tool.ini", ".sync.json", "wf/input-files/key/.hidden", "wf\\input-files\\k\\a",
                "wf/input-files/../../x/y"]:
        assert not paths.is_pushable(bad), bad
    assert paths.is_pullable("wf/results/a/b.tsv")
    assert not paths.is_pullable("wf/input-files/k/a.mzML")
    assert not paths.is_pullable("wf/results/../../x")


def test_push_pull_roundtrip(online, tmp_path):
    ws = _local_workspace(tmp_path)
    c = client.SyncClient(online["url"], online["token"], chunk_size=MB)
    assert c.check() == "ws-online"

    seen = []
    report = c.push(ws, progress=lambda d, t, r: seen.append((d, t)))
    sent = set(report.transferred)
    assert sent == {
        "params.json",
        "topp-workflow/params.json",
        "topp-workflow/input-files/mzML-files/a.mzML",
        "topp-workflow/input-files/mzML-files/b.raw",
        "topp-workflow/input-files/mzML-files/run.d/analysis.tdf",
        "topp-workflow/input-files/mzML-files/run.d/sub/x.bin",
    }
    remote = online["ws"]
    for rel in sent:
        local = paths.push_entries(ws)[rel]
        assert (remote / rel).read_bytes() == local.read_bytes(), rel
    assert not (remote / "topp-workflow/input-files/mzML-files/external_files.txt").exists()
    assert not (remote / "topp-workflow/results").exists()
    assert seen[-1][0] == seen[-1][1]

    # Nothing changed: nothing is sent again.
    again = c.push(ws)
    assert again.transferred == [] and again.unchanged == len(sent)

    # The online run produces results; pull brings them back, only once.
    res = remote / "topp-workflow" / "results" / "quant"
    res.mkdir(parents=True)
    (res / "proteins.tsv").write_bytes(os.urandom(2 * MB + 5))
    (remote / "topp-workflow" / "results" / "local-only.tsv").write_text("server")
    pulled = c.pull(ws)
    assert set(pulled.transferred) == {"topp-workflow/results/quant/proteins.tsv",
                                       "topp-workflow/results/local-only.tsv"}
    assert (ws / "topp-workflow/results/quant/proteins.tsv").read_bytes() == (res / "proteins.tsv").read_bytes()
    assert (ws / "topp-workflow/results/local-only.tsv").read_text() == "server"
    assert c.pull(ws).transferred == []


def test_upload_resumes_after_interruption(online, tmp_path):
    ws = _local_workspace(tmp_path)
    c = client.SyncClient(online["url"], online["token"], chunk_size=MB)
    cancel = threading.Event()

    def stop_midway(done, total, rel):
        if rel.endswith("a.mzML") and done >= MB:
            cancel.set()

    with pytest.raises(client.Cancelled):
        c.push(ws, progress=stop_midway, cancel=cancel)
    pending = client.read_link(ws)["uploads"]
    assert "topp-workflow/input-files/mzML-files/a.mzML" in pending
    # A new client (an app restart) continues the same tus upload.
    offsets = []
    c2 = client.SyncClient(online["url"], online["token"], chunk_size=MB)
    c2.push(ws, progress=lambda d, t, r: offsets.append((r, d)))
    first = [d for r, d in offsets if r.endswith("a.mzML")][0]
    assert first > 0
    assert client.read_link(ws)["uploads"] == {}
    rel = "topp-workflow/input-files/mzML-files/a.mzML"
    assert (online["ws"] / rel).read_bytes() == (ws / rel).read_bytes()


def test_download_resumes_from_partial_file(online, tmp_path):
    ws = tmp_path / "local" / "default"
    ws.mkdir(parents=True)
    res = online["ws"] / "wf" / "results"
    res.mkdir(parents=True)
    data = os.urandom(3 * MB)
    (res / "big.bin").write_bytes(data)
    part = ws / "wf" / "results" / ".big.bin.sync-part"
    part.parent.mkdir(parents=True)
    part.write_bytes(data[:MB])
    c = client.SyncClient(online["url"], online["token"])
    got = []
    c.pull(ws, progress=lambda d, t, r: got.append(d))
    assert (ws / "wf/results/big.bin").read_bytes() == data
    assert not part.exists()
    assert got[0] > MB


def test_server_refuses_bad_requests(online):
    url, token = online["url"], online["token"]
    auth = {"Authorization": f"Bearer {token}", "Tus-Resumable": "1.0.0"}
    assert requests.get(f"{url}/manifest").status_code == 401
    assert requests.get(f"{url}/manifest", headers={"Authorization": "Bearer nope"}).status_code == 401
    b64 = lambda s: __import__("base64").b64encode(s.encode()).decode()
    for path in ["../escape", "wf/results/x.tsv", "wf/ini/a.ini"]:
        r = requests.post(f"{url}/files", headers={**auth, "Upload-Length": "1",
                                                    "Upload-Metadata": f"path {b64(path)}"})
        assert r.status_code == 403, path
    r = requests.get(f"{url}/download", params={"path": "wf/input-files/k/a.mzML"}, headers=auth)
    assert r.status_code == 403
    too_big = int(online["config"]["max_file_gb"] * 1024 ** 3) + 1
    r = requests.post(f"{url}/files", headers={**auth, "Upload-Length": str(too_big),
                                                "Upload-Metadata": f"path {b64('params.json')}"})
    assert r.status_code == 413


def test_checksum_mismatch_discards_upload(online):
    url, token = online["url"], online["token"]
    auth = {"Authorization": f"Bearer {token}", "Tus-Resumable": "1.0.0"}
    b64 = lambda s: __import__("base64").b64encode(s.encode()).decode()
    r = requests.post(f"{url}/files", headers={**auth, "Upload-Length": "3",
                      "Upload-Metadata": f"path {b64('params.json')},sha256 {b64('0' * 64)}"})
    loc = url.rsplit("/sync", 1)[0] + r.headers["Location"]
    r = requests.patch(loc, data=b"abc", headers={**auth, "Upload-Offset": "0",
                       "Content-Type": "application/offset+octet-stream"})
    assert r.status_code == 460
    assert not (online["ws"] / "params.json").exists()


def test_token_lifecycle(tmp_path):
    (tmp_path / "ws").mkdir()
    token, expires = tokens.issue(tmp_path, "ws", 1)
    assert tokens.resolve(tmp_path, token) == "ws"
    assert tokens.active_count(tmp_path, "ws") == 1
    # Only the hash is stored.
    assert token not in "".join(p.read_text() + p.name for p in (tmp_path / ".sync-tokens").iterdir())
    assert tokens.revoke(tmp_path, "ws") == 1
    assert tokens.resolve(tmp_path, token) is None
    old, _ = tokens.issue(tmp_path, "ws", -1)
    assert tokens.resolve(tmp_path, old) is None
    tokens.issue(tmp_path, "ws", -1)
    assert tokens.prune(tmp_path) == 1
    with pytest.raises(ValueError):
        tokens.issue(tmp_path, "../x", 1)
