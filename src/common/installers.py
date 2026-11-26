"""Download buttons for the desktop installers of the app's latest release.

The desktop app workflow (build-desktop-app.yaml) attaches one installer per
platform to each GitHub release, and the installers of the OpenMS command line
tools it was built with. Their names
end in a fixed suffix, so they are found whatever the app and version are
called. The buttons link to the release assets instead of serving files from
the image, so a deployment does not carry several hundred MB of installers.
"""

from html import escape
import threading
import time
from pathlib import Path

import requests
import streamlit as st

# (key, button label, name suffix of the release asset, help text)
PLATFORMS = [
    ("windows", "Windows", "-Setup.exe", "Installer for Windows 10 and 11 (64-bit); no admin rights needed."),
    ("macos", "macOS", "-macOS-arm64.dmg", "Disk image for Macs with Apple Silicon (M1 and later)."),
    ("linux", "Linux", "-Linux-x86_64.AppImage", "AppImage for x86_64 Linux with glibc 2.35 or newer; runs without installation."),
]

# The OpenMS command line tools the desktop app was built with, packaged by
# the same workflow (electron/scripts/package-tools.sh) for users who run them
# from a terminal or a script. Their names never end in a suffix above.
TOOL_PLATFORMS = [
    ("windows", "Windows", "-command-line-tools-Windows-x86_64.exe", "Installer for Windows 10 and 11 (64-bit); no admin rights needed, puts the tools on your PATH."),
    ("macos", "macOS", "-command-line-tools-macOS-arm64.pkg", "Package for Macs with Apple Silicon; installs to /Applications/OpenMS-<version>."),
    ("linux", "Linux", "-command-line-tools-Linux-x86_64.deb", "Debian package for x86_64 Ubuntu; install it with sudo apt install ./<file>."),
]

# Copied into the image by the Dockerfile of older deployments; still offered
# for Windows when the release cannot be read.
LOCAL_WINDOWS_INSTALLER = Path("OpenMS-App-Setup.exe")


# Five minutes: short enough that installers uploaded after the release was
# published (or a failed lookup) show up soon, long enough to stay far below
# GitHub's limit of 60 unauthenticated requests per hour. Kept in this module
# rather than in st.cache_data, which page_setup() clears for every new session.
RELEASE_CACHE_SECONDS = 300
_release_cache = {}
_release_cache_lock = threading.Lock()


def latest_release_assets(github_user: str, repository: str) -> dict:
    """Name -> download URL of every asset of the latest release, or {} on failure."""
    key = (github_user, repository)
    with _release_cache_lock:
        hit = _release_cache.get(key)
        if hit and time.monotonic() - hit[0] < RELEASE_CACHE_SECONDS:
            return hit[1]
        assets = _fetch_release_assets(github_user, repository)
        _release_cache[key] = (time.monotonic(), assets)
        return assets


def _fetch_release_assets(github_user: str, repository: str) -> dict:
    try:
        r = requests.get(
            f"https://api.github.com/repos/{github_user}/{repository}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
            timeout=5,
        )
        r.raise_for_status()
        release = r.json()
    except (requests.RequestException, ValueError):
        return {}
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    assets["_release_page"] = release.get("html_url", "")
    return assets


def _release_assets() -> dict:
    settings = st.session_state.get("settings", {})
    user, repo = settings.get("github-user"), settings.get("repository-name")
    return latest_release_assets(user, repo) if user and repo else {}


def _match(assets: dict, platforms: list) -> dict:
    found = {}
    for key, _, suffix, _ in platforms:
        url = next((u for n, u in assets.items() if n.endswith(suffix)), None)
        if url:
            found[key] = url
    if assets.get("_release_page"):
        found["release"] = assets["_release_page"]
    return found


def find_installers() -> dict:
    """Platform key -> download URL of its installer in the latest release."""
    return _match(_release_assets(), PLATFORMS)


def find_tool_installers() -> dict:
    """Platform key -> download URL of the command line tools in the latest
    release, plus "release" (the release page) when it could be read; no
    platform key when the release has none (e.g. one made before they were
    built)."""
    return _match(_release_assets(), TOOL_PLATFORMS)


def _available():
    """Platforms with an installer to offer, the release's URLs, and the
    bundled Windows installer used when the release has none."""
    if st.session_state.get("location") != "online":
        return [], {}, None
    installers = find_installers()
    windows_file = None
    # The bundled copy may be older than the release; offer it only when the
    # release could not be read ("release" is set whenever the lookup worked).
    if "release" not in installers and LOCAL_WINDOWS_INSTALLER.exists():
        windows_file = LOCAL_WINDOWS_INSTALLER
    available = [p for p in PLATFORMS if p[0] in installers or (p[0] == "windows" and windows_file)]
    return available, installers, windows_file


def installers_available() -> bool:
    """Whether render_installer_buttons() would show any button."""
    return bool(_available()[0])


