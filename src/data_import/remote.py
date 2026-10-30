"""Reading remote files over HTTP: probing, random access, archive listings.

When a server answers Range requests, a tar or zip archive is listed in place:
a tar is a run of 512-byte headers each followed by its file's data, and a zip
keeps a central directory at its end. Each member then downloads as its own
byte range, so a user can pick files out of a large archive, each one resumes
on its own, and the disk never holds the archive next to its extracted copy.
"""
from __future__ import annotations

import io
import re
import struct
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import List, Optional
from urllib.parse import unquote, urlsplit

import requests

REQUEST_TIMEOUT = 60
READ_AHEAD = 64 * 1024
# Upper bounds on what an archive listing may cost.
MAX_MEMBERS = 20000
MAX_LISTING_REQUESTS = 25000


@dataclass
class RemoteFile:
    """One file to download.

    ``path`` is its path in the source (folder/name). For an archive member,
    ``url`` is the archive's, the file's bytes start at ``offset`` (a zip
    member's offset is only known once its local header is read, so
    ``zip_header`` holds that header's offset instead), take ``stored_size``
    bytes there, and are raw-deflate compressed if ``deflate`` is set.
    """

    path: str
    size: Optional[int]
    url: str
    md5: str = ""
    etag: str = ""
    archive: str = ""
    offset: Optional[int] = None
    zip_header: Optional[int] = None
    stored_size: Optional[int] = None
    deflate: bool = False
    crc32: Optional[int] = None

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name


@dataclass
class Probe:
    name: str
    size: Optional[int]
    ranges: bool
    etag: str
    content_type: str = ""
    extras: dict = field(default_factory=dict)


def _filename_from_disposition(value: str) -> str:
    match = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", value or "", re.IGNORECASE)
    if match:
        return unquote(match.group(1).strip().strip('"'))
    match = re.search(r'filename\s*=\s*"?([^";]+)"?', value or "", re.IGNORECASE)
    return match.group(1).strip() if match else ""


def name_from_url(url: str) -> str:
    return unquote(PurePosixPath(urlsplit(url).path).name)


def probe(session: requests.Session, url: str) -> Probe:
    """Name, size, Range support and ETag of ``url``, from one ranged GET.

    A GET for the first byte rather than a HEAD: presigned links are signed
    for GET only, and a 206 answer proves Range support.
    """
    with session.get(url, headers={"Range": "bytes=0-0"}, stream=True,
                     timeout=REQUEST_TIMEOUT) as response:
        response.raise_for_status()
        headers = response.headers
        size, ranges = None, False
        if response.status_code == 206:
            match = re.search(r"/(\d+)\s*$", headers.get("Content-Range", ""))
            if match:
                size, ranges = int(match.group(1)), True
        elif headers.get("Content-Length", "").isdigit():
            size = int(headers["Content-Length"])
        name = _filename_from_disposition(headers.get("Content-Disposition", "")) \
            or name_from_url(response.url) or name_from_url(url)
        return Probe(
            name=PurePosixPath(name).name,
            size=size,
            ranges=ranges,
            etag=headers.get("ETag", ""),
            content_type=headers.get("Content-Type", "").split(";")[0].strip().lower(),
        )


class RangeFile(io.RawIOBase):
    """A read-only, seekable file over HTTP Range requests, with read-ahead."""

    def __init__(self, session: requests.Session, url: str, size: int, etag: str = "",
                 max_requests: int = MAX_LISTING_REQUESTS):
        super().__init__()
        self.session, self.url, self.size, self.etag = session, url, size, etag
        self.pos = 0
        self.requests = 0
        self.max_requests = max_requests
        self._buf_start, self._buf = 0, b""

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        else:
            self.pos = self.size + offset
        self.pos = max(self.pos, 0)
        return self.pos

    def fetch(self, start: int, end: int) -> bytes:
        """Bytes ``start``..``end`` inclusive, from one Range request."""
        self.requests += 1
        if self.requests > self.max_requests:
            raise IOError("Reading the archive's table of contents needs too many requests.")
        headers = {"Range": f"bytes={start}-{end}"}
        if self.etag:
            headers["If-Range"] = self.etag
        response = self.session.get(self.url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        if response.status_code != 206:
            raise IOError("The server stopped answering Range requests.")
        return response.content

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        n = min(len(b), self.size - self.pos)
        offset = self.pos - self._buf_start
        if not (0 <= offset and offset + n <= len(self._buf)):
            end = min(self.size, self.pos + max(n, READ_AHEAD)) - 1
            self._buf_start, self._buf = self.pos, self.fetch(self.pos, end)
            offset = 0
        chunk = self._buf[offset:offset + n]
        b[:len(chunk)] = chunk
        self.pos += len(chunk)
        return len(chunk)


def safe_member_path(name: str) -> Optional[str]:
    """``name`` as a relative path inside the archive, or None if it escapes."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    parts = [p for p in path.parts if p not in ("", ".")]
    return "/".join(parts) or None


def list_tar(session: requests.Session, url: str, size: int, etag: str = "",
             archive_name: str = "") -> List[RemoteFile]:
    """The regular files in an uncompressed tar at ``url``."""
    files = []
    with tarfile.open(fileobj=RangeFile(session, url, size, etag), mode="r:") as tar:
        for member in tar:
            if len(files) >= MAX_MEMBERS:
                raise IOError(f"The archive holds more than {MAX_MEMBERS} files.")
            path = safe_member_path(member.name)
            if not member.isfile() or path is None or member.sparse:
                continue
            files.append(RemoteFile(path=path, size=member.size, url=url, etag=etag,
                                    archive=archive_name, offset=member.offset_data,
                                    stored_size=member.size))
    return files


def list_zip(session: requests.Session, url: str, size: int, etag: str = "",
             archive_name: str = "") -> List[RemoteFile]:
    """The stored or deflated, unencrypted files in a zip at ``url``."""
    files = []
    with zipfile.ZipFile(RangeFile(session, url, size, etag)) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise IOError(f"The archive holds more than {MAX_MEMBERS} files.")
        for info in infos:
            path = safe_member_path(info.filename)
            if info.is_dir() or path is None or info.flag_bits & 0x1:
                continue
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                continue
            files.append(RemoteFile(path=path, size=info.file_size, url=url, etag=etag,
                                    archive=archive_name, zip_header=info.header_offset,
                                    stored_size=info.compress_size,
                                    deflate=info.compress_type == zipfile.ZIP_DEFLATED,
                                    crc32=info.CRC))
    return files


def zip_data_offset(session: requests.Session, f: RemoteFile) -> int:
    """Where a zip member's data starts: after its local header."""
    header = RangeFile(session, f.url, f.zip_header + 30, f.etag).fetch(f.zip_header, f.zip_header + 29)
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise IOError(f"{f.path}: the archive's local file header is damaged.")
    name_len, extra_len = struct.unpack("<HH", header[26:30])
    return f.zip_header + 30 + name_len + extra_len


def archive_type(name: str) -> str:
    """'tar' or 'zip' for archives that can be read in place, 'packed' for
    compressed tars (only unpacked after a full download), else ''."""
    lower = name.lower()
    if lower.endswith(".tar"):
        return "tar"
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
        return "packed"
    return ""
