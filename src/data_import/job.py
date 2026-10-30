"""The import job: download the selected files and file them into upload folders.

Runs as its own process, without Streamlit, and talks to the page only
through files in the job directory, so any server replica can show and stop
it: ``status.json`` (written atomically, with a heartbeat), ``cancel`` (the
page creates it to stop the job) and ``request.json`` (what was asked for,
so an interrupted import can be started again and resumes its ``.part``
files).
"""
from __future__ import annotations

import filecmp
import gzip
import hashlib
import json
import multiprocessing
import os
import shutil
import tarfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from src.workflow.vendor_files import has_type

from .download import Cancelled, download, inflate, md5sum
from .net import make_session, redact
from .remote import RemoteFile, archive_type, safe_member_path, zip_data_offset

HEARTBEAT_SECONDS = 2
# A job whose heartbeat is older than this is gone (its server restarted).
STALE_AFTER = 30
# An archive may not unpack to more than this many times its own size (or
# this floor, as small archives of text-based mzML compress very well), nor
# beyond the size limit or the free disk space.
MAX_UNPACK_RATIO = 100
MIN_UNPACK_LIMIT = 10 * 10**9
MAX_UNPACK_MEMBERS = 20000


# ---------------------------------------------------------------------------
# Items: what the user selects
# ---------------------------------------------------------------------------

def _strip_gz(name: str) -> str:
    lower = name.lower()
    return name[:-3] if lower.endswith(".gz") and not lower.endswith(".tar.gz") else name


def target_for(name: str, targets: Dict[str, dict]) -> str:
    """The upload key whose file types match ``name`` ('' if none)."""
    base = _strip_gz(name)
    for key, target in targets.items():
        if has_type(base, target["file_types"]):
            return key
    return ""


def _item_id(*parts) -> str:
    return hashlib.sha1("\n".join(str(p) for p in parts).encode()).hexdigest()[:12]


def build_items(files: List[RemoteFile], targets: Dict[str, dict]) -> List[dict]:
    """Group files into selectable items: one per file, per Bruker .d folder
    (its files together), or per archive that has to be downloaded whole."""
    items, folders = [], {}
    for f in files:
        parts = f.path.split("/")
        d_index = next((i for i, p in enumerate(parts[:-1]) if p.lower().endswith(".d")), None)
        if d_index is not None:
            root = "/".join(parts[:d_index + 1])
            folder = folders.get(root)
            if folder is None:
                folder = folders[root] = {
                    "id": _item_id(redact(f.url), root), "name": parts[d_index], "path": root,
                    "kind": "folder", "size": 0, "files": [],
                    "target": target_for(parts[d_index], targets),
                }
                items.append(folder)
            folder["files"].append(asdict(f))
            folder["size"] += f.size or 0
            continue
        is_member = f.offset is not None or f.zip_header is not None
        kind = "archive" if archive_type(f.path) and not is_member else "file"
        items.append({
            "id": _item_id(redact(f.url), f.path, f.offset, f.zip_header),
            "name": parts[-1], "path": f.path, "kind": kind, "size": f.size,
            "files": [asdict(f)],
            "target": "*" if kind == "archive" else target_for(parts[-1], targets),
        })
    return items


# ---------------------------------------------------------------------------
# Status files
# ---------------------------------------------------------------------------

def status_path(job_dir) -> Path:
    return Path(job_dir, "status.json")


