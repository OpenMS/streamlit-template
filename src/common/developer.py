"""
Developer mode: features that are switched on in settings.json but shown only
to developers until they are ready for everyone.

It is unlocked with a password entered under ⚙️ Settings in the sidebar. Online
it stays on for that browser session only. In the local (desktop) app it stays
on after restarts until Lock is pressed: unlocking writes ``.developer-mode``
into the local workspaces folder, holding the hash it was unlocked against, so
a new password locks it again. settings.json holds only the password's sha256
(``developer_mode.password_sha256``), so the repository and the desktop
installers never contain it. A deployment sets its own with the environment
variable ``DEVELOPER_PASSWORD_SHA256``, which wins over settings.json; ``none``
there turns developer mode off. No hash, no developer mode.

    python -c "import hashlib, getpass; print(hashlib.sha256(getpass.getpass().encode()).hexdigest())"
"""

import hashlib
import hmac
import os
from pathlib import Path

import streamlit as st

_KEY = "developer-mode"
_MARKER = ".developer-mode"


def _password_hash() -> str:
    env = os.environ.get("DEVELOPER_PASSWORD_SHA256", "").strip()
    if env:
        return "" if env.lower() == "none" else env
    return (st.session_state.settings.get("developer_mode") or {}).get("password_sha256", "")


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
    return hmac.compare_digest(stored, expected.strip().lower())


def _remember(unlocked: bool) -> None:
    path = _marker_path()
    if path is None:
        return
    try:
        if unlocked:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_password_hash().strip().lower(), encoding="utf-8")
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
    given = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(given, expected.strip().lower())


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
