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


class FlakySession(requests.Session):
    """Loses every other PATCH response after the server got the chunk, and
    breaks every download stream after its first block."""

    def __init__(self):
        super().__init__()
        self.patches = 0
        self.broken_streams = 0

    def request(self, method, url, *args, **kwargs):
        resp = super().request(method, url, *args, **kwargs)
        if method == "PATCH":
            self.patches += 1
            if self.patches % 2 == 1:
                raise requests.ConnectionError("response lost")
        if method == "GET" and "download" in url and kwargs.get("stream"):
            original = resp.iter_content
            session = self

            def broken(chunk_size=1, decode_unicode=False):
                it = original(chunk_size)
                yield next(it)
                session.broken_streams += 1
                raise requests.exceptions.ChunkedEncodingError("connection reset")

            resp.iter_content = broken
        return resp


def test_transfers_survive_connection_loss(online, tmp_path, monkeypatch):
    monkeypatch.setattr(client.SyncClient, "_sleep", lambda self, s: None)
    ws = _local_workspace(tmp_path)
    notices = []
    c = client.SyncClient(online["url"], online["token"], session=FlakySession(),
                          chunk_size=MB, notice=notices.append)
    c.push(ws)
    rel = "topp-workflow/input-files/mzML-files/a.mzML"
    assert (online["ws"] / rel).read_bytes() == (ws / rel).read_bytes()
    assert any("Connection lost" in n for n in notices)

    res = online["ws"] / "topp-workflow" / "results"
    res.mkdir(parents=True)
    data = os.urandom(3 * MB)
    (res / "big.bin").write_bytes(data)
    c.pull(ws, ["topp-workflow/results/big.bin"])
    assert (ws / "topp-workflow/results/big.bin").read_bytes() == data
    assert c.session.broken_streams >= 3


def test_items_and_selective_transfer(online, tmp_path):
    ws = _local_workspace(tmp_path)
    c = client.SyncClient(online["url"], online["token"], chunk_size=MB)
    items = {i.key: i for i in c.input_items(ws)}
    assert set(items) == {
        "Parameters",
        "topp-workflow/Parameters",
        "topp-workflow/input-files/mzML-files/a.mzML",
        "topp-workflow/input-files/mzML-files/b.raw",
        "topp-workflow/input-files/mzML-files/run.d",
    }
    assert items["topp-workflow/input-files/mzML-files/run.d"].files.__len__() == 2
    assert all(i.state == client.NOT_ON_SERVER for i in items.values())

    report = c.push(ws, ["topp-workflow/input-files/mzML-files/run.d"])
    assert len(report.transferred) == 2
    states = {i.key: i.state for i in c.input_items(ws)}
    assert states["topp-workflow/input-files/mzML-files/run.d"] == client.ON_SERVER
    assert states["topp-workflow/input-files/mzML-files/a.mzML"] == client.NOT_ON_SERVER

    (ws / "topp-workflow" / "params.json").write_text('{"x": 2}')
    c.push(ws, ["topp-workflow/Parameters"])
    (ws / "topp-workflow" / "params.json").write_text('{"x": 3}')
    states = {i.key: i.state for i in c.input_items(ws)}
    assert states["topp-workflow/Parameters"] == client.CHANGED_LOCALLY
    assert states["Parameters"] == client.NOT_ON_SERVER
    assert {i.workflow for i in c.input_items(ws)} == {"", "topp-workflow"}

    # A paused upload shows how far it got.
    cancel = threading.Event()
    with pytest.raises(client.Cancelled):
        c.push(ws, ["topp-workflow/input-files/mzML-files/a.mzML"], cancel=cancel,
               progress=lambda d, t, r: cancel.set() if d >= MB else None)
    states = {i.key: i.state for i in c.input_items(ws)}
    assert states["topp-workflow/input-files/mzML-files/a.mzML"].startswith("Paused at")

    res = online["ws"] / "wf" / "results"
    res.mkdir(parents=True)
    (res / "one.tsv").write_text("1")
    (res / "two.tsv").write_text("2")
    assert {i.state for i in c.result_items(ws)} == {client.NOT_DOWNLOADED}
    c.pull(ws, ["wf/results/two.tsv"])
    states = {i.key: i.state for i in c.result_items(ws)}
    assert states == {"wf/results/one.tsv": client.NOT_DOWNLOADED,
                      "wf/results/two.tsv": client.DOWNLOADED}
    (res / "two.tsv").write_text("22")
    assert {i.key: i.state for i in c.result_items(ws)}["wf/results/two.tsv"] == client.CHANGED_ON_SERVER


