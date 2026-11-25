"""Download buttons for the desktop installers of the app's latest release.

The desktop app workflow (build-desktop-app.yaml) attaches one installer per
platform to each GitHub release, and the installers of the OpenMS command line
tools it was built with. Their names
end in a fixed suffix, so they are found whatever the app and version are
called. The buttons link to the release assets instead of serving files from
the image, so a deployment does not carry several hundred MB of installers.
"""

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


def render_tool_installer_buttons(heading: str = "", text: str = "") -> bool:
    """One download button per platform whose OpenMS command line tools are
    attached to the latest release, below `heading` and `text` (markdown);
    renders nothing and returns False when the release has none.

    Only shown in online deployments, like render_installer_buttons().
    """
    if st.session_state.get("location") != "online":
        return False
    found = find_tool_installers()
    available = [p for p in TOOL_PLATFORMS if p[0] in found]
    if not available:
        return False
    if heading:
        st.markdown(heading)
    if text:
        st.markdown(text)
    cols = st.columns(len(available))
    for col, (key, label, _, help_text) in zip(cols, available):
        with col:
            st.link_button(
                f"🧰 {label}",
                found[key],
                help=help_text,
                type="secondary",
                use_container_width=True,
            )
    return True
