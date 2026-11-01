"""
Developer mode: features that are switched on in settings.json but shown only
to developers until they are ready for everyone.

It is unlocked per browser session with a password entered under ⚙️ Settings in
the sidebar. settings.json holds only the password's sha256
(``developer_mode.password_sha256``), so the repository and the desktop
installers never contain it. A deployment sets its own with the environment
variable ``DEVELOPER_PASSWORD_SHA256``, which wins over settings.json; ``none``
there turns developer mode off. No hash, no developer mode.

    python -c "import hashlib, getpass; print(hashlib.sha256(getpass.getpass().encode()).hexdigest())"
"""

import hashlib
import hmac
import os

import streamlit as st

_KEY = "developer-mode"


def _password_hash() -> str:
    env = os.environ.get("DEVELOPER_PASSWORD_SHA256", "").strip()
    if env:
        return "" if env.lower() == "none" else env
    return (st.session_state.settings.get("developer_mode") or {}).get("password_sha256", "")


def is_developer() -> bool:
    """True once this session has unlocked developer mode."""
    return bool(st.session_state.get(_KEY))


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


def render_developer_toggle() -> None:
    """Password field to unlock developer mode, or its state and Lock."""
    if not _password_hash():
        return
    st.markdown("## Developer mode")
    if is_developer():
        st.caption("🛠️ On for this session: developer features are shown.")
        if st.button("Lock developer mode", key="developer-mode-lock"):
            st.session_state[_KEY] = False
            st.rerun()
        return
    st.text_input("Developer password", type="password", key="developer-mode-password",
                  on_change=_unlock,
                  help="Shows features that are still in development.")
    if st.session_state.get("developer-mode-failed"):
        st.caption("Wrong password.")
