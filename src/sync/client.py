"""Client side of workspace sync, used by the offline app.

A local workspace is linked to an online one by ``<workspace>/.sync.json``
(server URL and sync token). ``push`` sends inputs and parameters the server
does not have yet, ``pull`` fetches results the local workspace does not
have yet; both compare sha256 manifests, so an unchanged file is never sent
twice. Uploads use tus and downloads HTTP Range, and both resume where they
stopped, also across app restarts: open tus uploads are remembered in the
link file and partial downloads stay on disk as hidden ``.<name>.sync-part``.
"""

import base64
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import requests

from src.sync import paths

LINK_FILE = ".sync.json"
CACHE_FILE = ".sync-cache.json"
CHUNK_SIZE = 32 * 1024 * 1024
TUS_HEADERS = {"Tus-Resumable": "1.0.0"}

Progress = Callable[[int, int, str], None]


class SyncError(Exception):
    pass


class Cancelled(SyncError):
    pass


@dataclass
class SyncReport:
    transferred: list[str] = field(default_factory=list)
    unchanged: int = 0
    bytes: int = 0


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


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


class SyncClient:
    def __init__(self, url: str, token: str, session: requests.Session | None = None,
                 chunk_size: int = CHUNK_SIZE, retries: int = 5, timeout: float = 120):
        self.base = url.rstrip("/") + "/"
        self.token = token.strip()
        self.session = session or requests.Session()
        self.chunk_size = chunk_size
        self.retries = retries
        self.timeout = timeout

    # -- transport ---------------------------------------------------------
    def _request(self, method: str, url: str, expect=(200,), **kw) -> requests.Response:
        headers = {"Authorization": f"Bearer {self.token}", **TUS_HEADERS, **kw.pop("headers", {})}
        delay = 2
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.request(method, urljoin(self.base, url), headers=headers,
                                            timeout=self.timeout, **kw)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == self.retries:
                    raise SyncError(f"cannot reach {self.base}: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if resp.status_code in expect:
                return resp
            if resp.status_code in (502, 503, 504) and attempt < self.retries:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            try:
                message = resp.json().get("error", resp.reason)
            except ValueError:
                message = resp.reason
            if resp.status_code == 401:
                message = "the sync token is unknown or expired; create a new one in the online app"
            raise SyncError(f"{method} {url}: {resp.status_code} {message}")
        raise SyncError(f"{method} {url} failed")

    def manifest(self, scope: str) -> dict[str, dict]:
        return self._request("GET", f"manifest?scope={scope}").json()["files"]

    def check(self) -> str:
        """Validate URL and token; return the online workspace name."""
        return self._request("GET", "manifest?scope=pull").json()["workspace"]

    # -- push --------------------------------------------------------------
    def plan_push(self, workspace: Path) -> list[tuple[str, Path, int, str]]:
        cache = paths.HashCache(Path(workspace, CACHE_FILE))
        local = paths.push_entries(workspace)
        remote = self.manifest("push")
        plan = []
        for rel, path in local.items():
            size, digest = cache.digest(path)
            if remote.get(rel, {}).get("sha256") != digest:
                plan.append((rel, path, size, digest))
        cache.save()
        self._unchanged = len(local) - len(plan)
        return plan

    def push(self, workspace: Path, progress: Progress | None = None,
             cancel: threading.Event | None = None) -> SyncReport:
        plan = self.plan_push(workspace)
        report = SyncReport(unchanged=self._unchanged)
        total = sum(size for _, _, size, _ in plan)
        done = 0
        for rel, path, size, digest in plan:
            def step(n, base=done, rel=rel):
                if progress:
                    progress(base + n, total, rel)
            self._upload(workspace, rel, path, size, digest, step, cancel)
            done += size
            report.transferred.append(rel)
            report.bytes += size
        if progress:
            progress(total, total, "")
        return report

    def _upload(self, workspace, rel, path, size, digest, step, cancel):
        link = read_link(workspace)
        pending = link.setdefault("uploads", {})
        offset = None
        known = pending.get(rel)
        if known and known.get("sha256") == digest and known.get("size") == size:
            try:
                head = self._request("HEAD", known["location"])
                offset = int(head.headers["Upload-Offset"])
                location = known["location"]
            except SyncError:
                offset = None
        if offset is None:
            resp = self._request("POST", "files", expect=(201,), headers={
                "Upload-Length": str(size),
                "Upload-Metadata": f"path {_b64(rel)},sha256 {_b64(digest)}",
            })
            location = resp.headers["Location"]
            offset = 0
            pending[rel] = {"location": location, "sha256": digest, "size": size}
            write_link(workspace, link)

        step(offset)
        with open(path, "rb") as f:
            while offset < size:
                if cancel is not None and cancel.is_set():
                    raise Cancelled("cancelled")
                f.seek(offset)
                chunk = f.read(self.chunk_size)
                try:
                    resp = self._request("PATCH", location, expect=(204,), data=chunk, headers={
                        "Content-Type": "application/offset+octet-stream",
                        "Upload-Offset": str(offset),
                    })
                    offset = int(resp.headers["Upload-Offset"])
                except SyncError as exc:
                    if " 409 " not in str(exc):
                        raise
                    # A dropped connection left part of the chunk on the
                    # server: ask where it stands and continue from there.
                    offset = int(self._request("HEAD", location).headers["Upload-Offset"])
                step(offset)

        link = read_link(workspace)
        link.get("uploads", {}).pop(rel, None)
        write_link(workspace, link)

    # -- pull --------------------------------------------------------------
    def plan_pull(self, workspace: Path) -> list[tuple[str, int, str]]:
        cache = paths.HashCache(Path(workspace, CACHE_FILE))
        local = cache.manifest(paths.pull_entries(workspace))
        cache.save()
        remote = self.manifest("pull")
        plan = [(rel, m["size"], m["sha256"]) for rel, m in sorted(remote.items())
                if paths.is_pullable(rel) and local.get(rel, {}).get("sha256") != m["sha256"]]
        self._unchanged = len(remote) - len(plan)
        return plan

    def pull(self, workspace: Path, progress: Progress | None = None,
             cancel: threading.Event | None = None) -> SyncReport:
        plan = self.plan_pull(workspace)
        report = SyncReport(unchanged=self._unchanged)
        total = sum(size for _, size, _ in plan)
        done = 0
        cache = paths.HashCache(Path(workspace, CACHE_FILE))
        for rel, size, digest in plan:
            def step(n, base=done, rel=rel):
                if progress:
                    progress(base + n, total, rel)
            dest = Path(workspace, rel)
            self._download(rel, dest, size, digest, step, cancel)
            cache.remember(dest, digest)
            done += size
            report.transferred.append(rel)
            report.bytes += size
        cache.save()
        if progress:
            progress(total, total, "")
        return report

    def _download(self, rel, dest: Path, size, digest, step, cancel):
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(f".{dest.name}.sync-part")
        for attempt in range(2):
            have = part.stat().st_size if part.exists() else 0
            if have > size:
                part.unlink()
                have = 0
            if have < size:
                resp = self._request(
                    "GET", f"download?path={requests.utils.quote(rel)}", expect=(200, 206),
                    headers={"Range": f"bytes={have}-"} if have else {}, stream=True,
                )
                mode = "ab" if resp.status_code == 206 else "wb"
                have = have if mode == "ab" else 0
                with open(part, mode) as f:
                    for block in resp.iter_content(1024 * 1024):
                        if cancel is not None and cancel.is_set():
                            raise Cancelled("cancelled")
                        f.write(block)
                        have += len(block)
                        step(have)
            elif not part.exists():
                part.touch()
            if paths.sha256_file(part) == digest:
                os.replace(part, dest)
                return
            # The result changed on the server since the partial download
            # began: start this file over once.
            part.unlink()
        raise SyncError(f"{rel}: checksum mismatch after download")
