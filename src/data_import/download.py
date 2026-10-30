"""Resumable, verified downloads of whole files and byte ranges."""
from __future__ import annotations

import hashlib
import os
import time
import zlib
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
        if done and etag:
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
