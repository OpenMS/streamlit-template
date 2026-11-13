"""Resumable, verified downloads of whole files and byte ranges."""
from __future__ import annotations

import hashlib
import math
import os
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from typing import Callable, Optional

import requests

REQUEST_TIMEOUT = 60
# Small enough that a dropped connection loses little: a read cut short
# loses the bytes of its unfinished chunk.
CHUNK_SIZE = 256 * 1024
# Retry with back-off, at most a minute apart, and give up after this long
# without any progress (the workspace sync uses the same numbers).
MAX_BACKOFF = 60
GIVE_UP_AFTER = 15 * 60
# A large file is fetched as several byte ranges over parallel connections:
# one connection to a distant server is limited by its round-trip time (a few
# MB/s to the PRIDE archive), and the throughput grows with the connections.
# Ranges of this size keep the extra requests negligible; a file needs two of
# them before it is split.
SEGMENT_SIZE = 64 * 1024 * 1024


class Cancelled(Exception):
    pass


class TooLarge(Exception):
    pass


class _Retry(Exception):
    pass


def part_path(dest: Path) -> Path:
    return dest.with_name(f".{dest.name}.part")


def download(
    session: requests.Session,
    url: str,
    dest: Path,
    *,
    start: int = 0,
    length: Optional[int] = None,
    etag: str = "",
    max_bytes: Optional[int] = None,
    on_progress: Callable[[int], None] = None,
    on_retry: Callable[[str], None] = None,
    should_cancel: Callable[[], bool] = None,
    give_up_after: float = GIVE_UP_AFTER,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Download ``url`` (or ``length`` bytes from ``start``) to ``dest``.

    Bytes go to a hidden ``.part`` file next to ``dest`` that later calls
    resume with a Range request, also after a restart. ``etag`` is sent as
    If-Range, so a file that changed on the server starts over instead of
    being stitched together. A dropped connection is retried with back-off
    until ``give_up_after`` seconds pass without progress.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = part_path(dest)
    ranged = start > 0 or length is not None
    last_progress = time.monotonic()
    attempt = 0
    while True:
        done = part.stat().st_size if part.exists() else 0
        if length is not None and done >= length:
            break
        if max_bytes is not None and done > max_bytes:
            raise TooLarge(f"{dest.name} is larger than the {max_bytes / 1e9:.1f} GB limit.")
        try:
            done = _transfer(session, url, part, done, start, length, ranged, etag, max_bytes,
                             on_progress, should_cancel)
            if done is None:  # complete
                break
            last_progress = time.monotonic()
            attempt = 0
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError, _Retry) as e:
            progressed = part.exists() and part.stat().st_size > done
            if progressed:
                last_progress, attempt = time.monotonic(), 0
            if time.monotonic() - last_progress > give_up_after:
                raise IOError(f"{dest.name}: no progress for {int(give_up_after / 60)} minutes ({e}).") from e
            wait = min(MAX_BACKOFF, 2 ** attempt)
            attempt += 1
            if on_retry:
                on_retry(f"Connection lost ({type(e).__name__}), retrying in {wait} s")
            _sleep_unless_cancelled(sleep, wait, should_cancel)
    if length is not None and part.stat().st_size != length:
        raise IOError(f"{dest.name}: got {part.stat().st_size} bytes, expected {length}.")
    os.replace(part, dest)
    return dest


def _sleep_unless_cancelled(sleep, seconds, should_cancel):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if should_cancel and should_cancel():
            raise Cancelled()
        sleep(min(1.0, max(0.0, end - time.monotonic())))


def _transfer(session, url, part, done, start, length, ranged, etag, max_bytes,
              on_progress, should_cancel) -> Optional[int]:
    """One request. Returns None once the file is complete, else bytes so far."""
    headers = {}
    if done or ranged:
        end = "" if length is None else str(start + length - 1)
        headers["Range"] = f"bytes={start + done}-{end}"
        if etag and (done or not etag.startswith("W/")):
            # A file that changed on the server is answered whole, never with
            # a part of its new version (a weak ETag never matches If-Range,
            # so it is sent only to resume, as before).
            headers["If-Range"] = etag
    with session.get(url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT) as response:
        if response.status_code == 416 and done and length is None:
            return None  # the .part file already holds everything
        if response.status_code in (408, 425, 429) or response.status_code >= 500:
            raise _Retry(f"HTTP {response.status_code}")
        response.raise_for_status()
        if headers.get("Range") and response.status_code != 206:
            if ranged:
                raise IOError("The server stopped sending parts of the file.")
            done = 0  # whole file again: the server ignored the range or the file changed
        total_expected = length
        if total_expected is None and response.status_code == 200:
            cl = response.headers.get("Content-Length", "")
            total_expected = int(cl) if cl.isdigit() else None
        if max_bytes is not None and total_expected is not None and total_expected > max_bytes:
            raise TooLarge(f"The file is larger than the {max_bytes / 1e9:.1f} GB limit.")
        with open(part, "ab" if done else "wb") as f:
            for chunk in response.iter_content(CHUNK_SIZE):
                if should_cancel and should_cancel():
                    raise Cancelled()
                if length is not None and done + len(chunk) > length:
                    chunk = chunk[:length - done]
                f.write(chunk)
                done += len(chunk)
                if max_bytes is not None and done > max_bytes:
                    raise TooLarge(f"The file is larger than the {max_bytes / 1e9:.1f} GB limit.")
                if on_progress:
                    on_progress(done)
                if length is not None and done >= length:
                    break
    if length is not None:
        return None if done >= length else done
    content_range = response.headers.get("Content-Range", "")
    if response.status_code == 206 and "/" in content_range:
        total = content_range.rsplit("/", 1)[1]
        if total.isdigit() and done < int(total) - start:
            return done
    elif total_expected is not None and done < total_expected:
        return done
    return None


