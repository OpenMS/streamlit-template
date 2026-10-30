"""HTTP service that online workspaces expose for workspace sync.

Runs as its own process next to Streamlit (``python -m src.sync.server``),
on the same image and the same workspaces volume, routed at ``/sync``.

    GET    /sync/health                      liveness, no auth
    GET    /sync/manifest?scope=push|pull    {path: {size, sha256}} of the workspace
    OPTIONS/POST /sync/files                 tus 1.0.0 creation
    HEAD/PATCH/DELETE /sync/files/<id>       tus 1.0.0 core + termination
    GET/HEAD /sync/download?path=<rel>       a result file, with Range support
    GET    /sync/runs                        state of the runnable workflows
    POST   /sync/runs/<workflow>             queue a run with the given params
    DELETE /sync/runs/<workflow>             stop it (see runs.py)

Each PATCH may carry ``Upload-Checksum: sha256 <base64>`` (tus checksum
extension). A chunk that fails it, or whose connection drops before it is
complete, is cut back off the partial file, so only verified chunks are ever
kept; the whole file is checked against its sha256 once more at the end.

Every call but health carries ``Authorization: Bearer <sync token>``; the
token decides the workspace. Partial uploads live under
``<root>/.sync-uploads/`` on the shared volume, so any replica can continue
an upload another one started, and a finished upload is renamed into the
workspace without a copy.
"""

import argparse
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path

try:
    import fcntl
except ImportError:     # Windows: the desktop app imports this module, never serves it
    fcntl = None

import tornado.ioloop
import tornado.web

from src.sync import paths, runs, tokens

logger = logging.getLogger("workspace-sync")

TUS_VERSION = "1.0.0"
UPLOAD_DIR = ".sync-uploads"
INDEX_FILE = ".sync-index.json"
DOWNLOAD_BLOCK = 1024 * 1024
# A PATCH body is streamed to disk, so this only bounds a single request;
# the client sends far smaller chunks.
MAX_REQUEST_BYTES = 1024 ** 3
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")

DEFAULTS = {
    "enabled": False,
    "public_url": "",
    "token_ttl_hours": 24,
    "max_file_gb": 50,
    "max_workspace_gb": 200,
    "chunk_mb": 32,
    # Workflows the desktop app may run here: directory name -> "module:Class".
    "workflows": {},
}


def sync_settings(settings: dict) -> dict:
    """``workspace_sync`` from settings.json with defaults filled in."""
    return {**DEFAULTS, **(settings.get("workspace_sync") or {})}


def _decode_metadata(header: str) -> dict[str, str]:
    meta = {}
    for pair in filter(None, (p.strip() for p in header.split(","))):
        key, _, value = pair.partition(" ")
        try:
            meta[key] = base64.b64decode(value).decode() if value else ""
        except ValueError:
            raise tornado.web.HTTPError(400, "bad Upload-Metadata")
    return meta


def _workspace_bytes(workspace: Path) -> int:
    total = 0
    for root, _, files in os.walk(workspace):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


class SyncHandler(tornado.web.RequestHandler):
    def initialize(self, root: Path, config: dict):
        self.root = Path(root)
        self.config = config

    def set_default_headers(self):
        self.set_header("Tus-Resumable", TUS_VERSION)
        self.set_header("Cache-Control", "no-store")

    def write_error(self, status_code, **kwargs):
        reason = self._reason
        if "exc_info" in kwargs and isinstance(kwargs["exc_info"][1], tornado.web.HTTPError):
            reason = kwargs["exc_info"][1].log_message or reason
        self.finish({"error": reason})

    def workspace(self) -> Path:
        auth = self.request.headers.get("Authorization", "")
        scheme, _, token = auth.partition(" ")
        name = tokens.resolve(self.root, token.strip()) if scheme.lower() == "bearer" else None
        if name is None:
            raise tornado.web.HTTPError(401, "missing, unknown or expired sync token")
        return Path(self.root, name)

    def hash_cache(self, workspace: Path) -> paths.HashCache:
        return paths.HashCache(Path(workspace, INDEX_FILE))