def render_installer_buttons(heading: str = "", app_name: str = "") -> bool:
    """One download button per platform that has an installer, below `heading`
    (markdown); renders nothing and returns False if no platform has one.

    Only shown in online deployments: the desktop app does not offer to
    download itself.
    """
    available, installers, windows_file = _available()
    if not available:
        return False

    name = app_name or st.session_state.get("settings", {}).get("app-name", "OpenMS-App")
    if heading:
        st.markdown(heading)
    cols = st.columns(len(available))
    for col, (key, label, _, help_text) in zip(cols, available):
        with col:
            if key in installers:
                st.link_button(
                    f"📥 {label}",
                    installers[key],
                    help=help_text,
                    type="secondary",
                    use_container_width=True,
                )
            else:
                with open(windows_file, "rb") as f:
                    st.download_button(
                        label=f"📥 {label}",
                        data=f,
                        file_name=f"{name}-Setup.exe",
                        mime="application/vnd.microsoft.portable-executable",
                        help=help_text,
                        type="secondary",
                        use_container_width=True,
                    )

    if "release" in installers:
        st.caption(f"[All downloads and release notes]({installers['release']})")
    return True


def render_tool_installer_line(
    lead: str = "Prefer scripting? Get the OpenMS command line tools the desktop app runs for",
) -> bool:
    """A small line below the desktop installers linking the OpenMS command
    line tools of the latest release, one link per platform ("<lead> Windows
    · macOS · Linux."); renders nothing and returns False when the release
    has none.

    Only shown in online deployments, like render_installer_buttons().
    """
    if st.session_state.get("location") != "online":
        return False
    found = find_tool_installers()
    links = [
        f'<a href="{escape(found[key])}" title="{escape(help_text)}">{escape(label)}</a>'
        for key, label, _, help_text in TOOL_PLATFORMS
        if key in found
    ]
    if not links:
        return False
    st.markdown(
        '<div style="opacity: 0.75; font-size: 0.9rem; margin-top: 0.25rem;">'
        f"{escape(lead)} {' · '.join(links)}.</div>",
        unsafe_allow_html=True,
    )
    return True


def _accent() -> tuple[str, str]:
    """The theme's primary colour for the active light or dark theme, and a
    text colour that reads on it."""
    try:
        dark = st.context.theme.type == "dark"
    except Exception:
        dark = False
    try:
        colour = st.get_option(f"theme.{'dark' if dark else 'light'}.primaryColor")
    except Exception:
        colour = None
    colour = colour or st.get_option("theme.primaryColor") or ("#7891f1" if dark else "#1436b8")
    # The dark theme's primary colour is light: white on it is hard to read.
    return colour, ("#0e1117" if dark else "#ffffff")


def render_download_box(
    title: str = "",
    text: str = "Run the app on your own computer: the same analysis and results, "
    "on files that stay on your disk, with no upload.",
    key: str = "openms_downloads",
) -> bool:
    """A framed download box: a title, one line on what the desktop app is,
    a button per platform (render_installer_buttons()) and the line of the
    command line tools (render_tool_installer_line()), in the theme's
    primary colour. Renders nothing and returns False when there is nothing
    to download (offline, or a release without installers).
    """
    if not installers_available():
        return False
    name = st.session_state.get("settings", {}).get("app-name", "the app")
    title = title or f"⬇️ Download {name}"
    accent, on_accent = _accent()
    with st.container(key=key):
        st.markdown(
            f'<div class="openms-downloads-title">{escape(title)}</div>'
            f'<div class="openms-downloads-text">{escape(text)}</div>',
            unsafe_allow_html=True,
        )
        render_installer_buttons()
        render_tool_installer_line()
    buttons = (
        f'.st-key-{key} [data-testid^="stBaseLinkButton"], '
        f'.st-key-{key} [data-testid^="stBaseButton"]'
    )
    labels = (
        f'.st-key-{key} [data-testid^="stBaseLinkButton"] p, '
        f'.st-key-{key} [data-testid^="stBaseButton"] p'
    )
    st.markdown(
        f"""
        <style>
        .st-key-{key} {{
            border: 2px solid {accent} !important;
            border-radius: 12px !important;
            padding: 1.25rem 1.5rem !important;
            margin: 0 0 1.5rem 0 !important;
            background: linear-gradient(135deg, rgba(128, 128, 128, 0.04) 0%,
                                        rgba(128, 128, 128, 0.10) 100%) !important;
            text-align: center !important;
        }}
        .st-key-{key} [data-testid="stMarkdownContainer"],
        .st-key-{key} [data-testid="stCaptionContainer"] {{ text-align: center; }}
        .openms-downloads-title {{
            color: {accent};
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }}
        .openms-downloads-text {{ opacity: 0.85; margin-bottom: 0.75rem; }}
        {buttons} {{
            background: {accent} !important;
            border-color: {accent} !important;
            color: {on_accent} !important;
            font-weight: 600 !important;
            min-height: 3rem !important;
        }}
        {labels} {{ color: {on_accent} !important; font-size: 1.05rem !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    return True