def segment_path(dest: Path, index: int) -> Path:
    return dest.with_name(f".{dest.name}.seg{index}")


def segments(size: int, connections: int):
    """(start, length) of the ranges a file of ``size`` bytes is fetched in:
    one when it is small, otherwise at least ``SEGMENT_SIZE`` bytes each and
    twice as many as connections, so a slow connection holds up little."""
    count = min(math.ceil(size / SEGMENT_SIZE), 2 * max(1, connections))
    if size < 2 * SEGMENT_SIZE or count < 2:
        return [(0, size)]
    step = math.ceil(size / count)
    return [(start, min(step, size - start)) for start in range(0, size, step)]


def download_parallel(
    session: requests.Session,
    url: str,
    dest: Path,
    size: int,
    *,
    connections: int = 4,
    slots: Optional[threading.Semaphore] = None,
    etag: str = "",
    max_bytes: Optional[int] = None,
    on_progress: Callable[[int], None] = None,
    on_retry: Callable[[str], None] = None,
    should_cancel: Callable[[], bool] = None,
    give_up_after: float = GIVE_UP_AFTER,
    sleep: Callable[[float], None] = time.sleep,
):
    """Download ``url`` (``size`` bytes, served in ranges) over up to
    ``connections`` connections at once; returns ``dest`` and its MD5.

    Each range is its own ``download`` into a hidden ``.seg<n>`` file, so it
    resumes and retries on its own, also after a restart. ``slots``, shared by
    the downloads of one import, caps the connections all of them hold. The
    ranges are joined in order while the MD5 is computed, so the file is not
    read a second time to check it.
    """
    dest = Path(dest)
    if max_bytes is not None and size > max_bytes:
        raise TooLarge(f"{dest.name} is larger than the {max_bytes / 1e9:.1f} GB limit.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    ranges = segments(size, connections)
    lock = threading.Lock()
    done = [0] * len(ranges)
    failed = threading.Event()

    def cancelled():
        return failed.is_set() or bool(should_cancel and should_cancel())

    def fetch(index):
        start, length = ranges[index]
        path = segment_path(dest, index)
        if path.exists() and path.stat().st_size == length:
            done[index] = length
            return

        def progress(n):
            with lock:
                done[index] = n
                total = sum(done)
            if on_progress:
                on_progress(total)

        with slots or nullcontext():
            try:
                download(session, url, path, start=start, length=length, etag=etag,
                         on_progress=progress, on_retry=on_retry, should_cancel=cancelled,
                         give_up_after=give_up_after, sleep=sleep)
            except BaseException:
                failed.set()
                raise

    with ThreadPoolExecutor(max_workers=max(1, min(connections, len(ranges)))) as pool:
        futures = [pool.submit(fetch, i) for i in range(len(ranges))]
    errors = [f.exception() for f in futures if f.exception() is not None]
    if errors:
        # The first real error, not the Cancelled it caused in the other ranges
        raise next((e for e in errors if not isinstance(e, Cancelled)), errors[0])
    digest = hashlib.md5()
    part = part_path(dest)
    with open(part, "wb") as out:
        for index in range(len(ranges)):
            with open(segment_path(dest, index), "rb") as f:
                for chunk in iter(lambda: f.read(CHUNK_SIZE * 4), b""):
                    digest.update(chunk)
                    out.write(chunk)
    if part.stat().st_size != size:
        raise IOError(f"{dest.name}: got {part.stat().st_size} bytes, expected {size}.")
    os.replace(part, dest)
    for index in range(len(ranges)):
        segment_path(dest, index).unlink(missing_ok=True)
    return dest, digest.hexdigest()


def md5sum(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inflate(src: Path, dest: Path, expected_size: int, crc32: Optional[int]) -> Path:
    """Raw-deflate ``src`` (a zip member's data) into ``dest``, checking size and CRC."""
    decompressor = zlib.decompressobj(-15)
    crc, size = 0, 0
    tmp = part_path(dest)
    with open(src, "rb") as fin, open(tmp, "wb") as fout:
        for chunk in iter(lambda: fin.read(CHUNK_SIZE), b""):
            data = decompressor.decompress(chunk)
            size += len(data)
            if size > expected_size:
                raise IOError(f"{dest.name} unpacks to more than its listed size.")
            crc = zlib.crc32(data, crc)
            fout.write(data)
        data = decompressor.flush()
        size += len(data)
        crc = zlib.crc32(data, crc)
        fout.write(data)
    if size != expected_size or (crc32 is not None and crc != crc32):
        tmp.unlink(missing_ok=True)
        raise IOError(f"{dest.name}: the unpacked file does not match the archive's checksum.")
    os.replace(tmp, dest)
    src.unlink()
    return dest
