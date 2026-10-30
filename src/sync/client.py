"""Client side of workspace sync, used by the offline app.

A local workspace is linked to an online one by ``<workspace>/.sync.json``
(server URL and sync token). The sync page lists every input and every
result with its state on both sides, and the user pushes or pulls the items
they pick. An item is one uploaded input (a file, or a whole Bruker ``.d``
folder) or one result file.

The link also directs the online workspace: ``start_run`` queues one of its
workflows there with this workspace's parameters, ``runs`` reports their
state and ``stop_run`` cancels one.

Transfers are built for multi-GB files over unreliable links:

- Uploads use tus: the file goes up in chunks, each with a sha256 the server
  verifies before keeping it. Open uploads are remembered in the link file,
  so a push continues at the last verified chunk, also after an app restart.
- Downloads use HTTP Range into a hidden ``.<name>.sync-part`` next to the
  target and continue from its size when a connection breaks mid-stream.
- A lost connection is retried with growing back-off (up to a minute between
  attempts) until ``give_up_after`` seconds pass without progress, and every
  retry is reported, so the page can say "connection lost, retrying in 16 s".
- Every finished file is checked against the sender's sha256.
"""

import base64
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import quote, urljoin

import requests

from src.sync import paths

LINK_FILE = ".sync.json"
CACHE_FILE = ".sync-cache.json"
# What the user chose to sync per workflow. Kept apart from LINK_FILE, which
# a running transfer rewrites.
PREFS_FILE = ".sync-prefs.json"
CHUNK_SIZE = 32 * 1024 * 1024
TUS_HEADERS = {"Tus-Resumable": "1.0.0"}
# A workspace path in parameters sent with a run; the server puts its own
# workspace in front (see runs.resolve_params).
WORKSPACE_REF = "sync-workspace://"

Progress = Callable[[int, int, str], None]
Notice = Callable[[str], None]

_STREAM_ERRORS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
)


class SyncError(Exception):
    pass


class Cancelled(SyncError):
    pass


@dataclass
class Item:
    """One row of the sync page."""
    key: str
    kind: str                      # "input" or "result"
    size: int
    state: str
    files: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return PurePosixPath(self.key).name

    @property
    def workflow(self) -> str:
        return workflow_of(self.key)


@dataclass
class SyncReport:
    transferred: list[str] = field(default_factory=list)
    unchanged: int = 0
    bytes: int = 0


# States shown on the page.
NOT_ON_SERVER = "Not on server"
ON_SERVER = "On server"
CHANGED_LOCALLY = "Changed locally"
NOT_DOWNLOADED = "Not downloaded"
DOWNLOADED = "Downloaded"
CHANGED_ON_SERVER = "Changed on server"


def read_link(workspace: Path) -> dict:
    try:
        return json.loads(Path(workspace, LINK_FILE).read_text())
    except (OSError, ValueError):
        return {}


def write_link(workspace: Path, link: dict) -> None:
    target = Path(workspace, LINK_FILE)
    tmp = target.with_name(LINK_FILE + ".tmp")
    tmp.write_text(json.dumps(link, indent=2))
    os.replace(tmp, target)


def unlink_workspace(workspace: Path) -> None:
    Path(workspace, LINK_FILE).unlink(missing_ok=True)


def workflow_of(rel: str) -> str:
    """The workflow directory a path or item key belongs to; "" for the
    workspace's own mzML-files/."""
    parts = PurePosixPath(rel).parts
    if len(parts) < 2 or parts[0] == "mzML-files":
        return ""
    return parts[0]


def read_prefs(workspace: Path) -> dict:
    """``{"keep_in_sync": bool, "workflows": {wf: {"push": bool, "pull": bool}}}``"""
    try:
        prefs = json.loads(Path(workspace, PREFS_FILE).read_text())
    except (OSError, ValueError):
        prefs = {}
    prefs.setdefault("keep_in_sync", False)
    prefs.setdefault("workflows", {})
    return prefs


def write_prefs(workspace: Path, prefs: dict) -> None:
    target = Path(workspace, PREFS_FILE)
    tmp = target.with_name(PREFS_FILE + ".tmp")
    tmp.write_text(json.dumps(prefs, indent=2))
    os.replace(tmp, target)


def direction_on(prefs: dict, workflow: str, direction: str) -> bool:
    """Whether ``direction`` ("push" or "pull") is chosen for ``workflow``.
    Both are on until the user turns one off."""
    return bool(prefs["workflows"].get(workflow, {}).get(direction, True))


def item_key(rel: str) -> str:
    """The input item a pushable file belongs to.

    ``wf/input-files/<key>/<name>/...`` and ``mzML-files/<name>/...`` group
    under their top-level name, so a ``.d`` folder is one item.
    """
    parts = PurePosixPath(rel).parts
    if parts[0] == "mzML-files":
        return "/".join(parts[:2])
    return "/".join(parts[:4])