def test_half_chunk_with_checksum_is_discarded(online):
    """A connection dropped mid-chunk must not leave unverified bytes."""
    import base64, hashlib
    url, token = online["url"], online["token"]
    auth = {"Authorization": f"Bearer {token}", "Tus-Resumable": "1.0.0"}
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    r = requests.post(f"{url}/files", headers={**auth, "Upload-Length": str(2 * MB),
                      "Upload-Metadata": f"path {b64('params.json')}"})
    location = r.headers["Location"]
    port = int(url.split(":")[2].split("/")[0])
    body = os.urandom(MB)
    checksum = base64.b64encode(hashlib.sha256(body).digest()).decode()
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall((f"PATCH {location} HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {token}\r\n"
                   f"Tus-Resumable: 1.0.0\r\nContent-Type: application/offset+octet-stream\r\n"
                   f"Upload-Offset: 0\r\nUpload-Checksum: sha256 {checksum}\r\n"
                   f"Content-Length: {MB}\r\n\r\n").encode() + body[: MB // 2])
        time.sleep(0.3)
    time.sleep(0.3)
    head = requests.head(url.rsplit("/sync", 1)[0] + location, headers=auth)
    assert head.headers["Upload-Offset"] == "0"
    # A complete chunk with a wrong checksum is refused and dropped too.
    r = requests.patch(url.rsplit("/sync", 1)[0] + location, data=body, headers={
        **auth, "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream",
        "Upload-Checksum": "sha256 " + base64.b64encode(b"\0" * 32).decode()})
    assert r.status_code == 460
    head = requests.head(url.rsplit("/sync", 1)[0] + location, headers=auth)
    assert head.headers["Upload-Offset"] == "0"


def test_incoming_lists_unfinished_uploads(online, tmp_path):
    ws = _local_workspace(tmp_path)
    c = client.SyncClient(online["url"], online["token"], chunk_size=MB)
    cancel = threading.Event()

    def stop_after_first_chunk(done, total, rel):
        if rel.endswith("a.mzML") and done >= MB:
            cancel.set()

    with pytest.raises(client.Cancelled):
        c.push(ws, ["topp-workflow/input-files/mzML-files/a.mzML"],
               progress=stop_after_first_chunk, cancel=cancel)
    [upload] = server.incoming(online["root"], "ws-online")
    assert upload["path"] == "topp-workflow/input-files/mzML-files/a.mzML"
    assert 0 < upload["offset"] < upload["length"] and upload["active"]
    assert server.incoming(online["root"], "other") == []
    assert not server.incoming(online["root"], "ws-online", active_within=-1)[0]["active"]
    c.push(ws, ["topp-workflow/input-files/mzML-files/a.mzML"])
    assert server.incoming(online["root"], "ws-online") == []


def _wait_for_job(ui, ws, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = ui._JOBS.get(str(ws))
        if job is not None and job.finished:
            return job
        time.sleep(0.05)
    raise AssertionError("transfer did not finish")


def test_sync_follows_chosen_directions(online, tmp_path, monkeypatch):
    from src.common import workspace_sync as ui

    monkeypatch.setattr(ui, "_settings", lambda: server.sync_settings({}))
    ws = _local_workspace(tmp_path)
    res = online["ws"] / "topp-workflow" / "results"
    res.mkdir(parents=True)
    (res / "out.tsv").write_text("result")
    link = {"url": online["url"], "token": online["token"]}
    c = client.SyncClient(online["url"], online["token"])

    # Inputs of topp-workflow stay local; its results come down.
    prefs = client.read_prefs(ws)
    prefs["workflows"]["topp-workflow"] = {"push": False}
    client.write_prefs(ws, prefs)
    prefs = client.read_prefs(ws)
    status = ui._compute_status(ws, c)
    up, down = ui._chosen(status, prefs)
    assert {i.key for i in up} == {"Parameters"}
    assert [i.key for i in down] == ["topp-workflow/results/out.tsv"]

    ui._STATUS[str(ws)] = {"at": time.time()}
    ui._start(ws, "sync", [i.key for i in up + down], link)
    job = _wait_for_job(ui, ws)
    assert not job.error, job.error
    assert set(job.report.transferred) == {"params.json", "topp-workflow/results/out.tsv"}
    assert (ws / "topp-workflow/results/out.tsv").read_text() == "result"
    assert not (online["ws"] / "topp-workflow" / "input-files").exists()
    # The states shown in the sidebar are stale now and get recomputed.
    assert str(ws) not in ui._STATUS

    status = ui._compute_status(ws, c)
    assert ui._chosen(status, prefs, pending_only=True) == ([], [])
    assert ui._STATUS[str(ws)] is status


def test_keep_in_sync_loop(online, tmp_path, monkeypatch):
    from src.common import workspace_sync as ui

    monkeypatch.setattr(ui, "_settings", lambda: server.sync_settings({}))
    monkeypatch.setattr(ui, "_WATCH_INTERVAL", 0.2)
    ws = _local_workspace(tmp_path)
    client.write_link(ws, {"url": online["url"], "token": online["token"], "uploads": {}})
    client.write_prefs(ws, {"keep_in_sync": True, "workflows": {}})
    ui._ensure_watcher(ws)

    def wait_until(check, timeout=30):
        deadline = time.time() + timeout
        while not check():
            assert time.time() < deadline, "keep in sync did not catch up"
            time.sleep(0.1)

    remote = online["ws"]
    wait_until(lambda: (remote / "topp-workflow/input-files/mzML-files/a.mzML").is_file())
    # A result appearing online comes down without a click.
    (remote / "topp-workflow" / "results").mkdir(parents=True)
    (remote / "topp-workflow" / "results" / "new.tsv").write_text("fresh")
    wait_until(lambda: (ws / "topp-workflow/results/new.tsv").is_file()
               and (ws / "topp-workflow/results/new.tsv").read_text() == "fresh")
    assert ui._JOBS[str(ws)].auto

    # Clearing the box ends the loop.
    client.write_prefs(ws, {"keep_in_sync": False, "workflows": {}})
    wait_until(lambda: not ui._WATCHERS[str(ws)].is_alive())
    wait_until(lambda: ui._JOBS[str(ws)].finished)
