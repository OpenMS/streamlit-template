"""The building blocks of a workflow's **Describe experiment** page.

Every OpenMS workflow describes an experiment the same way:

1. **Your analysis**, a bordered box at the top (``analysis_box``): the input
   files (``select_input_file(..., upload=...)``, whose Browse dialog also
   takes new files, so there is no upload page), then *what to do* with them
   as choices stored with the settings (``choice``), then the settings that
   depend on the sample or the instrument as ready-made presets read back
   from the settings (``preset_choice``), a recommendation drawn from the
   data with a button that applies it (``recommendation``), and last, in one
   paragraph, what a start will do (``analysis_summary``).
2. **The steps**, one numbered tab per step the chosen analysis runs, in the
   order they run (``step_tabs``). A step the analysis does not run has no
   tab, so a choice in the box adds or removes tabs.
3. **The Run bar** at the bottom (``WorkflowManager.show_run_button``), with
   the same summary sentence beside the button.

Things that are not part of describing this experiment (importing a public
dataset, for example) go below the box, not inside it.

``StreamlitUI`` inherits these methods, so a workflow calls them as
``self.ui.choice(...)``.
"""

from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterable, List, Optional

import streamlit as st


SUMMARY_ICON = "🧭"


def numbered(steps: Iterable[str]) -> List[str]:
    """Tab labels ``**1 · Step**`` for the steps, in order."""
    return [f"**{i} · {step}**" for i, step in enumerate(steps, start=1)]


class DescribeMixin:
    """The Describe experiment widgets of ``StreamlitUI``."""

    # --- the box ---

    @contextmanager
    def analysis_box(self, title: str = "Your analysis"):
        """The bordered **Your analysis** box, after the note on whose settings these are."""
        self.follow_up_notice()
        with st.container(border=True):
            st.markdown(f"##### {title}")
            yield

    def current_params(self) -> Dict[str, Any]:
        """The workflow's parameters with the values the widgets hold in this rerun.

        ``self.params`` is read when the page starts, so it is stale for a
        widget changed in this rerun (or in a fragment).
        """
        prefix = self.parameter_manager.param_prefix
        current = dict(self.parameter_manager.get_parameters_from_json())
        current.update({k[len(prefix):]: v for k, v in st.session_state.items()
                        if isinstance(k, str) and k.startswith(prefix)})
        return current

    def choice(
        self,
        key: str,
        options: List[Any],
        labels: Optional[Dict[Any, str]] = None,
        default: Any = None,
        label: str = "",
        help: Optional[str] = None,
        selectbox: bool = False,
        option_help: Optional[Dict[Any, str]] = None,
    ) -> Any:
        """One of ``options``, stored as the workflow parameter ``key``.

        A segmented control (a selectbox with ``selectbox=True``, for long
        lists) that always holds a choice: clicking the picked option keeps
        it. ``option_help`` is joined into the help text, one sentence per
        option. Drawn in the page, not in a fragment, so a change reruns the
        page and the step tabs follow it.
        """
        labels = labels or {o: str(o) for o in options}
        default = options[0] if default is None else default
        if option_help:
            extra = " ".join(f"**{labels[o]}**: {h}" for o, h in option_help.items() if o in labels)
            help = f"{help} {extra}" if help else extra
        widget = f"{self.parameter_manager.param_prefix}{key}"
        if st.session_state.get(widget) not in options:
            stored = self.parameter_manager.get_parameters_from_json().get(key, default)
            st.session_state[widget] = stored if stored in options else default
        if selectbox:
            st.selectbox(label, options, format_func=lambda o: labels[o], key=widget, help=help)
        else:
            st.segmented_control(
                label, options, format_func=lambda o: labels[o], key=widget, help=help,
                on_change=_keep_choice, args=(widget,),
            )
        st.session_state[_last_key(widget)] = st.session_state[widget]
        self.parameter_manager.save_parameters()
        return st.session_state[widget]

    def preset_choice(
        self,
        key: str,
        label: str,
        options: List[str],
        current: Optional[str],
        labels: Optional[Dict[str, str]] = None,
        help: Optional[str] = None,
        on_pick: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Ready-made settings (presets) as one segmented control.

        It shows ``current``, the preset whose values the settings hold (None
        when they are the user's own), so it is read back from the settings
        and never stored itself. Picking another applies it: the preset of
        that name in presets.json, or ``on_pick(name)``.
        """
        labels = labels or {o: o for o in options}
        st.session_state[key] = current

        def picked():
            chosen = st.session_state.get(key)
            if chosen and chosen != current:
                (on_pick or self._apply_preset_callback)(chosen)

        st.segmented_control(label, options, format_func=lambda o: labels[o], key=key,
                             help=help, on_change=picked)

    def recommendation(
        self,
        text: str,
        recommended: Optional[str],
        current: Optional[str],
        button: str,
        key: str,
        on_click: Optional[Callable[..., None]] = None,
        args: tuple = (),
    ) -> None:
        """What the data suggests, and a button that applies it.

        With ``current == recommended`` a green note says the settings fit;
        otherwise the note sits beside ``button``, which runs ``on_click(*args)``
        (by default the preset ``recommended``). Without a recommendation
        (``recommended`` None) ``text`` is a warning.
        """
        if recommended is None:
            if text:
                st.warning(text, icon="⚠️")
            return
        if current == recommended:
            st.success(text, icon="✅")
            return
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.info(text, icon="💡")
        if on_click is None:
            on_click, args = self._apply_preset_callback, (recommended,)
        c2.button(button, key=key, on_click=on_click, args=args, use_container_width=True)

    @staticmethod
    def analysis_summary(text: str) -> None:
        """What a start will do, in one paragraph, at the end of the box."""
        st.info(text, icon=SUMMARY_ICON)

    # --- the steps ---

    @staticmethod
    def step_tabs(steps: List[str]) -> Dict[str, Any]:
        """One numbered tab per step, in order; returns {step: tab}."""
        steps = list(steps)
        if not steps:
            return {}
        return dict(zip(steps, st.tabs(numbered(steps))))


def _last_key(widget: str) -> str:
    return f"_{widget}__last"


def _keep_choice(widget: str) -> None:
    # A click on the picked option clears a segmented control: keep that option
    if st.session_state.get(widget) is None:
        st.session_state[widget] = st.session_state.get(_last_key(widget))
