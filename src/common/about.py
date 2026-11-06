"""The About dialog, opened from the bottom of the sidebar: the app's version
and license, the notices the bundled third-party software asks for, and the
license texts of the programs and Python packages the app ships."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.common import third_party


def _text_viewer(text: str) -> None:
    st.code(text or "No license file found.", language=None, wrap_lines=True, height=320)


def _component_table(components, key: str, columns: list[str]) -> None:
    rows = [
        {
            "Name": c.name,
            "Version": c.version,
            "License": c.license or ("see license text" if c.files else "not stated"),
        }
        for c in components
    ]
    st.dataframe(
        pd.DataFrame(rows, columns=["Name", "Version", "License"])[columns],
        hide_index=True,
        width="stretch",
        height=min(36 * (len(rows) + 1) + 3, 280),
    )
    with_files = [c for c in components if c.files]
    if not with_files:
        return
    names = [c.name for c in with_files]
    picked = st.selectbox("Show the license text of", names, index=None, key=f"about-{key}-pick")
    if picked:
        _text_viewer(third_party.license_text(with_files[names.index(picked)]))


@st.dialog("About", width="large")
def about_dialog() -> None:
    settings = st.session_state.settings
    name = settings.get("app-name", "")
    st.markdown(f"**{name}** · version {settings.get('version', '')}")

    thermo = third_party.thermo_notice()
    if thermo:
        st.info(
            f"{name} reads Thermo .raw files with RawFileReader, which it includes under a "
            f"license from Thermo Fisher Scientific. You may not pass RawFileReader on to others.\n\n"
            f"{thermo}"
        )

    tabs = st.tabs(["License", "Third-party programs", "Python packages"])
    with tabs[0]:
        text = third_party.app_license()
        if text:
            _text_viewer(text)
        else:
            st.write(f"{name} is released under a three-clause BSD license.")
        st.caption(
            f"{name} is built with OpenMS and pyOpenMS (three-clause BSD license) and includes "
            "software from others, each under its own license, listed in the other tabs."
        )
    with tabs[1]:
        programs = third_party.third_party_programs()
        if programs:
            _component_table(programs, "programs", ["Name"])
        else:
            st.write("This installation includes no third-party programs.")
    with tabs[2]:
        _component_table(third_party.python_packages(), "packages", ["Name", "Version", "License"])


def render_about_button() -> None:
    """The button in the sidebar that opens the About dialog."""
    if st.button("About and licenses", key="about-open", type="tertiary", width="stretch"):
        about_dialog()
