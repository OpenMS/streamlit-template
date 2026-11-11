"""Password for the app's Redis.

Kubernetes passes it as ``REDIS_PASSWORD`` from the Secret ``redis-auth``
(``k8s/base/redis-auth-secret.yaml``); empty or unset, Redis runs without one,
as before. ``REDIS_URL`` itself stays without credentials, so it can be logged
and patched by overlays as it is. Streamlit-free, imported by the RQ worker.
"""

import os
from urllib.parse import quote, urlsplit, urlunsplit


def redis_url_with_password(url: str) -> str:
    """``url`` with the password from ``REDIS_PASSWORD`` added, for a
    ``redis://`` or ``rediss://`` URL that names none itself."""
    password = os.environ.get("REDIS_PASSWORD", "")
    parts = urlsplit(url)
    if not password or parts.scheme not in ("redis", "rediss") or "@" in parts.netloc:
        return url
    netloc = f":{quote(password, safe='')}@{parts.netloc}"
    return urlunsplit(parts._replace(netloc=netloc))
