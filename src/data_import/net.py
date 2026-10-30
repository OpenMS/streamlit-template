"""HTTP sessions for importing data from links.

On a public server the import makes the server fetch a URL a stranger typed,
so the guarded session refuses any address that is not on the public
internet: loopback, private networks, link-local (cloud metadata services),
carrier-grade NAT, multicast and their IPv6 counterparts. It checks twice:
the host name's addresses before each request (and each redirect), and the
address the socket actually connected to, so DNS rebinding between the two
cannot slip a private address through. The local (desktop) app uses an
unguarded session, since users may import from their own network.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

USER_AGENT = "OpenMS-WebApp-DataImport/1.0"
MAX_REDIRECTS = 5


class BlockedURL(ValueError):
    """The URL points somewhere the import may not go."""


def is_public_address(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%", 1)[0])
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def _host_allowed(host: str, allowed_hosts) -> bool:
    host = host.lower().rstrip(".")
    for allowed in allowed_hosts:
        allowed = allowed.lower().strip().lstrip(".")
        if allowed and (host == allowed or host.endswith("." + allowed)):
            return True
    return False


def check_url(url: str, allowed_hosts=None, resolve: bool = True) -> None:
    """Raise BlockedURL unless ``url`` is http(s) to a public address."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BlockedURL(f"Only http and https links can be imported, not '{parts.scheme or url}'.")
    host = parts.hostname
    if not host:
        raise BlockedURL("The link has no host name.")
    if allowed_hosts and not _host_allowed(host, allowed_hosts):
        raise BlockedURL(f"This server only imports from: {', '.join(allowed_hosts)}.")
    if not resolve:
        return
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise BlockedURL(f"Could not resolve '{host}': {e}") from e
    for info in infos:
        if not is_public_address(info[4][0]):
            raise BlockedURL(f"'{host}' is not a public internet address.")


def _check_peer(conn, sock) -> None:
    # Behind a proxy the socket connects to the proxy, which may well be on a
    # private network; the host name check in send() covers that case.
    if getattr(conn, "_tunnel_host", None) or getattr(conn, "proxy", None):
        return
    try:
        peer = sock.getpeername()[0]
    except OSError:
        return
    if not is_public_address(peer):
        sock.close()
        raise BlockedURL(f"'{conn.host}' connected to {peer}, which is not a public internet address.")


class _GuardedHTTPConnection(HTTPConnection):
    def _new_conn(self):
        sock = super()._new_conn()
        _check_peer(self, sock)
        return sock


class _GuardedHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        sock = super()._new_conn()
        _check_peer(self, sock)
        return sock


class _GuardedHTTPPool(HTTPConnectionPool):
    ConnectionCls = _GuardedHTTPConnection


class _GuardedHTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _GuardedHTTPSConnection


_GUARDED_POOLS = {"http": _GuardedHTTPPool, "https": _GuardedHTTPSPool}


class GuardedAdapter(HTTPAdapter):
    """Checks every request, redirects included, and every new connection."""

    def __init__(self, allowed_hosts=None, **kwargs):
        self.allowed_hosts = list(allowed_hosts or [])
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = _GUARDED_POOLS

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        manager = super().proxy_manager_for(proxy, **proxy_kwargs)
        manager.pool_classes_by_scheme = _GUARDED_POOLS
        return manager

    def send(self, request, **kwargs):
        check_url(request.url, self.allowed_hosts)
        return super().send(request, **kwargs)


def make_session(guard: bool, allowed_hosts=None) -> requests.Session:
    """A session for one import; ``guard`` on public servers."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.max_redirects = MAX_REDIRECTS
    if guard or allowed_hosts:
        adapter = GuardedAdapter(allowed_hosts) if guard else _HostListAdapter(allowed_hosts)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
    return session


class _HostListAdapter(HTTPAdapter):
    """Applies only the host allow-list (local apps with one configured)."""

    def __init__(self, allowed_hosts, **kwargs):
        self.allowed_hosts = list(allowed_hosts or [])
        super().__init__(**kwargs)

    def send(self, request, **kwargs):
        check_url(request.url, self.allowed_hosts, resolve=False)
        return super().send(request, **kwargs)


def redact(url: str) -> str:
    """The URL without query string or credentials, for logs and status files.

    Presigned links carry their signature in the query string.
    """
    parts = urlsplit(url)
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
