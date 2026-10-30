"""Import from a link: listing, resumable downloads, archives, the SSRF guard.

A local HTTP server stands in for the object stores. It can refuse Range
requests, drop the connection partway through a file, and redirect.
"""
import gzip
import hashlib
import io
import json
import os
import tarfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import requests

from src.data_import import job, net, sources
from src.data_import.download import download, part_path
from src.data_import.remote import Probe, list_tar, list_zip, probe


class Server:
    def __init__(self):
        self.files = {}  # path -> (bytes, content type)
        self.ranges = True
        self.cut_once = {}  # path -> bytes after which the first full response breaks
        self.etags = {}
        self.redirects = {}
        self.requests = []

    def add(self, path, data, content_type="application/octet-stream"):
        self.files[path] = (data, content_type)
        self.etags[path] = '"' + hashlib.md5(data).hexdigest() + '"'

    def start(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                server.requests.append((self.path, self.headers.get("Range")))
                path = self.path.split("?", 1)[0]
                if self.path in server.files:
                    path = self.path
                if path in server.redirects:
                    self.send_response(302)
                    self.send_header("Location", server.redirects[path])
                    self.end_headers()
                    return
                if path not in server.files:
                    self.send_response(404)
                    self.end_headers()
                    return
                data, ctype = server.files[path]
                start, end = 0, len(data) - 1
                status = 200
                rng = self.headers.get("Range")
                if_range = self.headers.get("If-Range")
                if rng and server.ranges and (not if_range or if_range == server.etags[path]):
                    spec = rng.split("=", 1)[1]
                    a, _, b = spec.partition("-")
                    start = int(a)
                    end = int(b) if b else len(data) - 1
                    if start >= len(data):
                        self.send_response(416)
                        self.end_headers()
                        return
                    end = min(end, len(data) - 1)
                    status = 206
                body = data[start:end + 1]
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("ETag", server.etags[path])
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.end_headers()
                cut = server.cut_once.pop(path, None)
                if cut is not None and cut < len(body):
                    self.wfile.write(body[:cut])
                    self.wfile.flush()
                    self.connection.shutdown(2)
                    return
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"


@pytest.fixture
def server():
    s = Server().start()
    yield s
    s.httpd.shutdown()


def tar_bytes(members, gz=False):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz" if gz else "w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def zip_bytes(members, compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=compress) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


MZML_A = b"<mzML>a</mzML>" * 5000
MZML_B = os.urandom(1_000_000)
FASTA = b">P1\nPEPTIDE\n" * 100

TARGETS_TEMPLATE = {
    "mzML-files": {"name": "MS data", "file_types": ["mzML", "raw", "d"]},
    "fasta-file": {"name": "FASTA", "file_types": ["fasta"]},
}


def targets(tmp_path, fallback=None):
    out = {}
    for key, t in TARGETS_TEMPLATE.items():
        out[key] = {**t, "dir": str(Path(tmp_path, "input-files", key)),
                    "fallback": (fallback or {}).get(key, [])}
    return out


def plain():
    return net.make_session(guard=False)


def run(tmp_path, url, server_session=None, **kwargs):
    t = targets(tmp_path, kwargs.pop("fallback", None))
    listing = sources.resolve(server_session or plain(), url)
    items = job.build_items(listing.files, t)
    status = job.run_import(str(Path(tmp_path, "job")), items, t, guard=False, **kwargs)
    return listing, items, status, t


# ---------------------------------------------------------------------------
# Archives read in place
# ---------------------------------------------------------------------------

def test_tar_is_listed_in_place_and_members_download(tmp_path, server):
    server.add("/course/data.tar", tar_bytes({
        "data/run1.mzML": MZML_A, "data/run2.mzML": MZML_B, "data/db.fasta": FASTA,
        "data/readme.txt": b"hi", "../escape.mzML": b"x",
    }))
    listing, items, status, t = run(tmp_path, server.url("/course/data.tar"))
    assert [i["path"] for i in items] == [
        "data.tar/data/run1.mzML", "data.tar/data/run2.mzML", "data.tar/data/db.fasta",
        "data.tar/data/readme.txt"]
    assert [i["target"] for i in items] == ["mzML-files", "mzML-files", "fasta-file", ""]
    assert status["state"] == "done", status
    mzml = Path(t["mzML-files"]["dir"])
    assert Path(mzml, "run1.mzML").read_bytes() == MZML_A
    assert Path(mzml, "run2.mzML").read_bytes() == MZML_B
    assert Path(t["fasta-file"]["dir"], "db.fasta").read_bytes() == FASTA
    assert not Path(mzml, "escape.mzML").exists()
    # Only ranges were fetched, never the whole archive.
    assert all(r for p, r in server.requests if p == "/course/data.tar")


@pytest.mark.parametrize("compress", [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED])
def test_zip_members_download_by_range(tmp_path, server, compress):
    server.add("/z.zip", zip_bytes({"a/run1.mzML": MZML_A, "b/run2.mzML.gz": gzip.compress(MZML_B)},
                                   compress))
    _, items, status, t = run(tmp_path, server.url("/z.zip"))
    assert status["state"] == "done", status
    assert {i["name"] for i in items} == {"run1.mzML", "run2.mzML.gz"}
    mzml = Path(t["mzML-files"]["dir"])
    assert Path(mzml, "run1.mzML").read_bytes() == MZML_A
    assert Path(mzml, "run2.mzML").read_bytes() == MZML_B  # .gz unpacked


def test_bruker_folder_in_archive_is_one_item(tmp_path, server):
    server.add("/b.tar", tar_bytes({"x/sample.d/analysis.tdf": b"tdf", "x/sample.d/analysis.tdf_bin": MZML_B}))
    _, items, status, t = run(tmp_path, server.url("/b.tar"))
    assert len(items) == 1 and items[0]["kind"] == "folder" and items[0]["target"] == "mzML-files"
    folder = Path(t["mzML-files"]["dir"], "sample.d")
    assert Path(folder, "analysis.tdf").read_bytes() == b"tdf"
    assert Path(folder, "analysis.tdf_bin").read_bytes() == MZML_B


def test_archive_without_range_support_is_unpacked_after_download(tmp_path, server):
    server.ranges = False
    server.add("/all.tar.gz", tar_bytes({"r1.mzML": MZML_A, "notes.txt": b"n", "s.d/a.tdf": b"t"}, gz=True))
    listing, items, status, t = run(tmp_path, server.url("/all.tar.gz"))
    assert [i["kind"] for i in items] == ["archive"] and items[0]["target"] == "*"
    assert status["state"] == "done", status
    mzml = Path(t["mzML-files"]["dir"])
    assert Path(mzml, "r1.mzML").read_bytes() == MZML_A
    assert Path(mzml, "s.d", "a.tdf").read_bytes() == b"t"
    assert status["skipped"] == ["all.tar.gz/notes.txt"]


def test_tar_on_server_without_ranges_is_offered_whole(tmp_path, server):
    server.ranges = False
    server.add("/t.tar", tar_bytes({"r1.mzML": MZML_A}))
    listing = sources.resolve(plain(), server.url("/t.tar"))
    assert [f.path for f in listing.files] == ["t.tar"]
    assert "downloaded whole" in listing.notes[0]


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def test_download_resumes_after_a_dropped_connection(tmp_path, server):
    server.add("/big.mzML", MZML_B)
    server.cut_once["/big.mzML"] = 600_000
    retries = []
    dest = download(plain(), server.url("/big.mzML"), Path(tmp_path, "big.mzML"),
                    on_retry=retries.append, sleep=lambda s: None)
    assert dest.read_bytes() == MZML_B
    assert retries and "retrying" in retries[0]
    assert server.requests[-1][1] == "bytes=524288-"  # two whole chunks were kept


def test_part_file_from_an_earlier_run_is_resumed(tmp_path, server):
    server.add("/f.mzML", MZML_B)
    dest = Path(tmp_path, "f.mzML")
    part_path(dest).write_bytes(MZML_B[:5000])
    download(plain(), server.url("/f.mzML"), dest, etag=server.etags["/f.mzML"])
    assert dest.read_bytes() == MZML_B
    assert server.requests[-1][1] == "bytes=5000-"


def test_changed_file_starts_over(tmp_path, server):
    server.add("/f.mzML", MZML_B)
    dest = Path(tmp_path, "f.mzML")
    part_path(dest).write_bytes(b"stale bytes from an older version")
    download(plain(), server.url("/f.mzML"), dest, etag='"old-etag"')
    assert dest.read_bytes() == MZML_B


def test_size_limit_is_enforced(tmp_path, server):
    server.add("/f.mzML", MZML_B)
    _, _, status, t = run(tmp_path, server.url("/f.mzML"), max_bytes=1000)
    assert status["state"] == "failed"
    assert "limit" in status["errors"][0]
    assert not Path(t["mzML-files"]["dir"], "f.mzML").exists()


def test_checksum_mismatch_is_an_error(tmp_path, server):
    server.add("/f.mzML", MZML_A)
    t = targets(tmp_path)
    items = [{"id": "x", "name": "f.mzML", "path": "f.mzML", "kind": "file", "size": len(MZML_A),
              "target": "mzML-files",
              "files": [{"path": "f.mzML", "size": len(MZML_A), "url": server.url("/f.mzML"),
                         "md5": "0" * 32}]}]
    status = job.run_import(str(Path(tmp_path, "job")), items, t, guard=False)
    assert status["state"] == "failed" and "checksum" in status["errors"][0]


def test_example_files_are_replaced_by_the_import(tmp_path, server):
    server.add("/f.mzML", MZML_A)
    mzml = Path(tmp_path, "input-files", "mzML-files")
    mzml.mkdir(parents=True)
    Path(mzml, "example.mzML").write_text("example")
    run(tmp_path, server.url("/f.mzML"), fallback={"mzML-files": ["example.mzML"]})
    assert sorted(p.name for p in mzml.iterdir()) == ["f.mzML"]


def test_cancel_stops_the_job(tmp_path, server):
    server.add("/f.mzML", MZML_A)
    job_dir = Path(tmp_path, "job")
    t = targets(tmp_path)
    items = job.build_items(sources.resolve(plain(), server.url("/f.mzML")).files, t)

    original = job._Job.cancelled
    job._Job.cancelled = lambda self: True
    try:
        status = job.run_import(str(job_dir), items, t, guard=False)
    finally:
        job._Job.cancelled = original
    assert status["state"] == "cancelled"
    assert job.read_status(job_dir)["state"] == "cancelled"


def test_status_tells_a_live_job_from_an_interrupted_one():
    import time
    assert job.is_running({"state": "running", "heartbeat": time.time()})
    stale = {"state": "running", "heartbeat": time.time() - 120}
    assert not job.is_running(stale) and job.is_interrupted(stale)


# ---------------------------------------------------------------------------
# Unpacking safety
# ---------------------------------------------------------------------------

def test_unpack_skips_links_and_escaping_paths(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, kind in (("ok.mzML", tarfile.REGTYPE), ("../../evil.mzML", tarfile.REGTYPE),
                           ("/abs.mzML", tarfile.REGTYPE), ("link.mzML", tarfile.SYMTYPE)):
            info = tarfile.TarInfo(name)
            info.type = kind
            data = b"" if kind == tarfile.SYMTYPE else b"data"
            if kind == tarfile.SYMTYPE:
                info.linkname = "/etc/passwd"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    archive = Path(tmp_path, "a.tar")
    archive.write_bytes(buf.getvalue())
    out = Path(tmp_path, "out")
    job._unpack(archive, out, None)
    assert sorted(str(p.relative_to(out)) for p in out.rglob("*")) == ["ok.mzML"]
    assert not Path(tmp_path, "evil.mzML").exists()


def test_unpack_refuses_a_zip_bomb(tmp_path):
    archive = Path(tmp_path, "bomb.zip")
    archive.write_bytes(zip_bytes({"zeros.mzML": b"\0" * 20_000_000}))
    with pytest.raises(IOError, match="allowed size"):
        job._unpack(archive, Path(tmp_path, "out"), 5_000_000)


def test_member_paths_are_confined():
    from src.data_import.remote import safe_member_path
    assert safe_member_path("a/./b.mzML") == "a/b.mzML"
    assert safe_member_path("../b") is None
    assert safe_member_path("/etc/passwd") is None
    assert safe_member_path("a\\..\\..\\b") is None


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/", "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/", "http://[::1]/", "http://100.64.0.1/", "http://[::ffff:127.0.0.1]/",
])
def test_private_addresses_are_refused(url):
    with pytest.raises(net.BlockedURL):
        net.check_url(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.org/x", "gopher://x/"])
def test_other_schemes_are_refused(url):
    with pytest.raises(net.BlockedURL):
        net.check_url(url, resolve=False)


def test_guarded_session_refuses_loopback(server):
    server.add("/f.mzML", MZML_A)
    with pytest.raises(net.BlockedURL):
        net.make_session(guard=True).get(server.url("/f.mzML"))


def test_redirect_to_a_private_address_is_refused(server, monkeypatch):
    # 127.0.0.1 plays the public server; the redirect goes to 127.0.0.2.
    monkeypatch.setattr(net, "is_public_address", lambda ip: ip != "127.0.0.2")
    server.add("/f.mzML", MZML_A)
    server.redirects["/go"] = f"http://127.0.0.2:{server.port}/f.mzML"
    session = net.make_session(guard=True)
    assert session.get(server.url("/f.mzML")).content == MZML_A
    with pytest.raises(net.BlockedURL):
        session.get(server.url("/go"))


def test_allowed_hosts():
    net.check_url("https://a3s.fi/x", ["a3s.fi"], resolve=False)
    net.check_url("https://sub.zenodo.org/x", ["zenodo.org"], resolve=False)
    with pytest.raises(net.BlockedURL):
        net.check_url("https://evil-a3s.fi/x", ["a3s.fi"], resolve=False)


def test_redact_drops_signatures():
    assert net.redact("https://user:pw@a3s.fi:443/b/o.tar?X-Amz-Signature=abc") == "https://a3s.fi:443/b/o.tar"


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def test_web_page_is_not_a_file(server):
    server.add("/page", b"<html></html>", "text/html")
    with pytest.raises(LookupError, match="web page"):
        sources.resolve(plain(), server.url("/page"))


def test_swift_container_listing(server):
    listing_json = json.dumps([
        {"name": "course/run1.mzML", "bytes": 10, "hash": "a" * 32},
        {"subdir": "course/deeper/"},
        {"name": "course/db.fasta", "bytes": 5, "hash": "b" * 32},
    ]).encode()
    server.add("/swift/v1/bucket?format=json&limit=10000&prefix=course%2F", listing_json, "application/json")
    listing = sources.resolve(plain(), server.url("/swift/v1/bucket/course/"))
    assert [(f.path, f.size, f.md5) for f in listing.files] == [
        ("run1.mzML", 10, "a" * 32), ("db.fasta", 5, "b" * 32)]
    assert listing.files[0].url == server.url("/swift/v1/bucket/course/run1.mzML")


def test_s3_bucket_listing(server):
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>b</Name><IsTruncated>false</IsTruncated>
<Contents><Key>data/run1.mzML</Key><Size>12</Size><ETag>"0123456789abcdef0123456789abcdef"</ETag></Contents>
<Contents><Key>data/</Key><Size>0</Size></Contents>
</ListBucketResult>"""
    server.add("/b?list-type=2&prefix=data%2F&max-keys=1000", xml, "application/xml")
    listing = sources.resolve(plain(), server.url("/b/data"))
    assert [(f.path, f.size, f.md5) for f in listing.files] == [
        ("run1.mzML", 12, "0123456789abcdef0123456789abcdef")]
    assert listing.files[0].url == server.url("/b/data/run1.mzML")


def test_zenodo_record(monkeypatch):
    calls = []

    def fake_json(session, url, **kwargs):
        calls.append(url)
        return {"metadata": {"title": "Course data"}, "files": [
            {"key": "runs.tar", "size": 100, "checksum": "md5:" + "c" * 32,
             "links": {"self": "https://zenodo.org/api/records/123/files/runs.tar/content"}}]}

    monkeypatch.setattr(sources, "_json", fake_json)
    monkeypatch.setattr(sources, "_open_archives", lambda session, listing: None)
    for link in ("https://zenodo.org/records/123", "10.5281/zenodo.123", "https://doi.org/10.5281/zenodo.123"):
        listing = sources.resolve(plain(), link)
        assert listing.title == "Zenodo: Course data"
        assert [(f.path, f.size, f.md5) for f in listing.files] == [("runs.tar", 100, "c" * 32)]
    assert set(calls) == {"https://zenodo.org/api/records/123"}


def test_figshare_article(monkeypatch):
    monkeypatch.setattr(sources, "_json", lambda session, url, **kw: {
        "title": "Spectra", "url_public_html": "https://figshare.com/articles/dataset/x/456",
        "files": [{"name": "a.mzML", "size": 7, "computed_md5": "d" * 32,
                   "download_url": "https://ndownloader.figshare.com/files/1"}]})
    for link in ("https://figshare.com/articles/dataset/Spectra/456", "10.6084/m9.figshare.456.v2"):
        listing = sources.resolve(plain(), link)
        assert [(f.path, f.url) for f in listing.files] == [("a.mzML", "https://ndownloader.figshare.com/files/1")]


def test_probe_reads_size_and_range_support(server):
    server.add("/x.tar", b"0" * 2048)
    info = probe(plain(), server.url("/x.tar?X-Amz-Signature=abc"))
    assert (info.name, info.size, info.ranges) == ("x.tar", 2048, True)


def test_onedrive_personal_folder_is_walked(monkeypatch):
    api = sources.ONEDRIVE_API
    link = "https://1drv.ms/f/s!AbCdEf"
    pages = {
        f"{api}/shares/{sources.share_id(link)}/root?$expand=children": {
            "name": "Course", "folder": {"childCount": 3},
            "children": [
                {"name": "run1.mzML", "size": 5, "file": {"hashes": {"md5Hash": "AB" * 16}},
                 "@content.downloadUrl": "https://dl.example/run1"},
                {"name": "sample.d", "id": "D1", "folder": {"childCount": 1},
                 "parentReference": {"driveId": "drv"}},
                {"name": "..", "size": 1, "file": {}, "@content.downloadUrl": "https://dl.example/x"},
            ],
            "children@odata.nextLink": f"{api}/next",
        },
        f"{api}/next": {"value": [{"name": "db.fasta", "size": 3, "file": {},
                                   "@content.downloadUrl": "https://dl.example/db"}]},
        f"{api}/drives/drv/items/D1/children": {"value": [
            {"name": "analysis.tdf", "size": 2, "file": {}, "@content.downloadUrl": "https://dl.example/tdf"}]},
    }
    monkeypatch.setattr(sources, "_json", lambda session, url, **kw: pages[url])
    monkeypatch.setattr(sources, "_open_archives", lambda session, listing: None)
    listing = sources.resolve(plain(), link)
    assert listing.title == "OneDrive: Course"
    assert [(f.path, f.url, f.md5) for f in listing.files] == [
        ("run1.mzML", "https://dl.example/run1", "ab" * 16),
        ("sample.d/analysis.tdf", "https://dl.example/tdf", ""),
        ("db.fasta", "https://dl.example/db", ""),
    ]
    items = job.build_items(listing.files, targets(Path("/tmp")))
    assert [(i["name"], i["kind"]) for i in items] == [
        ("run1.mzML", "file"), ("sample.d", "folder"), ("db.fasta", "file")]


def test_sharepoint_file_link_is_fetched_with_download(monkeypatch):
    def no_api(session, url, **kw):
        raise AssertionError("SharePoint links must not go to the shares API")

    seen = []

    def fake_probe(session, url):
        seen.append(url)
        return Probe(name="run.mzML", size=10, ranges=True, etag='"e"')

    monkeypatch.setattr(sources, "_json", no_api)
    monkeypatch.setattr(sources, "probe", fake_probe)
    link = "https://uni-my.sharepoint.com/:u:/g/personal/x/EAbc?e=XyZ"
    listing = sources.resolve(plain(), link)
    assert seen == ["https://uni-my.sharepoint.com/:u:/g/personal/x/EAbc?e=XyZ&download=1"]
    assert listing.files[0].url == seen[0]


def test_onedrive_page_that_needs_sign_in_is_explained(monkeypatch):
    def denied(session, url, **kw):
        raise requests.HTTPError("401")

    monkeypatch.setattr(sources, "_json", denied)
    monkeypatch.setattr(sources, "probe", lambda session, url: Probe(
        name="x", size=None, ranges=False, etag="", content_type="text/html"))
    with pytest.raises(LookupError, match="Anyone with the link"):
        sources.resolve(plain(), "https://onedrive.live.com/?id=ABC&cid=DEF")