def read_status(job_dir) -> dict:
    try:
        with open(status_path(job_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_status(job_dir, status: dict) -> None:
    path = status_path(job_dir)
    tmp = path.with_name(f".status-{os.getpid()}-{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)
    os.replace(tmp, path)


def is_running(status: dict) -> bool:
    return status.get("state") == "running" and time.time() - status.get("heartbeat", 0) < STALE_AFTER


def is_interrupted(status: dict) -> bool:
    """Marked running, but its process stopped sending heartbeats."""
    return status.get("state") == "running" and not is_running(status)


def request_cancel(job_dir) -> None:
    Path(job_dir, "cancel").touch()


def _log(job_dir, message: str) -> None:
    with open(Path(job_dir, "import.log"), "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


# ---------------------------------------------------------------------------
# Unpacking whole archives
# ---------------------------------------------------------------------------

def _unpack(archive: Path, out: Path, max_bytes: Optional[int]) -> None:
    """Unpack regular files only, refusing paths that escape ``out``,
    links and devices, and archives that grow too large."""
    out.mkdir(parents=True, exist_ok=True)
    limit = max(archive.stat().st_size * MAX_UNPACK_RATIO, MIN_UNPACK_LIMIT)
    limit = min(limit, shutil.disk_usage(out).free)
    if max_bytes is not None:
        limit = min(limit, max_bytes)
    total = 0
    if archive.name.lower().endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            if len(infos) > MAX_UNPACK_MEMBERS:
                raise IOError(f"{archive.name} holds more than {MAX_UNPACK_MEMBERS} files.")
            if sum(i.file_size for i in infos) > limit:
                raise IOError(f"{archive.name} unpacks to more than the allowed size.")
            for info in infos:
                path = safe_member_path(info.filename)
                if path is None or info.flag_bits & 0x1:
                    continue
                target = Path(out, path)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > limit:
                            raise IOError(f"{archive.name} unpacks to more than the allowed size.")
                        dst.write(chunk)
        return
    with tarfile.open(archive, mode="r:*") as tar:
        count = 0
        for member in tar:
            count += 1
            if count > MAX_UNPACK_MEMBERS:
                raise IOError(f"{archive.name} holds more than {MAX_UNPACK_MEMBERS} files.")
            path = safe_member_path(member.name)
            if path is None or not member.isfile():
                continue
            total += member.size
            if total > limit:
                raise IOError(f"{archive.name} unpacks to more than the allowed size.")
            target = Path(out, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)


def _unpacked_entries(root: Path):
    """Files and .d folders below ``root``, the .d folders not descended into."""
    for dirpath, dirnames, filenames in os.walk(root):
        for d in list(dirnames):
            if d.lower().endswith(".d"):
                dirnames.remove(d)
                yield Path(dirpath, d)
        for name in filenames:
            yield Path(dirpath, name)


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------

def _is_copy(path: Path, source: Optional[Path]) -> bool:
    try:
        return (source is not None and path.is_file() and source.is_file()
                and filecmp.cmp(path, source, shallow=False))
    except OSError:
        return False


class _Job:
    def __init__(self, job_dir: Path, items, targets, guard, allowed_hosts, max_bytes):
        self.job_dir, self.items, self.targets = job_dir, items, targets
        self.max_bytes = max_bytes
        self.session = make_session(guard, allowed_hosts)
        self.lock = threading.Lock()
        self.cancel_file = Path(job_dir, "cancel")
        self._cancel_checked, self._cancelled = 0.0, False
        self.cleared = set()
        self.used_names = set()
        self.item_bytes = {item["id"]: 0 for item in items}
        self.status = {
            "state": "running", "pid": os.getpid(), "started": time.time(), "heartbeat": time.time(),
            "total_items": len(items), "done_items": 0,
            "bytes_total": sum(int(i.get("size") or 0) for i in items), "bytes_done": 0,
            "active": {}, "retry": "", "imported": [], "skipped": [], "errors": [],
        }

    def cancelled(self) -> bool:
        now = time.monotonic()
        if not self._cancelled and now - self._cancel_checked > 1:
            self._cancel_checked = now
            self._cancelled = self.cancel_file.exists()
        return self._cancelled

    def save(self) -> None:
        with self.lock:
            self.status["heartbeat"] = time.time()
            self.status["bytes_done"] = sum(self.item_bytes.values())
            write_status(self.job_dir, self.status)

    def heartbeat(self, stop: threading.Event) -> None:
        while not stop.wait(HEARTBEAT_SECONDS):
            self.save()

    def place(self, path: Path, key: str) -> Path:
        """Move ``path`` into the upload folder ``key``; replaces a file of the
        same name, and the example files the folder holds while it is empty."""
        target = self.targets[key]
        directory = Path(target["dir"])
        with self.lock:
            directory.mkdir(parents=True, exist_ok=True)
            if key not in self.cleared:
                self.cleared.add(key)
                # Only example files so far (a demo workspace may hold just
                # some of them): the import replaces them. A file counts as an
                # example only if it is a copy of one, so an earlier import
                # that happens to share an example's name is kept.
                examples = {Path(f).name: Path(f) for f in target.get("fallback") or []}
                present = [p for p in directory.iterdir() if p.name != "external_files.txt"]
                if present and all(_is_copy(p, examples.get(p.name)) for p in present):
                    for p in present:
                        p.unlink(missing_ok=True)
            name = path.name
            stem, dot, ext = name.partition(".")
            n = 2
            while (key, name.lower()) in self.used_names:
                name = f"{stem}_{n}{dot}{ext}"
                n += 1
            self.used_names.add((key, name.lower()))
        dest = Path(directory, name)
        if dest.is_dir():
            shutil.rmtree(dest)
        elif dest.exists():
            dest.unlink()
        shutil.move(str(path), dest)
        return dest

    def fetch(self, item: dict, f: dict, dest: Path, base: int = 0) -> Path:
        rf = RemoteFile(**f)

        def progress(done):
            self.item_bytes[item["id"]] = base + done

        def retry(message):
            with self.lock:
                self.status["retry"] = message

        common = dict(on_progress=progress, on_retry=retry, should_cancel=self.cancelled,
                      max_bytes=self.max_bytes)
        if rf.zip_header is not None:
            offset = zip_data_offset(self.session, rf)
            if rf.deflate:
                packed = dest.with_name(dest.name + ".deflate")
                if not dest.exists():
                    download(self.session, rf.url, packed, start=offset, length=rf.stored_size,
                             etag=rf.etag, **common)
                    inflate(packed, dest, rf.size, rf.crc32)
                return dest
            path = download(self.session, rf.url, dest, start=offset, length=rf.stored_size,
                            etag=rf.etag, **common)
        elif rf.offset is not None:
            path = download(self.session, rf.url, dest, start=rf.offset, length=rf.stored_size,
                            etag=rf.etag, **common)
        else:
            path = download(self.session, rf.url, dest, etag=rf.etag, **common)
            if rf.size and path.stat().st_size != rf.size:
                path.unlink()
                raise IOError(f"{dest.name}: got {path.stat().st_size} bytes, the source lists {rf.size}.")
            if rf.md5 and md5sum(path) != rf.md5:
                path.unlink()
                raise IOError(f"{dest.name}: the checksum does not match the source's.")
        with self.lock:
            self.status["retry"] = ""
        return path

    def run_item(self, item: dict) -> None:
        if self.cancelled():
            raise Cancelled()
        work = Path(self.job_dir, "downloads", item["id"])
        with self.lock:
            self.status["active"][item["id"]] = item["name"]
        try:
            if item["kind"] == "folder":
                folder = Path(work, item["name"])
                done = 0
                for f in item["files"]:
                    rel = f["path"][len(item["path"]) + 1:]
                    path = Path(folder, rel)
                    if not path.exists():
                        self.fetch(item, f, path, base=done)
                    done += f.get("size") or path.stat().st_size
                self.record(item, self.place(folder, item["target"]))
            elif item["kind"] == "archive":
                archive = self.fetch(item, item["files"][0], Path(work, item["name"]))
                unpacked = Path(work, "unpacked")
                shutil.rmtree(unpacked, ignore_errors=True)
                _unpack(archive, unpacked, self.max_bytes)
                archive.unlink()
                for entry in _unpacked_entries(unpacked):
                    key = target_for(entry.name, self.targets)
                    if not key:
                        with self.lock:
                            self.status["skipped"].append(f"{item['name']}/{entry.relative_to(unpacked)}")
                        continue
                    if entry.is_file() and _strip_gz(entry.name) != entry.name:
                        entry = _gunzip(entry)
                    self.record(item, self.place(entry, key))
            else:
                path = self.fetch(item, item["files"][0], Path(work, item["name"]))
                if _strip_gz(path.name) != path.name:
                    path = _gunzip(path)
                self.record(item, self.place(path, item["target"]))
            shutil.rmtree(work, ignore_errors=True)
            _log(self.job_dir, f"{item['path']}: imported")
        except Cancelled:
            raise
        except Exception as e:  # keep going with the other items
            with self.lock:
                self.status["errors"].append(f"{item['name']}: {e}")
            _log(self.job_dir, f"{item['path']}: ERROR {e}")
        finally:
            with self.lock:
                self.status["active"].pop(item["id"], None)
                self.status["done_items"] += 1
                if item.get("size"):
                    self.item_bytes[item["id"]] = item["size"]

    def record(self, item: dict, dest: Path) -> None:
        with self.lock:
            self.status["imported"].append({"id": item["id"], "name": dest.name,
                                            "key": next((k for k, t in self.targets.items()
                                                         if Path(t["dir"]) == dest.parent), "")})


def _gunzip(path: Path) -> Path:
    out = path.with_name(_strip_gz(path.name))
    with gzip.open(path, "rb") as src, open(out, "wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    path.unlink()
    return out


def run_import(job_dir: str, items: List[dict], targets: Dict[str, dict], guard: bool = True,
               allowed_hosts: List[str] = None, max_bytes: Optional[int] = None,
               parallel: int = 4) -> dict:
    """Download ``items`` (from ``build_items``) into their targets' folders."""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    Path(job_dir, "cancel").unlink(missing_ok=True)
    items = [i for i in items if i.get("target")]
    job = _Job(job_dir, items, targets, guard, allowed_hosts, max_bytes)
    job.save()
    _log(job_dir, f"Importing {len(items)} item(s).")
    stop = threading.Event()
    beat = threading.Thread(target=job.heartbeat, args=(stop,), daemon=True)
    beat.start()
    cancelled = False
    try:
        with ThreadPoolExecutor(max_workers=max(1, int(parallel))) as pool:
            for future in [pool.submit(job.run_item, item) for item in items]:
                try:
                    future.result()
                except Cancelled:
                    cancelled = True
    finally:
        stop.set()
        beat.join()
    status = job.status
    if cancelled or job.cancelled():
        status["state"] = "cancelled"
    elif status["errors"] and not status["imported"]:
        status["state"] = "failed"
    else:
        status["state"] = "done"
    status["active"], status["retry"] = {}, ""
    status["finished"] = time.time()
    job.save()
    Path(job_dir, "cancel").unlink(missing_ok=True)
    _log(job_dir, f"Finished ({status['state']}): {len(status['imported'])} imported, "
                  f"{len(status['errors'])} failed.")
    return status


def start_import(job_dir, items, targets, **kwargs) -> None:
    """Start ``run_import`` in its own process; remembers the request for a restart."""
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    request = {"items": items, "targets": targets, **kwargs}
    with open(Path(job_dir, "request.json"), "w", encoding="utf-8") as f:
        json.dump(request, f)
    status_path(job_dir).unlink(missing_ok=True)
    Path(job_dir, "import.log").unlink(missing_ok=True)
    write_status(job_dir, {"state": "running", "heartbeat": time.time(), "starting": True,
                           "total_items": len(items), "done_items": 0, "bytes_total": 0,
                           "bytes_done": 0, "active": {}, "imported": [], "errors": []})
    process = multiprocessing.Process(target=run_import, args=(str(job_dir), items, targets),
                                      kwargs=kwargs, daemon=False)
    process.start()


def restart_import(job_dir) -> bool:
    """Start the last request again: imported items are skipped, partial files resume."""
    try:
        with open(Path(job_dir, "request.json"), "r", encoding="utf-8") as f:
            request = json.load(f)
    except (OSError, ValueError):
        return False
    items, targets = request.pop("items"), request.pop("targets")
    done = {entry.get("id") for entry in read_status(job_dir).get("imported", [])}
    items = [item for item in items if item["id"] not in done]
    start_import(job_dir, items, targets, **request)
    return True
