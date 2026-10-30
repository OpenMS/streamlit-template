"""Download buttons for the desktop installers of the app's latest release.

The release workflows attach one installer per platform to each GitHub release
(build-windows-executable-app.yaml and build-macos-linux-app.yaml). Their names
end in a fixed suffix, so they are found whatever the app and version are
called. The buttons link to the release assets instead of serving files from
the image, so a deployment does not carry several hundred MB of installers.
"""

from pathlib import Path

import requests
import streamlit as st

# (key, button label, name suffix of the release asset, help text)
PLATFORMS = [
    ("windows", "Windows", "-Setup.exe", "Installer for Windows 10 and 11 (64-bit); no admin rights needed."),
    ("macos", "macOS", "-macOS-arm64.dmg", "Disk image for Macs with Apple Silicon (M1 and later)."),
    ("linux", "Linux", "-Linux-x86_64.AppImage", "AppImage for x86_64 Linux with glibc 2.35 or newer; runs without installation."),
]
# Offered as a link below the buttons.
LINUX_DEB_SUFFIX = "-Linux-amd64.deb"

# Copied into the image by the Dockerfile of older deployments; still offered
# for Windows when the release cannot be read.
LOCAL_WINDOWS_INSTALLER = Path("OpenMS-App-Setup.exe")


@st.cache_data(ttl=3600, show_spinner=False)
def latest_release_assets(github_user: str, repository: str) -> dict:
    """Name -> download URL of every asset of the latest release, or {} on failure."""
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


def find_installers() -> dict:
    """Platform key -> download URL of its installer in the latest release."""
    settings = st.session_state.get("settings", {})
    user, repo = settings.get("github-user"), settings.get("repository-name")
    assets = latest_release_assets(user, repo) if user and repo else {}
    found = {}
    for key, _, suffix, _ in PLATFORMS:
        url = next((u for n, u in assets.items() if n.endswith(suffix)), None)
        if url:
            found[key] = url
    deb = next((u for n, u in assets.items() if n.endswith(LINUX_DEB_SUFFIX)), None)
    if deb:
        found["linux-deb"] = deb
    if assets.get("_release_page"):
        found["release"] = assets["_release_page"]
    return found


def _available():
    """Platforms with an installer to offer, the release's URLs, and the
    bundled Windows installer used when the release has none."""
    if st.session_state.get("location") != "online":
        return [], {}, None
    installers = find_installers()
    windows_file = None
    if "windows" not in installers and LOCAL_WINDOWS_INSTALLER.exists():
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

    notes = []
    if "linux-deb" in installers:
        notes.append(f"Debian/Ubuntu package: [.deb]({installers['linux-deb']})")
    if "release" in installers:
        notes.append(f"[All downloads and release notes]({installers['release']})")
    if notes:
        st.caption(" · ".join(notes))
    return True