def portable_params(workspace: Path, workflow: str) -> dict:
    """The workflow's parameters with every local input path replaced by
    its place in the workspace, so the server can point them at its copy.

    Input selections hold absolute paths: files under ``input-files/`` and
    files or ``.d`` folders anywhere else (``external_files.txt``). Both are
    pushed to ``<wf>/input-files/<key>/<name>``.
    """
    try:
        params = json.loads(Path(workspace, workflow, "params.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    where: dict[str, str] = {}
    for rel, path in paths.push_entries(workspace).items():
        where[str(path)] = rel
        # The item's own root, e.g. the .d folder a file belongs to.
        key = item_key(rel)
        depth = len(PurePosixPath(rel).parts) - len(PurePosixPath(key).parts)
        where[str(path.parents[depth - 1]) if depth else str(path)] = key

    def convert(value):
        if isinstance(value, str) and value in where:
            return WORKSPACE_REF + where[value]
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        return value

    return convert(params)


def run_inputs(params: dict) -> set[str]:
    """The input items portable parameters refer to: what a run needs online."""
    found: set[str] = set()

    def visit(value):
        if isinstance(value, str) and value.startswith(WORKSPACE_REF):
            found.add(item_key(value[len(WORKSPACE_REF):]))
        elif isinstance(value, list):
            for v in value:
                visit(v)
        elif isinstance(value, dict):
            for v in value.values():
                visit(v)

    visit(params)
    return found


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _part_file(dest: Path) -> Path:
    return dest.with_name(f".{dest.name}.sync-part")


class SyncClient:
    def __init__(self, url: str, token: str, session: requests.Session | None = None,
                 chunk_size: int = CHUNK_SIZE, give_up_after: float = 900,
                 timeout: float = 120, notice: Notice | None = None):
        self.base = url.rstrip("/") + "/"
        self.token = token.strip()
        self.session = session or requests.Session()
        self.chunk_size = chunk_size
        self.give_up_after = give_up_after
        self.timeout = timeout
        self.notice = notice or (lambda msg: None)
        self.cancel: threading.Event | None = None

    # -- transport ---------------------------------------------------------
    def _check_cancel(self):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled("Cancelled")

    def _sleep(self, seconds: float) -> None:
        """Sleep, waking early when the transfer is cancelled."""
        (self.cancel or threading.Event()).wait(seconds)

    def _wait(self, failing_since: float, delay: float, reason: str) -> float:
        """Sleep before the next attempt; raise once retrying has gone on too long."""
        if time.monotonic() - failing_since > self.give_up_after:
            raise SyncError(f"giving up after {self.give_up_after:.0f} s without a connection: {reason}")
        self.notice(f"Connection lost ({reason}). Retrying in {delay:.0f} s…")
        self._sleep(delay)
        self._check_cancel()
        return min(delay * 2, 60)

    def _request(self, method: str, url: str, expect=(200,), **kw) -> requests.Response:
        headers = {"Authorization": f"Bearer {self.token}", **TUS_HEADERS, **kw.pop("headers", {})}
        delay, failing_since = 2.0, None
        while True:
            self._check_cancel()
            try:
                resp = self.session.request(method, urljoin(self.base, url), headers=headers,
                                            timeout=self.timeout, **kw)
            except (requests.ConnectionError, requests.Timeout) as exc:
                failing_since = failing_since or time.monotonic()
                delay = self._wait(failing_since, delay, type(exc).__name__)
                continue
            if resp.status_code in (502, 503, 504):
                failing_since = failing_since or time.monotonic()
                delay = self._wait(failing_since, delay, f"server answered {resp.status_code}")
                continue
            if failing_since is not None:
                self.notice("")
            if resp.status_code in expect:
                return resp
            try:
                message = resp.json().get("error", resp.reason)
            except ValueError:
                message = resp.reason
            if resp.status_code == 401:
                message = "the sync token is unknown or expired; create a new one in the online app"
            err = SyncError(f"{resp.status_code} {message}")
            err.status = resp.status_code
            raise err

    def manifest(self, scope: str) -> dict[str, dict]:
        return self._request("GET", f"manifest?scope={scope}").json()["files"]

    def check(self) -> str:
        """Validate URL and token; return the online workspace name."""
        return self._request("GET", "manifest?scope=pull").json()["workspace"]

    # -- status ------------------------------------------------------------
    def _pending_offset(self, workspace: Path, rel: str, size: int) -> int | None:
        known = read_link(workspace).get("uploads", {}).get(rel)
        if not known or known.get("size") != size:
            return None
        try:
            return int(self._request("HEAD", known["location"]).headers["Upload-Offset"])
        except SyncError:
            return None

    def input_items(self, workspace: Path) -> list[Item]:
        """Every input item with its state on the server."""
        cache = paths.HashCache(Path(workspace, CACHE_FILE))
        local = paths.push_entries(workspace)
        remote = self.manifest("push")
        items: dict[str, Item] = {}
        for rel, path in local.items():
            key = item_key(rel)
            item = items.setdefault(key, Item(key, "input", 0, ON_SERVER))
            item.files.append(rel)
            size = path.stat().st_size
            item.size += size
            theirs = remote.get(rel)
            if theirs is None:
                state = NOT_ON_SERVER
            elif theirs["size"] != size or cache.digest(path)[1] != theirs["sha256"]:
                state = CHANGED_LOCALLY
            else:
                continue
            if item.state == ON_SERVER or state == NOT_ON_SERVER:
                item.state = state
        cache.save()
        for item in items.values():
            if item.state == ON_SERVER:
                continue
            sent = total = 0
            for rel in item.files:
                size = local[rel].stat().st_size
                total += size
                if rel in remote and remote[rel]["size"] == size:
                    sent += size
                else:
                    offset = self._pending_offset(workspace, rel, size)
                    sent += offset or 0
            if 0 < sent < total and item.state == NOT_ON_SERVER:
                item.state = f"Paused at {100 * sent // total}%"
        return sorted(items.values(), key=lambda i: i.key)

    def result_items(self, workspace: Path) -> list[Item]:
        """Every result on the server with its state in the local workspace."""
        cache = paths.HashCache(Path(workspace, CACHE_FILE))
        remote = self.manifest("pull")
        items = []
        for rel, meta in sorted(remote.items()):
            if not paths.is_pullable(rel):
                continue
            dest = Path(workspace, rel)
            part = _part_file(dest)
            if dest.is_file():
                same = (dest.stat().st_size == meta["size"]
                        and cache.digest(dest)[1] == meta["sha256"])
                state = DOWNLOADED if same else CHANGED_ON_SERVER
            elif part.is_file() and 0 < part.stat().st_size < meta["size"]:
                state = f"Paused at {100 * part.stat().st_size // max(meta['size'], 1)}%"
            else:
                state = NOT_DOWNLOADED
            items.append(Item(rel, "result", meta["size"], state, [rel]))
        cache.save()
        return items

    # -- runs --------------------------------------------------------------
    def runs(self) -> dict[str, dict]:
        """The online workflows that can be run from here, with their state."""
        return {r["workflow"]: r for r in self._request("GET", "runs").json()["runs"]}

    def start_run(self, workspace: Path, workflow: str, name: str = "") -> dict:
        """Queue ``workflow`` online with this workspace's parameters for it.
        ``name`` names the run of a multi-run workflow."""
        params = portable_params(workspace, workflow)
        return self._request("POST", f"runs/{workflow}", json={"params": params, "name": name},
                             expect=(200, 201)).json()

    def stop_run(self, workflow: str) -> dict:
        return self._request("DELETE", f"runs/{workflow}").json()

    # -- push --------------------------------------------------------------
    def push(self, workspace: Path, keys: list[str] | None = None,
             progress: Progress | None = None,
             cancel: threading.Event | None = None) -> SyncReport:
        """Upload the files of the chosen input items the server lacks."""
        self.cancel = cancel
        try:
            return self._push(workspace, keys, progress)
        finally:
            self.cancel = None

    def _push(self, workspace, keys, progress) -> SyncReport:
        cache = paths.HashCache(Path(workspace, CACHE_FILE))
        local = paths.push_entries(workspace)
        remote = self.manifest("push")
        wanted = None if keys is None else set(keys)
        plan, report = [], SyncReport()
        for rel, path in local.items():
            if wanted is not None and item_key(rel) not in wanted:
                continue
            size, digest = cache.digest(path)
            if remote.get(rel, {}).get("sha256") == digest:
                report.unchanged += 1
            else:
                plan.append((rel, path, size, digest))
        cache.save()
        total = sum(p[2] for p in plan)
        done = 0
        for rel, path, size, digest in plan:
            def step(n, base=done, rel=rel):
                if progress:
                    progress(base + n, total, rel)
            self._upload(workspace, rel, path, size, digest, step)
            done += size
            report.transferred.append(rel)
            report.bytes += size
        if progress:
            progress(total, total, "")
        return report

    def _upload(self, workspace, rel, path, size, digest, step):
        link = read_link(workspace)
        pending = link.setdefault("uploads", {})
        offset, location = None, None
        known = pending.get(rel)
        if known and known.get("sha256") == digest and known.get("size") == size:
            try:
                offset = int(self._request("HEAD", known["location"]).headers["Upload-Offset"])
                location = known["location"]
            except SyncError:
                offset = None
        if offset is None:
            resp = self._request("POST", "files", expect=(201,), headers={
                "Upload-Length": str(size),
                "Upload-Metadata": f"path {_b64(rel)},sha256 {_b64(digest)}",
            })
            location, offset = resp.headers["Location"], 0
            pending[rel] = {"location": location, "sha256": digest, "size": size}
            write_link(workspace, link)

        step(offset)
        bad_chunks = 0
        with open(path, "rb") as f:
            while offset < size:
                self._check_cancel()
                f.seek(offset)
                chunk = f.read(self.chunk_size)
                checksum = base64.b64encode(hashlib.sha256(chunk).digest()).decode()
                try:
                    resp = self._request("PATCH", location, expect=(204,), data=chunk, headers={
                        "Content-Type": "application/offset+octet-stream",
                        "Upload-Offset": str(offset),
                        "Upload-Checksum": f"sha256 {checksum}",
                    })
                    offset = int(resp.headers["Upload-Offset"])
                except SyncError as exc:
                    status = getattr(exc, "status", None)
                    if status == 460 and offset + len(chunk) < size and bad_chunks < 3:
                        # Corrupted in transit: the server dropped it, send again.
                        bad_chunks += 1
                        continue
                    if status not in (409, 423):
                        raise SyncError(f"{rel}: {exc}") from exc
                    if status == 423:
                        # An earlier, timed-out send of this chunk is still
                        # being written; the server lets it finish or drops it.
                        self._sleep(2)
                    # A retried chunk had already arrived: continue from
                    # where the server stands.
                    offset = int(self._request("HEAD", location).headers["Upload-Offset"])
                step(offset)

        link = read_link(workspace)
        link.get("uploads", {}).pop(rel, None)
        write_link(workspace, link)

    # -- pull --------------------------------------------------------------
    def pull(self, workspace: Path, keys: list[str] | None = None,
             progress: Progress | None = None,
             cancel: threading.Event | None = None) -> SyncReport:
        """Download the chosen results that differ from the local copy."""
        self.cancel = cancel
        try:
            return self._pull(workspace, keys, progress)
        finally:
            self.cancel = None

    def _pull(self, workspace, keys, progress) -> SyncReport:
        cache = paths.HashCache(Path(workspace, CACHE_FILE))
        remote = self.manifest("pull")
        wanted = None if keys is None else set(keys)
        plan, report = [], SyncReport()
        for rel, meta in sorted(remote.items()):
            if not paths.is_pullable(rel) or (wanted is not None and rel not in wanted):
                continue
            dest = Path(workspace, rel)
            if dest.is_file() and cache.digest(dest)[1] == meta["sha256"]:
                report.unchanged += 1
            else:
                plan.append((rel, meta["size"], meta["sha256"]))
        total = sum(p[1] for p in plan)
        done = 0
        for rel, size, digest in plan:
            def step(n, base=done, rel=rel):
                if progress:
                    progress(base + n, total, rel)
            dest = Path(workspace, rel)
            self._download(rel, dest, size, digest, step)
            cache.remember(dest, digest)
            done += size
            report.transferred.append(rel)
            report.bytes += size
        cache.save()
        if progress:
            progress(total, total, "")
        return report

    def _download(self, rel, dest: Path, size, digest, step):
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = _part_file(dest)
        restarted = False
        delay, failing_since = 2.0, None
        while True:
            have = part.stat().st_size if part.exists() else 0
            if have > size:
                part.unlink()
                have = 0
            if have < size:
                before = have
                resp = self._request(
                    "GET", f"download?path={quote(rel)}", expect=(200, 206), stream=True,
                    headers={"Range": f"bytes={have}-"} if have else {},
                )
                if resp.status_code == 200:
                    have = 0
                try:
                    with open(part, "ab" if have else "wb") as f:
                        for block in resp.iter_content(1024 * 1024):
                            self._check_cancel()
                            f.write(block)
                            have += len(block)
                            step(have)
                            failing_since = None
                except _STREAM_ERRORS as exc:
                    # Keep what arrived and ask for the rest.
                    failing_since = failing_since or time.monotonic()
                    delay = self._wait(failing_since, delay, type(exc).__name__)
                    continue
                finally:
                    resp.close()
                if have < size:
                    if have == before:
                        # The stream ended early without delivering anything.
                        failing_since = failing_since or time.monotonic()
                        delay = self._wait(failing_since, delay, "transfer stalled")
                    continue
            elif not part.exists():
                part.touch()
            if paths.sha256_file(part) == digest:
                os.replace(part, dest)
                return
            part.unlink()
            if restarted:
                raise SyncError(f"{rel}: checksum mismatch after download")
            # The result changed on the server since the partial download
            # began: start this file over once.
            restarted = True
