"""Turn a link into a list of files.

Each source is a function that recognises its links and lists their files.
Supported: Zenodo records, Figshare articles, S3 bucket listings (AWS, CSC
Allas, MinIO, Ceph), OpenStack Swift container listings (CSC Allas), and any
single file over HTTP(S), presigned S3 and Swift TempURL links included. An
uncompressed tar or zip whose server answers Range requests is listed member
by member.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Callable, List, Optional
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit

import requests

from .remote import (
    REQUEST_TIMEOUT,
    RemoteFile,
    archive_type,
    list_tar,
    list_zip,
    name_from_url,
    probe,
)

MAX_LISTING_BYTES = 50 * 1024 * 1024
MAX_LISTED_FILES = 20000
# Archives listed member by member per link; more are offered whole.
MAX_ARCHIVES_TO_OPEN = 10


@dataclass
class Listing:
    """What a link holds."""

    title: str
    url: str
    files: List[RemoteFile] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _json(session: requests.Session, url: str, **kwargs):
    response = session.get(url, timeout=REQUEST_TIMEOUT, headers={"Accept": "application/json"}, **kwargs)
    if response.status_code == 404:
        raise LookupError("Nothing was found at this link (404). Is it public?")
    response.raise_for_status()
    return response.json()


def _text(session: requests.Session, url: str, **kwargs) -> requests.Response:
    response = session.get(url, timeout=REQUEST_TIMEOUT, stream=True, **kwargs)
    body = response.raw.read(MAX_LISTING_BYTES + 1, decode_content=True)
    response.close()
    if len(body) > MAX_LISTING_BYTES:
        raise IOError("The listing is too large.")
    response._content = body
    return response


# ---------------------------------------------------------------------------
# Zenodo
# ---------------------------------------------------------------------------

ZENODO_RE = re.compile(
    r"(?:(?:https?://)?(?P<host>(?:sandbox\.)?zenodo\.org)/(?:records?|deposit|uploads)/(?P<id>\d+))"
    r"|(?:10\.5281/zenodo\.(?P<doi>\d+))",
    re.IGNORECASE,
)


def zenodo(session, link: str) -> Optional[Listing]:
    match = ZENODO_RE.search(link)
    if not match:
        return None
    record_id = match.group("id") or match.group("doi")
    host = (match.group("host") or "zenodo.org").lower()
    data = _json(session, f"https://{host}/api/records/{record_id}")
    files = []
    for entry in data.get("files") or []:
        name = entry.get("key") or entry.get("filename") or ""
        links = entry.get("links") or {}
        url = links.get("content") or links.get("self") or links.get("download") or ""
        if url and not url.endswith("/content") and "/api/records/" in url and "/files/" in url:
            url += "/content"
        checksum = entry.get("checksum") or ""
        files.append(RemoteFile(
            path=name, size=int(entry.get("size") or entry.get("filesize") or 0) or None, url=url,
            md5=checksum[4:] if checksum.startswith("md5:") else "",
        ))
    title = (data.get("metadata") or {}).get("title") or data.get("title") or f"Zenodo record {record_id}"
    return Listing(title=f"Zenodo: {title}", url=f"https://{host}/records/{record_id}", files=files)


# ---------------------------------------------------------------------------
# Figshare
# ---------------------------------------------------------------------------

FIGSHARE_RE = re.compile(
    r"(?:figshare\.com/(?:articles/(?:[^/]+/)*?|ndownloader/articles/)(?P<id>\d+)(?:/(?P<ver>\d+))?/?(?:[?#]|$))"
    r"|(?:10\.6084/m9\.figshare\.(?P<doi>\d+)(?:\.v(?P<dver>\d+))?)",
    re.IGNORECASE,
)


def figshare(session, link: str) -> Optional[Listing]:
    match = FIGSHARE_RE.search(link)
    if not match:
        return None
    article = match.group("id") or match.group("doi")
    version = match.group("ver") or match.group("dver")
    base = f"https://api.figshare.com/v2/articles/{article}"
    data = _json(session, f"{base}/versions/{version}" if version else base)
    files = [
        RemoteFile(path=entry.get("name", ""), size=int(entry.get("size") or 0) or None,
                   url=entry.get("download_url", ""), md5=entry.get("computed_md5") or "")
        for entry in data.get("files") or []
        if not entry.get("is_link_only")
    ]
    return Listing(title=f"Figshare: {data.get('title') or article}",
                   url=data.get("url_public_html") or link, files=files)


# ---------------------------------------------------------------------------
# Object stores
# ---------------------------------------------------------------------------

def _looks_like_folder(url: str) -> bool:
    """A link without a file extension in its last segment, or ending in '/'."""
    path = urlsplit(url).path
    return path.endswith("/") or "." not in PurePosixPath(path).name


def _join(base: str, *parts: str) -> str:
    return base.rstrip("/") + "/" + "/".join(quote(p, safe="/") for p in parts if p)


def swift(session, link: str) -> Optional[Listing]:
    """A public Swift container or prefix (``.../swift/v1/[AUTH_x/]container/prefix/``)."""
    parts = urlsplit(link)
    match = re.match(r"^(?P<root>.*?/swift/v1)/(?P<rest>.+)$", parts.path)
    if not match or not _looks_like_folder(link):
        return None
    segments = [unquote(s) for s in match.group("rest").split("/") if s]
    account = segments.pop(0) if segments and segments[0].startswith("AUTH_") else ""
    if not segments:
        return None
    container, prefix = segments[0], "/".join(segments[1:])
    if prefix:
        prefix += "/"
    container_url = urlunsplit((parts.scheme, parts.netloc,
                                _join(match.group("root"), account, container), "", ""))
    files, marker = [], ""
    while True:
        query = {"format": "json", "limit": 10000, "prefix": prefix}
        if marker:
            query["marker"] = marker
        response = _text(session, f"{container_url}?{urlencode(query)}",
                         headers={"Accept": "application/json"})
        if response.status_code in (401, 403):
            raise LookupError("This Swift container does not allow public listing. "
                              "Link to a single file, or make the container's listing public.")
        if response.status_code == 404:
            raise LookupError("The Swift container was not found.")
        response.raise_for_status()
        entries = response.json()
        for entry in entries:
            name = entry.get("name", "")
            if "subdir" in entry or name.endswith("/"):
                continue
            files.append(RemoteFile(path=name[len(prefix):], size=int(entry.get("bytes") or 0),
                                    url=_join(container_url, name),
                                    md5=entry.get("hash", "") if len(entry.get("hash", "")) == 32 else ""))
        if len(entries) < 10000 or len(files) > MAX_LISTED_FILES:
            break
        marker = entries[-1].get("name") or entries[-1].get("subdir", "")
    return Listing(title=f"Swift container {container}" + (f", folder {prefix}" if prefix else ""),
                   url=link, files=files)


S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def _s3_location(link: str):
    """(bucket URL, prefix) for an S3 folder link, or None."""
    if link.lower().startswith("s3://"):
        rest = link[5:]
        bucket, _, prefix = rest.partition("/")
        return f"https://{bucket}.s3.amazonaws.com", prefix
    parts = urlsplit(link)
    host = (parts.hostname or "").lower()
    path = unquote(parts.path).lstrip("/")
    if re.match(r"^[^.]+\.s3[.-]([a-z0-9-]+\.)?amazonaws\.com$", host):
        return f"{parts.scheme}://{parts.netloc}", path
    bucket, _, prefix = path.partition("/")
    if not bucket:
        return None
    return f"{parts.scheme}://{parts.netloc}/{quote(bucket)}", prefix


def s3(session, link: str) -> Optional[Listing]:
    """A public S3 bucket or prefix, listed with ListObjectsV2 (unsigned)."""
    if not (link.lower().startswith("s3://") or _looks_like_folder(link)):
        return None
    location = _s3_location(link)
    if not location:
        return None
    bucket_url, prefix = location
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    files, token = [], ""
    while True:
        query = {"list-type": 2, "prefix": prefix, "max-keys": 1000}
        if token:
            query["continuation-token"] = token
        response = _text(session, f"{bucket_url}?{urlencode(query)}")
        if b"ListBucketResult" not in response.content[:2000]:
            return None
        root = ET.fromstring(response.content)
        ns = S3_NS if root.tag.startswith(S3_NS) else ""
        for item in root.findall(f"{ns}Contents"):
            key = item.findtext(f"{ns}Key") or ""
            if key.endswith("/"):
                continue
            etag = (item.findtext(f"{ns}ETag") or "").strip('"')
            files.append(RemoteFile(path=key[len(prefix):], size=int(item.findtext(f"{ns}Size") or 0),
                                    url=_join(bucket_url, key),
                                    md5=etag if re.fullmatch(r"[0-9a-f]{32}", etag) else ""))
        token = root.findtext(f"{ns}NextContinuationToken") or ""
        if root.findtext(f"{ns}IsTruncated") != "true" or not token or len(files) > MAX_LISTED_FILES:
            break
    name = bucket_url.rstrip("/").rsplit("/", 1)[-1]
    return Listing(title=f"Bucket {name}" + (f", folder {prefix}" if prefix else ""), url=link, files=files)


# ---------------------------------------------------------------------------
# Single files
# ---------------------------------------------------------------------------

def single_file(session, link: str) -> Optional[Listing]:
    info = probe(session, link)
    if info.content_type == "text/html":
        raise LookupError("This link opens a web page, not a file. Use the file's download link.")
    file = RemoteFile(path=info.name or name_from_url(link) or "download", size=info.size,
                      url=link, etag=info.etag)
    file.ranges = info.ranges
    return Listing(title=file.path, url=link, files=[file])


SOURCES: List[Callable] = [zenodo, figshare, swift, s3, single_file]


def normalize(link: str) -> str:
    link = (link or "").strip()
    if re.match(r"^10\.\d{4,}/", link):
        link = "https://doi.org/" + link
    if not re.match(r"^[a-z][a-z0-9+.-]*://", link, re.IGNORECASE):
        link = "https://" + link
    return link


def _open_archives(session, listing: Listing) -> None:
    """Replace archives the server can serve in pieces by their members."""
    opened = 0
    expanded = []
    for f in listing.files:
        kind = archive_type(f.path)
        if kind not in ("tar", "zip") or opened >= MAX_ARCHIVES_TO_OPEN:
            expanded.append(f)
            continue
        try:
            ranges = getattr(f, "ranges", None)
            if ranges is None or not f.size or not f.etag:
                info = probe(session, f.url)
                f.size, f.etag, ranges = info.size or f.size, info.etag or f.etag, info.ranges
            if not ranges or not f.size:
                listing.notes.append(f"{f.path}: the server does not send parts of files, "
                                     "so the archive is downloaded whole and then unpacked.")
                expanded.append(f)
                continue
            lister = list_tar if kind == "tar" else list_zip
            members = lister(session, f.url, f.size, f.etag, archive_name=f.path)
            opened += 1
            for m in members:
                m.path = f"{f.path}/{m.path}"
            expanded.extend(members)
        except Exception as e:  # offer it whole instead
            listing.notes.append(f"{f.path}: could not read its table of contents ({e}); "
                                 "it is downloaded whole and then unpacked.")
            expanded.append(f)
    listing.files = expanded


def resolve(session: requests.Session, link: str) -> Listing:
    """List the files behind ``link``. Raises LookupError with a message for users."""
    link = normalize(link)
    if urlsplit(link).hostname in ("doi.org", "dx.doi.org"):
        doi = unquote(urlsplit(link).path.lstrip("/"))
        for source in (zenodo, figshare):
            listing = source(session, doi)
            if listing:
                break
        else:
            raise LookupError("Only Zenodo and Figshare DOIs can be imported; "
                              "for other DOIs, link to the data file.")
    else:
        listing = None
        for source in SOURCES:
            listing = source(session, link)
            if listing is not None:
                break
    listing.files = [f for f in listing.files if f.url and f.path][:MAX_LISTED_FILES]
    if not listing.files:
        raise LookupError("No downloadable files were found at this link.")
    _open_archives(session, listing)
    return listing
