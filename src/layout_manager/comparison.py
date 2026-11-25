"""Edit comparison: the steps that turn the runs of an experiment into a comparison, in a dialog.

A comparison of runs (or samples) is made in steps an app names: which
samples belong to which group, how features are filtered, how missing values
are filled in, how abundances are normalized, which test is used. The dialog
shows one tab per step, **Start over with the recommended settings** and
**Done**::

    edit_comparison(
        "viewer_0",
        [("1. Groups", draw_groups), ("2. Filter", draw_filter), ("3. Test", draw_test)],
        on_reset=forget_settings, on_done=apply_settings,
    )

Each ``draw`` function draws the widgets of its step. A step may apply its
widgets at once (the components behind the dialog follow) or leave them to
``on_done``, which runs when **Done** is pressed and returns False to keep the
dialog open (an error it has shown). The dialog stays open over reruns of the
page it did not ask for (components behind it can rerun the page right after
a click) until it is closed or **Done** is pressed. ``open_comparison(key)``
opens it from elsewhere, a view bar action for instance, when
``edit_comparison(..., button=False)`` draws only the dialog.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence, Tuple

import streamlit as st

Step = Tuple[str, Callable[[], Any]]


def _open_key(key: str) -> str:
    return f"{key}_comparison_open"


def open_comparison(key: str) -> None:
    """Open the Edit comparison dialog drawn by ``edit_comparison(key, ...)``."""
    st.session_state[_open_key(key)] = True


def close_comparison(key: str) -> None:
    """Close it (as **Done** does)."""
    st.session_state[_open_key(key)] = False


def comparison_open(key: str) -> bool:
    return bool(st.session_state.get(_open_key(key)))


def edit_comparison(
    key: str,
    steps: Sequence[Step],
    *,
    title: str = "Edit comparison",
    intro: Optional[str] = None,
    on_reset: Optional[Callable[[], Any]] = None,
    reset_label: str = "Start over with the recommended settings",
    reset_help: str = "Discard the steps changed here and compare again with the defaults.",
    on_done: Optional[Callable[[], Any]] = None,
    done_label: str = "Done",
    button: bool = True,
    button_label: str = "Edit comparison",
    button_help: Optional[str] = None,
) -> None:
    """The **Edit comparison** button and its dialog of ``steps`` (label, draw function)."""
    open_key = _open_key(key)

    def _closed() -> None:
        st.session_state[open_key] = False

    @st.dialog(title, width="large", on_dismiss=_closed)
    def _dialog() -> None:
        if intro:
            st.caption(intro)
        if len(steps) == 1:
            steps[0][1]()
        else:
            for tab, (_, draw) in zip(st.tabs([label for label, _ in steps]), steps):
                with tab:
                    draw()
        left, right = st.columns(2)
        if on_reset is not None and left.button(reset_label, key=f"{key}_comparison_reset", help=reset_help):
            on_reset()
            st.rerun()
        if right.button(done_label, type="primary", key=f"{key}_comparison_done"):
            if on_done is None or on_done() is not False:
                _closed()
                st.rerun()

    if button and st.button(button_label, key=f"{key}_comparison_button", icon=":material/tune:",
                            help=button_help, width="content"):
        st.session_state[open_key] = True
    if st.session_state.get(open_key):
        _dialog()
