"""Turn a link into a list of files.

Each source is a function that recognises its links and lists their files.
Supported: PRIDE Archive datasets (by accession), Zenodo records, Figshare
articles, OneDrive and SharePoint sharing
links, S3 bucket listings (AWS, CSC Allas, MinIO, Ceph), OpenStack Swift
container listings (CSC Allas), and any
single file over HTTP(S), presigned S3 and Swift TempURL links included. An
uncompressed tar or zip whose server answers Range requests is listed member
by member.
"""
from __future__ import annotations

import base64
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Callable, List, Optional
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import requests

from .remote import (
    REQUEST_TIMEOUT,
    RemoteFile,
    archive_type,
    list_tar,
    list_zip,
    name_from_url,
    probe,
    safe_member_path,
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


def _json(session: requests.Session, url: str, headers: Optional[dict] = None, **kwargs):
    response = session.get(url, timeout=REQUEST_TIMEOUT,
                           headers={"Accept": "application/json", **(headers or {})}, **kwargs)
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
# PRIDE Archive
# ---------------------------------------------------------------------------

PRIDE_API = "https://www.ebi.ac.uk/pride/ws/archive/v3"
PRIDE_PAGE = "https://www.ebi.ac.uk/pride/archive/projects/{accession}"
PRIDE_PAGE_SIZE = 100
PRIDE_ACCESSION_RE = re.compile(r"\b(P[XR]D\d{6})\b", re.IGNORECASE)
# Hosts whose links name a dataset rather than one of its files
PRIDE_HOSTS = ("www.ebi.ac.uk", "ebi.ac.uk", "proteomecentral.proteomexchange.org",
               "identifiers.org", "ftp.pride.ebi.ac.uk")
# Vendor files the converted mzML of the same run makes unnecessary to download
_PRIDE_VENDOR_SUFFIXES = (".raw", ".d.zip", ".d.tar", ".d.tar.gz", ".wiff", ".wiff.scan")
# Larger datasets start with nothing ticked, so a click does not start terabytes
PRIDE_PRESELECT_MAX_BYTES = 50 * 10**9


def pride_accession(link: str) -> str:
    """The PRIDE accession a link or a bare accession names ('' if none).

    Accepts ``PXD000001`` (any case), the PRIDE project page, the
    ProteomeXchange page, identifiers.org, the DOI ``10.6019/PXD000001`` and
    the dataset's folder on the PRIDE FTP server. A link to a single file on
    the FTP server is left to the single-file source.
    """
    link = (link or "").strip()
    match = PRIDE_ACCESSION_RE.fullmatch(link) or re.fullmatch(
        r"(?:https?://(?:dx\.)?doi\.org/)?10\.6019/(P[XR]D\d{6})", link, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    parts = urlsplit(link if "://" in link else "https://" + link)
    host = (parts.hostname or "").lower()
    if PRIDE_ACCESSION_RE.fullmatch(host):
        return host.upper()  # a bare accession, after normalize() made it a link
    if host not in PRIDE_HOSTS:
        return ""
    if host == "ftp.pride.ebi.ac.uk" and not _looks_like_folder(link):
        return ""
    match = PRIDE_ACCESSION_RE.search(unquote(parts.path) + "?" + unquote(parts.query))
    return match.group(1).upper() if match else ""


def _pride_url(entry: dict) -> str:
    """HTTPS link of a PRIDE file: its FTP server serves the same paths over HTTPS."""
    for location in entry.get("publicFileLocations") or []:
        value = location.get("value", "")
        if value.startswith("ftp://"):
            return "https://" + value[len("ftp://"):]
        if value.startswith("https://"):
            return value
    return ""


def _pride_names(entries) -> List[str]:
    names = []
    for entry in entries or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if name and str(name) not in names:
            names.append(str(name))
    return names


def _run_name(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    for suffix in (".gz", ".zip", ".tar"):
        name = name.removesuffix(suffix)
    return name.rsplit(".", 1)[0] if "." in name else name


def pride(session, link: str) -> Optional[Listing]:
    """A PRIDE Archive dataset: its files, with the project's description as notes.

    When a run is there both as mzML and as a vendor file, only the mzML is
    selected at first.
    """
    accession = pride_accession(link)
    if not accession:
        return None
    try:
        project = _json(session, f"{PRIDE_API}/projects/{accession}")
    except LookupError:
        raise LookupError(f"{accession} was not found in PRIDE, or is not public yet.") from None
    files, page = [], 0
    while len(files) <= MAX_LISTED_FILES:
        entries = _json(session, f"{PRIDE_API}/projects/{accession}/files",
                        params={"pageSize": PRIDE_PAGE_SIZE, "page": page})
        if isinstance(entries, dict):  # older HAL responses
            entries = (entries.get("_embedded") or {}).get("files", [])
        for entry in entries:
            checksum = (entry.get("checksum") or "").lower()
            files.append(RemoteFile(
                path=entry.get("fileName", ""), size=int(entry.get("fileSizeBytes") or 0) or None,
                url=_pride_url(entry), md5=checksum if re.fullmatch(r"[0-9a-f]{32}", checksum) else "",
            ))
        if len(entries) < PRIDE_PAGE_SIZE:
            break
        page += 1
    mzml_runs = {_run_name(f.path) for f in files
                 if f.path.lower().removesuffix(".gz").endswith(".mzml")}
    for f in files:
        if (f.path.lower().removesuffix(".gz").endswith(_PRIDE_VENDOR_SUFFIXES)
                and _run_name(f.path) in mzml_runs):
            f.preselect = False

    notes = []
    ticked = sum(f.size or 0 for f in files if f.preselect)
    if ticked > PRIDE_PRESELECT_MAX_BYTES:
        for f in files:
            f.preselect = False
        notes.append(f"The dataset holds {ticked / 1e9:.0f} GB, so no file is ticked at first: "
                     "tick the runs to reanalyse.")
    facts = [("Organisms", project.get("organisms")), ("Instruments", project.get("instruments")),
             ("Modifications", project.get("identifiedPTMStrings")),
             ("Quantification", project.get("quantificationMethods"))]
    line = "; ".join(f"{label}: {', '.join(_pride_names(values))}"
                     for label, values in facts if _pride_names(values))
    if line:
        notes.append(line)
    description = (project.get("projectDescription") or "").strip()
    if description:
        notes.append(description if len(description) <= 600 else description[:600].rsplit(" ", 1)[0] + " ...")
    if mzml_runs and ticked <= PRIDE_PRESELECT_MAX_BYTES and any(not f.preselect for f in files):
        notes.append("Runs that are in the dataset as mzML too are selected only as mzML; "
                     "tick their vendor files to download those as well.")
    title = project.get("title") or accession
    return Listing(title=f"PRIDE {accession}: {title}", url=PRIDE_PAGE.format(accession=accession),
                   files=files, notes=notes)


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
# OneDrive and SharePoint
# ---------------------------------------------------------------------------

ONEDRIVE_API = "https://api.onedrive.com/v1.0"
# Personal OneDrive moved onto SharePoint ("migratedtospo"); its shares are
# also served here.
ONEDRIVE_PERSONAL_API = "https://my.microsoftpersonalcontent.com/_api/v2.0"
# An anonymous token for public personal shares, the one onedrive.live.com
# itself asks for before it shows a shared folder to a visitor.
BADGER_TOKEN_URL = "https://api-badgerp.svc.ms/v1.0/token"
BADGER_APP_UUID = "5cbed6ac-a083-4e14-b191-b4ba07653de2"
BADGER_APP_ID = "1141147648"
BADGER_LIFETIME = 30 * 60
ONEDRIVE_MAX_DEPTH = 20

_badger: dict = {}


def _is_onedrive(host: str) -> bool:
    host = host.lower()
    return host in ("1drv.ms", "onedrive.live.com", "photos.onedrive.com") \
        or host.endswith(".sharepoint.com")


def share_id(link: str) -> str:
    """The id the OneDrive shares API takes for a sharing link: 'u!' + base64url."""
    return "u!" + base64.urlsafe_b64encode(link.encode()).decode().rstrip("=")


def sharing_link(link: str) -> str:
    """The sharing link behind a OneDrive page link.

    Opening a ``1drv.ms`` link lands on ``onedrive.live.com/?id=...&redeem=...``,
    whose ``redeem`` parameter is the sharing link in base64; users often copy
    that address from the browser instead of the link they were sent.
    """
    parts = urlsplit(link)
    if (parts.hostname or "").lower() != "onedrive.live.com":
        return link
    redeem = dict(parse_qsl(parts.query)).get("redeem", "")
    if not redeem:
        return link
    try:
        decoded = base64.b64decode(redeem.replace("-", "+").replace("_", "/")
                                   + "=" * (-len(redeem) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return link
    host = (urlsplit(decoded).hostname or "").lower()
    if urlsplit(decoded).scheme in ("http", "https") and host in ("1drv.ms", "onedrive.live.com"):
        return decoded
    return link


def with_download(link: str) -> str:
    """A sharing link that answers with the file instead of the preview page."""
    parts = urlsplit(link)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "download"]
    query.append(("download", "1"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _badger_headers(session) -> dict:
    """Headers that let a visitor read a public personal OneDrive share."""
    if _badger.get("token") and _badger.get("expires", 0) > time.time():
        token = _badger["token"]
    else:
        response = session.post(BADGER_TOKEN_URL, json={"appId": BADGER_APP_UUID},
                                headers={"AppId": BADGER_APP_ID, "Accept": "application/json"},
                                timeout=REQUEST_TIMEOUT, allow_redirects=False)
        response.raise_for_status()
        token = response.json().get("token") or ""
        if not token:
            raise ValueError("OneDrive gave no token.")
        _badger.update(token=token, expires=time.time() + BADGER_LIFETIME)
    return {"Authorization": f"Badger {token}", "Prefer": "autoredeem"}


@dataclass
class _Share:
    """Where a share was read: the API, the headers it needed, its id."""

    api: str
    headers: dict
    id: str


def _onedrive_children(session, share: _Share, item: dict):
    drive = (item.get("parentReference") or {}).get("driveId") or ""
    item_id = quote(item.get("id", ""), safe="")
    try:
        return _json(session, f"{share.api}/drives/{quote(drive, safe='')}/items/{item_id}/children",
                     headers=share.headers)
    except (requests.RequestException, LookupError, ValueError):
        # A folder of a share the visitor has not redeemed is read through the share.
        return _json(session, f"{share.api}/shares/{share.id}/items/{item_id}/children",
                     headers=share.headers)


def _onedrive_pages(session, share: _Share, children, next_url):
    while True:
        yield from children or []
        if not next_url or not next_url.startswith(share.api + "/"):
            return
        page = _json(session, next_url, headers=share.headers)
        children, next_url = page.get("value", []), page.get("@odata.nextLink")


def _onedrive_files(session, share: _Share, item: dict, prefix: str, depth: int,
                    files: List[RemoteFile]) -> None:
    name = item.get("name") or ""
    if name in ("", ".", "..") or "/" in name or "\\" in name:
        return
    path = f"{prefix}/{name}" if prefix else name
    if "file" in item:
        url = item.get("@content.downloadUrl") or item.get("@microsoft.graph.downloadUrl") or ""
        hashes = (item.get("file") or {}).get("hashes") or {}
        files.append(RemoteFile(path=path, size=item.get("size"), url=url,
                                md5=(hashes.get("md5Hash") or "").lower()))
        return
    if "folder" not in item or depth > ONEDRIVE_MAX_DEPTH or len(files) > MAX_LISTED_FILES:
        return
    children, next_url = item.get("children"), item.get("children@odata.nextLink")
    if children is None:
        page = _onedrive_children(session, share, item)
        children, next_url = page.get("value", []), page.get("@odata.nextLink")
    for child in _onedrive_pages(session, share, children, next_url):
        _onedrive_files(session, share, child, path, depth + 1, files)


def _onedrive_share(session, link: str):
    """The shared item and where it was read, or ``(None, None)``.

    Older personal shares answer without a sign-in; shares made since
    personal OneDrive moved onto SharePoint want the anonymous visitor token.
    """
    sid = share_id(link)
    attempts = [
        (ONEDRIVE_API, lambda: {}, "root"),
        (ONEDRIVE_API, lambda: _badger_headers(session), "root"),
        (ONEDRIVE_PERSONAL_API, lambda: _badger_headers(session), "driveitem"),
    ]
    for api, headers_for, item in attempts:
        try:
            headers = headers_for()
            root = _json(session, f"{api}/shares/{sid}/{item}?$expand=children", headers=headers)
        except (requests.RequestException, LookupError, ValueError):
            continue
        if root and ("file" in root or "folder" in root):
            return root, _Share(api=api, headers=headers, id=sid)
    return None, None


def onedrive(session, link: str) -> Optional[Listing]:
    """A OneDrive or SharePoint sharing link ("Anyone with the link").

    Personal OneDrive shares are read through the public shares API, which
    lists folders too; the address of a shared folder opened in the browser
    (``onedrive.live.com/?...&redeem=...``) works as well. SharePoint and
    OneDrive for Business only allow that API with a signed-in app, so their
    links work for single files, fetched with ``download=1``.
    """
    host = urlsplit(link).hostname or ""
    if not _is_onedrive(host):
        return None
    if not host.endswith(".sharepoint.com"):
        root, share = _onedrive_share(session, sharing_link(link))
        if root is not None:
            files: List[RemoteFile] = []
            if "folder" in root:
                for child in _onedrive_pages(session, share, root.get("children"),
                                             root.get("children@odata.nextLink")):
                    _onedrive_files(session, share, child, "", 1, files)
            else:
                _onedrive_files(session, share, root, "", 0, files)
            return Listing(title=f"OneDrive: {root.get('name', '')}", url=link, files=files,
                           notes=["OneDrive download links expire after about an hour: "
                                  "if an import stops for longer, look the link up again."])
    info = probe(session, with_download(link))
    if info.content_type == "text/html":
        raise LookupError(
            "This OneDrive/SharePoint link needs a sign-in, or is a folder that can only be "
            "read with a sign-in. Share the file with \"Anyone with the link\" and paste "
            "that link, or share a zip of the folder."
        )
    url = with_download(link)
    file = RemoteFile(path=info.name or "download", size=info.size, url=url, etag=info.etag)
    file.ranges = info.ranges
    return Listing(title=file.path, url=link, files=[file])


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


SOURCES: List[Callable] = [pride, zenodo, figshare, onedrive, swift, s3, single_file]


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
                m.preselect = f.preselect
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
        for source in (pride, zenodo, figshare):
            listing = source(session, doi)
            if listing:
                break
        else:
            raise LookupError("Only PRIDE, Zenodo and Figshare DOIs can be imported; "
                              "for other DOIs, link to the data file.")
    else:
        listing = None
        for source in SOURCES:
            listing = source(session, link)
            if listing is not None:
                break
    listing.files = [f for f in listing.files
                     if f.url and f.path and safe_member_path(f.path)][:MAX_LISTED_FILES]
    if not listing.files:
        raise LookupError("No downloadable files were found at this link.")
    _open_archives(session, listing)
    return listing
