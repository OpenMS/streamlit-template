"""
Developer mode: features that are switched on in settings.json but shown only
to developers until they are ready for everyone.

It is unlocked with a password entered under ⚙️ Settings in the sidebar. Online
it stays on for that browser session only. In the local (desktop) app it stays
on after restarts until Lock is pressed: unlocking writes ``.developer-mode``
into the local workspaces folder, holding the hash it was unlocked against, so
a new password locks it again.

settings.json holds only a salted scrypt hash of the password
(``developer_mode.password_hash``), so the repository and the desktop installers
never contain the password and a copy of the file cannot be checked against a
list of common passwords at sha256 speed. A deployment sets its own with the
environment variable ``DEVELOPER_PASSWORD_HASH``, which wins over settings.json;
``none`` there turns developer mode off. No hash, no developer mode. Make a
hash with

    python -m src.common.developer

An unsalted sha256 (``password_sha256`` / ``DEVELOPER_PASSWORD_SHA256``) is
still accepted, so existing deployments keep working until they move over.
"""

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path

import streamlit as st

_KEY = "developer-mode"
_MARKER = ".developer-mode"


# scrypt cost: 2**15 * 8 * 128 bytes = 32 MiB and roughly 50 ms per check.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str, salt: bytes | None = None) -> str:
    """A salted scrypt hash: ``scrypt$<n>$<r>$<p>$<salt>$<key>`` (base64)."""
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                         p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(key)}"


def _normalized(stored: str) -> str:
    """A legacy sha256 is compared case-insensitively, a scrypt hash as is."""
    stored = stored.strip()
    return stored if stored.startswith("scrypt$") else stored.lower()


def _matches(password: str, stored: str) -> bool:
    stored = _normalized(stored)
    if not stored.startswith("scrypt$"):
        given = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(given, stored)
    try:
        _, n, r, p, salt, key = stored.split("$")
        expected = base64.b64decode(key, validate=True)
        given = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt, validate=True),
                               n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM,
                               dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(given, expected)


def _password_hash() -> str:
    for var in ("DEVELOPER_PASSWORD_HASH", "DEVELOPER_PASSWORD_SHA256"):
        env = os.environ.get(var, "").strip()
        if env:
            return "" if env.lower() == "none" else env
    config = st.session_state.settings.get("developer_mode") or {}
    return config.get("password_hash") or config.get("password_sha256", "")


def _marker_path() -> Path | None:
    """Where the local app remembers an unlock; None online."""
    settings = st.session_state.get("settings") or {}
    if settings.get("online_deployment", True):
        return None
    from src.common.common import local_workspaces_dir  # common imports this module

    return local_workspaces_dir(settings) / _MARKER


def _remembered() -> bool:
    """True when the local app was unlocked against the current password."""
    path, expected = _marker_path(), _password_hash()
    if path is None or not expected:
        return False
    try:
        stored = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return hmac.compare_digest(stored, _normalized(expected))


def _remember(unlocked: bool) -> None:
    path = _marker_path()
    if path is None:
        return
    try:
        if unlocked:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_normalized(_password_hash()), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass  # a read-only folder: developer mode lasts for this session only


def is_developer() -> bool:
    """True once developer mode is unlocked: in this session, or (local app)
    in an earlier one that was not locked again."""
    if _KEY not in st.session_state:
        st.session_state[_KEY] = _remembered()
    return bool(st.session_state[_KEY])


def verify_password(password: str) -> bool:
    expected = _password_hash()
    if not expected or not password:
        return False
    return _matches(password, expected)


def _unlock() -> None:
    entered = st.session_state.pop("developer-mode-password", "")
    st.session_state[_KEY] = verify_password(entered)
    st.session_state["developer-mode-failed"] = not st.session_state[_KEY]
    if st.session_state[_KEY]:
        _remember(True)


def render_developer_toggle() -> None:
    """Password field to unlock developer mode, or its state and Lock."""
    if not _password_hash():
        return
    st.markdown("## Developer mode")
    if is_developer():
        if _marker_path() is None:
            st.caption("🛠️ On for this session: developer features are shown.")
        else:
            st.caption("🛠️ On: developer features are shown, also after a restart, until you lock it.")
        if st.button("Lock developer mode", key="developer-mode-lock"):
            st.session_state[_KEY] = False
            _remember(False)
            st.rerun()
        return
    st.text_input("Developer password", type="password", key="developer-mode-password",
                  on_change=_unlock,
                  help="Shows features that are still in development.")
    if st.session_state.get("developer-mode-failed"):
        st.caption("Wrong password.")


if __name__ == "__main__":
    import getpass

    first = getpass.getpass("Developer password: ")
    if not first or first != getpass.getpass("Repeat: "):
        raise SystemExit("The passwords differ or are empty.")
    print(hash_password(first))
