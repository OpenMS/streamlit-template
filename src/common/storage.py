"""Workspace storage: local paths, or the same files through S3.

Streamlit-free, so it works in the RQ worker as well.

With the S3 storage tier (``k8s/storage-s3/`` plus the overlay component
``k8s/components/storage-s3/``) the workspace directory is a JuiceFS mount,
and the JuiceFS S3 gateway serves the same files as objects: the app's
directory is the bucket, a file's path below ``WORKSPACES_DIR`` is its key.
Everything keeps working on the mounted path; this module is for the code
that wants S3 on top of it:

    import polars as pl
    from src.common import storage

    lf = pl.scan_parquet(storage.uri(path), storage_options=storage.options())
    url = storage.presigned_url(path)   # None without S3

Without the tier (desktop app, Manila, docker-compose) ``uri()`` returns the
local path, ``options()`` returns ``None`` and ``presigned_url()`` returns
``None``, so the same code runs everywhere.

Configuration comes from the environment, set by the overlay component:

    WORKSPACES_S3_ENDPOINT    gateway URL, e.g. http://juicefs-s3-gateway.openms-storage.svc:9000
    WORKSPACES_S3_BUCKET      the app's bucket (its slug)
    WORKSPACES_S3_ACCESS_KEY  gateway credentials
    WORKSPACES_S3_SECRET_KEY
    WORKSPACES_S3_REGION      optional, default us-east-1
    WORKSPACES_DIR            the mounted workspace root
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
from urllib.parse import quote, urlsplit

DEFAULT_WORKSPACES_DIR = "/workspaces-streamlit-template"
DEFAULT_REGION = "us-east-1"

PathLike = Union[str, os.PathLike]


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str = DEFAULT_REGION


def s3_config() -> Optional[S3Config]:
    """The S3 settings, or None when the app is not on the S3 tier."""
    env = os.environ
    values = {
        "endpoint": env.get("WORKSPACES_S3_ENDPOINT", "").strip().rstrip("/"),
        "bucket": env.get("WORKSPACES_S3_BUCKET", "").strip(),
        "access_key": env.get("WORKSPACES_S3_ACCESS_KEY", "").strip(),
        "secret_key": env.get("WORKSPACES_S3_SECRET_KEY", "").strip(),
    }
    if not all(values.values()):
        return None
    return S3Config(
        region=env.get("WORKSPACES_S3_REGION", "").strip() or DEFAULT_REGION,
        **values,
    )


def s3_enabled() -> bool:
    """True when workspace files are also reachable through S3."""
    return s3_config() is not None


def workspaces_root() -> Path:
    return Path(os.environ.get("WORKSPACES_DIR") or DEFAULT_WORKSPACES_DIR)


def object_key(path: PathLike) -> Optional[str]:
    """The S3 key of a file under the workspace root, else None."""
    root = Path(os.path.abspath(workspaces_root()))
    target = Path(os.path.abspath(os.fspath(path)))
    try:
        rel = target.relative_to(root)
    except ValueError:
        return None
    key = rel.as_posix()
    return key if key not in ("", ".") else None


def uri(path: PathLike) -> str:
    """``s3://<bucket>/<key>`` on the S3 tier, otherwise the local path.

    Paths outside the workspace root (e.g. files shipped in the image) always
    stay local.
    """
    cfg = s3_config()
    key = object_key(path) if cfg else None
    if cfg is None or key is None:
        return os.fspath(path)
    return f"s3://{cfg.bucket}/{key}"


def options() -> Optional[dict]:
    """``storage_options`` for polars (object_store keys), or None."""
    cfg = s3_config()
    if cfg is None:
        return None
    opts = {
        "aws_endpoint_url": cfg.endpoint,
        "aws_access_key_id": cfg.access_key,
        "aws_secret_access_key": cfg.secret_key,
        "aws_region": cfg.region,
        "aws_virtual_hosted_style_request": "false",
    }
    if cfg.endpoint.startswith("http://"):
        opts["aws_allow_http"] = "true"
    return opts


def presigned_url(
    path: PathLike,
    expires: int = 3600,
    method: str = "GET",
    endpoint: Optional[str] = None,
    now: Optional[_dt.datetime] = None,
) -> Optional[str]:
    """A presigned S3 URL for a workspace file, or None without S3.

    ``endpoint`` overrides the configured one, for a link the browser opens
    (the in-cluster gateway address is not reachable from outside).
    """
    cfg = s3_config()
    key = object_key(path) if cfg else None
    if cfg is None or key is None:
        return None
    base = (endpoint or cfg.endpoint).rstrip("/")
    parts = urlsplit(base)
    prefix = parts.path.rstrip("/")
    canonical_uri = (
        f"{prefix}/{_quote(cfg.bucket)}/" + "/".join(_quote(p) for p in key.split("/"))
    )
    query = _presign_query(
        method=method,
        host=parts.netloc,
        canonical_uri=canonical_uri,
        access_key=cfg.access_key,
        secret_key=cfg.secret_key,
        region=cfg.region,
        expires=expires,
        now=now,
    )
    return f"{parts.scheme}://{parts.netloc}{canonical_uri}?{query}"


def _quote(segment: str) -> str:
    return quote(segment, safe="-_.~")


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _presign_query(
    method: str,
    host: str,
    canonical_uri: str,
    access_key: str,
    secret_key: str,
    region: str,
    expires: int,
    now: Optional[_dt.datetime] = None,
) -> str:
    """AWS Signature Version 4 query string for a presigned request."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")
    scope = f"{date}/{region}/s3/aws4_request"
    params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(int(expires)),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = "&".join(
        f"{_quote(k)}={_quote(v)}" for k, v in sorted(params.items())
    )
    canonical_request = "\n".join(
        [method, canonical_uri, canonical_query, f"host:{host}", "", "host", "UNSIGNED-PAYLOAD"]
    )
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    k = _sign(("AWS4" + secret_key).encode("utf-8"), date)
    k = _sign(k, region)
    k = _sign(k, "s3")
    k = _sign(k, "aws4_request")
    signature = hmac.new(k, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{canonical_query}&X-Amz-Signature={signature}"