class HealthHandler(SyncHandler):
    def get(self):
        status = "ok" if self.config["enabled"] else "disabled"
        self.finish({"status": status, "tus": TUS_VERSION})


class ManifestHandler(SyncHandler):
    async def get(self):
        workspace = self.workspace()
        scope = self.get_query_argument("scope", "push")
        if scope not in ("push", "pull"):
            raise tornado.web.HTTPError(400, "scope must be push or pull")

        def build():
            entries = (paths.push_entries if scope == "push" else paths.pull_entries)(workspace)
            cache = self.hash_cache(workspace)
            manifest = cache.manifest(entries)
            cache.save()
            return manifest

        # A result an online run just wrote is hashed here for the first
        # time; a multi-GB one must not stall every other request.
        manifest = await tornado.ioloop.IOLoop.current().run_in_executor(None, build)
        self.finish({"workspace": workspace.name, "files": manifest})


class _Upload:
    """State of one tus upload: ``<id>.json`` beside the ``<id>.part`` data."""

    def __init__(self, root: Path, upload_id: str):
        if not _UPLOAD_ID.match(upload_id):
            raise tornado.web.HTTPError(404)
        base = Path(root, UPLOAD_DIR)
        self.state_file = Path(base, upload_id + ".json")
        self.part = Path(base, upload_id + ".part")
        self.id = upload_id
        self.lock = Path(base, upload_id + ".lock")
        self._lock_fd = None
        try:
            self.state = json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            raise tornado.web.HTTPError(404, "unknown upload")

    @property
    def offset(self) -> int:
        if self.state.get("completed"):
            return self.state["length"]
        try:
            return self.part.stat().st_size
        except FileNotFoundError:
            return 0

    def remove(self):
        self.part.unlink(missing_ok=True)
        self.state_file.unlink(missing_ok=True)
        self.lock.unlink(missing_ok=True)

    def acquire(self) -> None:
        """Take the upload's write lock, or answer 423.

        A client whose PATCH timed out sends it again, maybe to another
        replica, while the first may still be writing. Both would pass the
        offset check and append to the same partial file. The lock is a POSIX
        record lock on ``<id>.lock``: NFS 4.1 grants it across replicas, it
        is held for as long as the request keeps the file open, and the
        kernel (or the NFS lease, for a pod that died) releases it, so no
        writer can lose it while still writing and none needs breaking.
        Record locks are per process, hence ``_HELD`` for the requests of
        this one. The file is never unlinked while the upload exists:
        unlinking would let two writers lock two different files.
        """
        if self.id in _HELD:
            raise tornado.web.HTTPError(423, "another request is writing this upload")
        fd = os.open(self.lock, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            if fcntl is not None:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise tornado.web.HTTPError(423, "another request is writing this upload")
        self._lock_fd = fd
        _HELD.add(self.id)

    def release(self) -> None:
        if self._lock_fd is not None:
            _HELD.discard(self.id)
            os.close(self._lock_fd)         # closing releases the record lock
            self._lock_fd = None


_HELD: set = set()      # uploads a request of this process is writing


class UploadsHandler(SyncHandler):
    def options(self):
        self.set_header("Tus-Version", TUS_VERSION)
        self.set_header("Tus-Extension", "creation,termination,checksum")
        self.set_header("Tus-Checksum-Algorithm", "sha256")
        self.set_header("Tus-Max-Size", str(int(self.config["max_file_gb"] * 1024 ** 3)))
        self.set_status(204)

    async def post(self):
        workspace = self.workspace()
        try:
            length = int(self.request.headers["Upload-Length"])
        except (KeyError, ValueError):
            raise tornado.web.HTTPError(400, "Upload-Length required")
        meta = _decode_metadata(self.request.headers.get("Upload-Metadata", ""))
        rel = meta.get("path", "")
        if not paths.is_pushable(rel):
            raise tornado.web.HTTPError(403, f"path not accepted for upload: {rel!r}")
        if length < 0 or length > self.config["max_file_gb"] * 1024 ** 3:
            raise tornado.web.HTTPError(413, "file exceeds the per-file limit")
        dest = Path(workspace, rel)
        replaced = dest.stat().st_size if dest.is_file() else 0
        # A walk over the whole workspace on NFS: not on the event loop.
        used = await tornado.ioloop.IOLoop.current().run_in_executor(
            None, _workspace_bytes, workspace)
        if used - replaced + length > self.config["max_workspace_gb"] * 1024 ** 3:
            raise tornado.web.HTTPError(413, "workspace storage limit reached")

        upload_id = secrets.token_hex(16)
        base = Path(self.root, UPLOAD_DIR)
        base.mkdir(parents=True, exist_ok=True)
        Path(base, upload_id + ".part").touch()
        Path(base, upload_id + ".json").write_text(json.dumps({
            "workspace": workspace.name,
            "path": rel,
            "length": length,
            "sha256": meta.get("sha256", ""),
            "created": time.time(),
        }))
        self.set_status(201)
        self.set_header("Location", f"{self.request.path.rstrip('/')}/{upload_id}")
        self.set_header("Upload-Offset", "0")
        if length == 0:
            self._finish_upload(workspace, _Upload(self.root, upload_id))
        self.finish()

    def _finish_upload(self, workspace, upload):
        finalize(workspace, upload, self.hash_cache(workspace))


def incoming(root: Path, workspace: str, active_within: float = 120) -> list[dict]:
    """The unfinished uploads into one workspace, for the online app to show.

    ``active`` marks an upload that received data within ``active_within``
    seconds; the others are paused until the desktop app continues them.
    """
    found = []
    now = time.time()
    for state_file in Path(root, UPLOAD_DIR).glob("*.json"):
        try:
            state = json.loads(state_file.read_text())
            part = state_file.with_suffix(".part").stat()
        except (OSError, ValueError):
            continue
        if state.get("workspace") != workspace or state.get("completed"):
            continue
        found.append({"path": state.get("path", ""), "length": state.get("length", 0),
                      "offset": part.st_size, "active": now - part.st_mtime < active_within})
    return sorted(found, key=lambda u: u["path"])


def finalize(workspace: Path, upload: _Upload, cache: paths.HashCache) -> None:
    """Verify a complete upload and rename it into the workspace."""
    expected = upload.state.get("sha256")
    digest = paths.sha256_file(upload.part)
    if expected and digest != expected:
        upload.remove()
        raise tornado.web.HTTPError(460, "checksum mismatch, upload discarded", reason="Checksum Mismatch")
    dest = Path(workspace, upload.state["path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.is_dir():
        # Demo data is linked in, never overwritten through the link.
        if dest.is_dir() and not dest.is_symlink():
            raise tornado.web.HTTPError(409, "a folder exists at this path")
        dest.unlink()
    os.replace(upload.part, dest)
    # Keep the state, marked complete: a client whose last response was lost
    # asks again and learns the upload is done instead of "unknown upload".
    # clean-up-workspaces.py removes it later.
    upload.state["completed"] = True
    upload.state_file.write_text(json.dumps(upload.state))
    cache.remember(dest, digest)
    cache.save()
    # Restart the workspace's 7-day cleanup clock.
    os.utime(workspace)


@tornado.web.stream_request_body
class UploadHandler(SyncHandler):
    _fh = None
    _hash = None
    _start = 0

    def prepare(self):
        self._upload_workspace = self.workspace()
        upload_id = self.path_args[0] if self.path_args else ""
        self._upload = _Upload(self.root, upload_id)
        if self._upload.state.get("workspace") != self._upload_workspace.name:
            raise tornado.web.HTTPError(404, "unknown upload")
        if self.request.method != "PATCH":
            return
        if self.request.headers.get("Content-Type") != "application/offset+octet-stream":
            raise tornado.web.HTTPError(415, "Content-Type must be application/offset+octet-stream")
        try:
            offset = int(self.request.headers["Upload-Offset"])
        except (KeyError, ValueError):
            raise tornado.web.HTTPError(400, "Upload-Offset required")
        self._upload.acquire()
        if offset != self._upload.offset or self._upload.state.get("completed"):
            raise tornado.web.HTTPError(409, "Upload-Offset does not match")
        checksum = self.request.headers.get("Upload-Checksum")
        if checksum:
            algorithm, _, value = checksum.partition(" ")
            if algorithm != "sha256":
                raise tornado.web.HTTPError(400, "only sha256 checksums are supported")
            try:
                self._expected = base64.b64decode(value)
            except ValueError:
                raise tornado.web.HTTPError(400, "bad Upload-Checksum")
            self._hash = hashlib.sha256()
        self._start = offset
        self._remaining = self._upload.state["length"] - offset
        self._fh = open(self._upload.part, "ab")

    def data_received(self, chunk):
        if self._fh is None:
            return
        if len(chunk) > self._remaining:
            self._discard_chunk()
            raise tornado.web.HTTPError(400, "body exceeds Upload-Length")
        self._fh.write(chunk)
        if self._hash is not None:
            self._hash.update(chunk)
        self._remaining -= len(chunk)

    def _close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def _unlock(self):
        upload = getattr(self, "_upload", None)
        if upload is not None:
            upload.release()

    def _discard_chunk(self):
        """Cut an unverified chunk back off the partial file."""
        self._close()
        with open(self._upload.part, "r+b") as f:
            f.truncate(self._start)

    def on_connection_close(self):
        # Without a checksum whatever arrived is kept and the client resumes
        # from HEAD; with one, a half chunk cannot be verified and is dropped.
        if self._hash is not None and self._fh is not None:
            self._discard_chunk()
        self._close()
        self._unlock()

    def on_finish(self):
        self._close()
        self._unlock()

    def head(self, upload_id):
        self.set_header("Upload-Offset", str(self._upload.offset))
        self.set_header("Upload-Length", str(self._upload.state["length"]))
        self.set_status(200)

    async def patch(self, upload_id):
        self._close()
        if self._hash is not None and self._hash.digest() != self._expected:
            self._discard_chunk()
            raise tornado.web.HTTPError(460, "chunk checksum mismatch", reason="Checksum Mismatch")
        offset = self._upload.offset
        if offset == self._upload.state["length"]:
            # Hashing a multi-GB file must not stall every other request.
            await tornado.ioloop.IOLoop.current().run_in_executor(
                None, finalize, self._upload_workspace, self._upload,
                self.hash_cache(self._upload_workspace),
            )
        self.set_header("Upload-Offset", str(offset))
        self.set_status(204)

    def delete(self, upload_id):
        self._upload.remove()
        self.set_status(204)


class DownloadHandler(SyncHandler):
    def _target(self) -> Path:
        workspace = self.workspace()
        rel = self.get_query_argument("path", "")
        if not paths.is_pullable(rel):
            raise tornado.web.HTTPError(403, f"path not offered for download: {rel!r}")
        target = Path(workspace, rel)
        if not target.is_file():
            raise tornado.web.HTTPError(404, "no such file")
        return target

    def _range(self, size: int) -> tuple[int, int]:
        header = self.request.headers.get("Range")
        if not header:
            return 0, size
        m = re.fullmatch(r"bytes=(\d+)-(\d*)", header.strip())
        if not m:
            raise tornado.web.HTTPError(416)
        start = int(m.group(1))
        end = int(m.group(2)) + 1 if m.group(2) else size
        end = min(end, size)
        if start >= size and size > 0 or start > end:
            self.set_header("Content-Range", f"bytes */{size}")
            raise tornado.web.HTTPError(416)
        self.set_status(206)
        self.set_header("Content-Range", f"bytes {start}-{max(end - 1, start)}/{size}")
        return start, end

    def head(self):
        target = self._target()
        size = target.stat().st_size
        self.set_header("Accept-Ranges", "bytes")
        self.set_header("Content-Length", str(size))

    async def get(self):
        target = self._target()
        size = target.stat().st_size
        start, end = self._range(size)
        self.set_header("Accept-Ranges", "bytes")
        self.set_header("Content-Type", "application/octet-stream")
        self.set_header("Content-Length", str(end - start))
        with open(target, "rb") as f:
            f.seek(start)
            remaining = end - start
            while remaining > 0:
                block = f.read(min(DOWNLOAD_BLOCK, remaining))
                if not block:
                    break
                remaining -= len(block)
                self.write(block)
                await self.flush()
        self.finish()


class RunsHandler(SyncHandler):
    """``GET /runs``: every workflow the desktop app may run, with its state."""

    def get(self):
        workspace = self.workspace()
        qm = runs.queue_manager()
        self.finish({"queue": qm is not None,
                     "runs": [runs.status(qm, workspace, wf) for wf in self.config["workflows"]]})


class RunHandler(SyncHandler):
    """``POST /runs/<workflow>`` queues a run, ``DELETE`` stops it."""

    def _target(self, workflow: str):
        target = self.config["workflows"].get(workflow)
        if target is None:
            raise tornado.web.HTTPError(404, f"{workflow} cannot be run from the desktop app")
        qm = runs.queue_manager()
        if qm is None:
            raise tornado.web.HTTPError(503, "the workflow queue is not available")
        return target, qm

    def post(self, workflow):
        workspace = self.workspace()
        target, qm = self._target(workflow)
        try:
            params = json.loads(self.request.body or b"{}").get("params", {})
        except ValueError:
            raise tornado.web.HTTPError(400, "body must be JSON")
        try:
            state = runs.start(qm, workspace, workflow, target, params)
        except LookupError as exc:
            raise tornado.web.HTTPError(409, str(exc))
        except FileNotFoundError as exc:
            raise tornado.web.HTTPError(409, f"inputs not uploaded yet: {exc}")
        except ValueError as exc:
            raise tornado.web.HTTPError(400, str(exc))
        except RuntimeError as exc:
            raise tornado.web.HTTPError(503, str(exc))
        logger.info("run of %s queued in %s", workflow, workspace.name)
        self.set_status(201)
        self.finish(state)

    def delete(self, workflow):
        workspace = self.workspace()
        _, qm = self._target(workflow)
        self.finish(runs.stop(qm, workspace, workflow))


def make_app(root: Path, config: dict, prefix: str = "/sync") -> tornado.web.Application:
    kw = {"root": Path(root), "config": config}
    if not config["enabled"]:
        return tornado.web.Application([(rf"{prefix}/health", HealthHandler, kw)])
    return tornado.web.Application([
        (rf"{prefix}/health", HealthHandler, kw),
        (rf"{prefix}/manifest", ManifestHandler, kw),
        (rf"{prefix}/files/?", UploadsHandler, kw),
        (rf"{prefix}/files/([0-9a-f]+)", UploadHandler, kw),
        (rf"{prefix}/download", DownloadHandler, kw),
        (rf"{prefix}/runs/?", RunsHandler, kw),
        (rf"{prefix}/runs/([A-Za-z0-9._-]+)", RunHandler, kw),
    ])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=int(os.environ.get("SYNC_PORT", 8502)))
    parser.add_argument("--address", default="0.0.0.0")
    parser.add_argument("--settings", default="settings.json")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s workspace-sync %(message)s")

    settings = json.loads(Path(args.settings).read_text())
    config = sync_settings(settings)
    # Disabled, the service still answers /sync/health and nothing else, so a
    # Kubernetes sidecar stays Ready instead of crash-looping on exit 0.
    config["enabled"] = bool(config["enabled"] and settings.get("online_deployment"))
    if not config["enabled"]:
        logger.info("workspace sync disabled in %s; serving health only", args.settings)
    root = Path(os.environ.get("WORKSPACES_DIR", "/workspaces-streamlit-template"))
    root.mkdir(parents=True, exist_ok=True)
    make_app(root, config).listen(
        args.port, args.address, max_body_size=MAX_REQUEST_BYTES, xheaders=True
    )
    if config["enabled"]:
        logger.info("serving %s on %s:%d", root, args.address, args.port)
    tornado.ioloop.IOLoop.current().start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
