"""The four steps of an OpenMS workflow and the furniture of their pages.

Every workflow reads as one path, in the menu and on its pages:

    Describe experiment -> Run analysis -> Explore results -> Export results

(*Download results* online, where the files go to the user's computer.)
Describe experiment also takes the files (the Browse dialog of
``select_input_file``), so there is no upload page.

Each page opens with ``page_intro`` (what the page is for and, folded away,
the background a newcomer needs) and ends with ``next_steps`` (where to go
from here, each with a reason). A workflow names its pages as the class
attributes ``configure_page``, ``run_page``, ``results_page`` and
``export_page`` of its ``WorkflowManager``; ``step_page`` builds the menu
entry of each step from the same titles and icons.
"""

from pathlib import Path
from typing import Optional

import streamlit as st
from streamlit.errors import StreamlitAPIException

DESCRIBE, RUN, EXPLORE, EXPORT = "describe", "run", "explore", "export"
ORDER = (DESCRIBE, RUN, EXPLORE, EXPORT)

# The workflow class attribute that names each step's page
PAGE_ATTRIBUTES = {
    DESCRIBE: "configure_page",
    RUN: "run_page",
    EXPLORE: "results_page",
    EXPORT: "export_page",
}

_STEPS = {
    DESCRIBE: ("Describe experiment", "⚙️"),
    RUN: ("Run analysis", "🚀"),
    EXPLORE: ("Explore results", "👀"),
    EXPORT: ("Export results", "📤"),
}


def _online() -> bool:
    location = st.session_state.get("location")
    if location is not None:
        return location == "online"
    settings = st.session_state.get("settings") or {}
    return bool(settings.get("online_deployment"))


def step_title(step: str) -> str:
    """The step's name, as the menu and the pages say it."""
    if step == EXPORT and _online():
        return "Download results"
    return _STEPS[step][0]


def step_icon(step: str) -> str:
    if step == EXPORT and _online():
        return "⬇️"
    return _STEPS[step][1]


def step_page(path, step: str, **kwargs) -> "st.Page":
    """The menu entry of a step's page, with its title and icon."""
    return st.Page(Path(path), title=step_title(step), icon=step_icon(step), **kwargs)


def workflow_pages(workflow_class) -> dict:
    """{step: page path} of a workflow class, for the steps it has pages for."""
    pages = {}
    for step in ORDER:
        path = getattr(workflow_class, PAGE_ATTRIBUTES[step], None)
        if path:
            pages[step] = str(path)
    return pages


def page_link(path, label: str, icon: Optional[str] = None) -> None:
    """A link to another page; plain text where the page has no navigation."""
    try:
        st.page_link(str(path), label=label, icon=icon)
    except (KeyError, StreamlitAPIException):
        # A page loaded on its own (AppTest.from_file) has no navigation to link into
        st.markdown(f"{icon or ''} {label}".strip())


def step_link(workflow, step: str, label: Optional[str] = None) -> None:
    """A link to one step of ``workflow`` (an instance or its class)."""
    path = workflow_pages(type(workflow) if not isinstance(workflow, type) else workflow).get(step)
    if path:
        page_link(path, label or step_title(step), step_icon(step))


def page_intro(lead: str, background: Optional[str] = None,
               background_title: str = "Background") -> None:
    """The page's purpose in plain words, with background folded away."""
    st.markdown(lead)
    if background:
        with st.expander(f"📖 {background_title}"):
            st.markdown(background)


def next_steps(workflow, *steps) -> None:
    """A footer linking to the steps that usually come next, each with a reason.

    ``steps`` are ``(step, why)`` pairs, a step one of ``describe``, ``run``,
    ``explore`` and ``export``, or ``(path, label, icon, why)`` for a page
    outside the workflow.
    """
    st.markdown("---")
    st.markdown("**Where to go next**")
    for entry in steps:
        cols = st.columns([2, 5])
        with cols[0]:
            if len(entry) == 2:
                step_link(workflow, entry[0])
            else:
                page_link(entry[0], entry[1], entry[2])
        cols[1].markdown(entry[-1])


# The groups of an Explore results page's components, in the order an
# analysis runs; the component palette of Customize views lists them so.
# Quality control and functional analysis go with the data they are about.
# The visualization library (src/viz/) is laid out in the same folders.
MS_DATA = "MS data"
FEATURES = "Features and masses"
IDENTIFICATION = "Identification"
QUANTIFICATION = "Quantification"
COMPONENT_GROUPS = (MS_DATA, FEATURES, IDENTIFICATION, QUANTIFICATION)
