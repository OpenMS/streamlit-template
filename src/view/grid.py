"""Reusable, tool-agnostic linked-grid rendering for OpenMS-Insight components.

This module is the *single source of truth* for the cross-linked component grid used
by OpenMS-ecosystem viewers (FLASHDeconv, FLASHTnT, FLASHQuant, ...). It is deliberately
free of any tool/MS-specific knowledge (it knows nothing about scans, masses, proteins,
heatmaps, or any particular dataset): everything domain-specific is supplied by the caller
through ``builders`` (a ``comp_name -> () -> BaseComponent`` map) and a ``layout`` (a nested
list of component names). Because it is tool-agnostic it can be frozen and vendored into
downstream apps byte-for-byte unchanged.

It distills two pieces of prior FLASHApp logic:

* ``render.py::render_grid`` inner loop -> :func:`render_linked_grid`. Per row it opens
  ``st.columns`` (clamped to <=3, the oracle invariant) and, per cell, constructs the
  Insight component via the registered builder and renders it against one *shared*
  ``StateManager`` so every panel cross-links. All data loading / hashing / filtering that
  the oracle did Python-side now lives inside each Insight component (``filters`` /
  ``interactivity`` + its own preprocessing), so the grid is pure layout + a shared
  StateManager.
* The two near-identical ``FLASH*LayoutManager`` page modules -> :class:`LayoutManager`,
  parameterized by the bits that differed between them (component vocabulary, storage keys,
  session namespace). The UI, JSON format, ``<=3`` column cap, ``"(... needed)"`` dependency
  validation, side-by-side option, and JSON download/upload behavior are preserved verbatim.

The data store is accessed only through the small :class:`Store` ``Protocol`` so the template
never imports any concrete FileManager from a downstream app.
"""

from __future__ import annotations

import json
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

import streamlit as st
from openms_insight import BaseComponent, StateManager

# A layout is the trimmed nested list the LayoutManager persists:
#   List[row], row = List[comp_name:str], <=3 entries per row.   (one experiment)
Layout = List[List[str]]
# `builders` maps a comp_name -> a zero-arg factory returning a *constructed* BaseComponent.
# Zero-arg so the grid can lazily build only the panels a given layout references, and so the
# factory can close over the caller's (dataset, file_manager, cache_path) context.
BuilderMap = Dict[str, Callable[[], BaseComponent]]

# Maximum number of columns per row. This is the oracle's hard cap, surfaced as a module
# constant so render_linked_grid and the default LayoutManager agree on the same value.
MAX_COLUMNS = 3


def render_linked_grid(
    layout: Layout,
    builders: BuilderMap,
    state_key: str,
    *,
    grid_key: str = "linked_grid",
    height: Optional[int] = None,
    column_heights: Optional[Dict[str, int]] = None,
    on_missing: str = "warn",  # "warn" | "error" | "skip"
) -> StateManager:
    """Render one experiment's linked grid.

    For each row in ``layout``, open ``st.columns(len(row))`` (clamped to <=3, mirroring the
    oracle's hard cap) and, in each column, call ``builders[comp_name]()`` to construct the
    Insight component, then render it with a SHARED ``StateManager(session_key=state_key)`` and a
    per-cell Streamlit key ``f"{grid_key}_{r}_{c}"``. The shared StateManager is what cross-links
    every panel in the grid: clicks (``interactivity``) write selections, other panels read them
    (``filters``). Returns the StateManager so callers can introspect/seed selections.

    Args:
        layout: trimmed nested list (rows of comp_names) for ONE experiment.
        builders: comp_name -> () -> BaseComponent  (factory; see BuilderMap).
        state_key: StateManager session_key. MUST be unique per (tool, experiment) so two
            experiments shown together do not share selections. ``StateManager`` stores its
            state under ``st.session_state[state_key]``, so distinct ``state_key`` values are
            fully independent. Baking a dataset identifier into ``state_key`` (and into each
            builder's ``cache_id``) makes switching datasets yield a fresh StateManager + fresh
            component caches automatically -- no manual reset needed here.
        grid_key: prefix for per-cell component keys.
        height: default px height passed to every comp's ``__call__`` (None -> Insight default).
        column_heights: optional comp_name -> height override (e.g. heatmaps taller).
        on_missing: behavior when a comp_name has no builder:
            ``"warn"`` (st.warning + skip, default), ``"error"`` (raise KeyError), or
            ``"skip"`` (silently skip).

    Returns:
        The shared ``StateManager`` used for this experiment's grid.
    """
    if on_missing not in ("warn", "error", "skip"):
        raise ValueError(
            f"on_missing must be 'warn', 'error' or 'skip', got {on_missing!r}"
        )

    sm = StateManager(session_key=state_key)
    heights = column_heights or {}
    for r, row in enumerate(layout):
        # <=3 columns per row, the oracle invariant. Any extra cells in a row are ignored.
        cols = st.columns(min(len(row), MAX_COLUMNS))
        for c, comp_name in enumerate(row[:MAX_COLUMNS]):
            factory = builders.get(comp_name)
            if factory is None:
                if on_missing == "error":
                    raise KeyError(
                        f"No builder registered for component '{comp_name}'"
                    )
                if on_missing == "warn":
                    cols[c].warning(f"Unknown component: {comp_name}")
                continue
            h = heights.get(comp_name, height)
            with cols[c]:
                factory()(key=f"{grid_key}_{r}_{c}", state_manager=sm, height=h)
    return sm


@runtime_checkable
class Store(Protocol):
    """Minimal results-store interface the LayoutManager persists its layout through.

    Any object implementing these four calls satisfies the protocol -- in particular the
    template/FLASHApp ``FileManager``. The template never imports a concrete FileManager;
    it only relies on this structural protocol.
    """

    def get_results(self, dataset_id: str, name_tags: list) -> dict:
        ...

    def store_data(self, dataset_id: str, name_tag: str, data) -> None:
        ...

    def result_exists(self, dataset_id: str, name_tag: str) -> bool:
        ...

    def remove_results(self, dataset_id: str) -> None:
        ...


class LayoutManager:
    """Layout-editor UI + persistence for a linked grid (distillation of both FLASH managers).

    Owns the full "Layout Manager" page: an experiment-count selector, per-experiment
    expanders with add-column(+)/add-row(+)/delete(x) controls, the ``<=max_columns`` cap, a
    side-by-side checkbox (offered only when exactly two experiments), Save/Edit/Reset buttons,
    JSON download (disabled while the layout is invalid) + JSON upload, and success/error
    toasts. It is parameterized by the things that differed between the two FLASH managers:
    the component vocabulary (``component_options``/``component_names``), the FileManager
    storage keys (``layout_id``/``layout_tag``), and the session-state namespace
    (``session_prefix``).

    The persisted JSON is the *trimmed internal-name* nested list (so old saved layouts keep
    loading), stored alongside the ``side_by_side`` flag exactly as the oracle did.
    """

    def __init__(
        self,
        component_options: List[str],  # human labels, e.g. "Scan table"
        component_names: List[str],  # parallel internal names, e.g. "scan_table"
        *,
        store: Store,  # object with get_results/store_data/result_exists/remove_results
        layout_id: str = "layout",  # store dataset_id for the saved layout
        layout_tag: str = "layout",  # store name_tag for the saved layout
        max_columns: int = MAX_COLUMNS,
        max_experiments: int = 5,
        session_prefix: str = "lm",  # namespaces all st.session_state keys
        download_name: str = "layout_settings.json",
        title: str = "Layout Manager",
    ):
        if len(component_options) != len(component_names):
            raise ValueError(
                "component_options and component_names must be the same length "
                f"({len(component_options)} != {len(component_names)})"
            )
        # Copy so add_options() does not mutate the caller's lists.
        self.component_options = list(component_options)
        self.component_names = list(component_names)
        self.store = store
        self.layout_id = layout_id
        self.layout_tag = layout_tag
        self.max_columns = max_columns
        self.max_experiments = max_experiments
        self.session_prefix = session_prefix
        self.download_name = download_name
        self.title = title

    # ------------------------------------------------------------------ #
    # session-state key helpers (namespaced by session_prefix)
    # ------------------------------------------------------------------ #
    def _k(self, name: str) -> str:
        """Build a namespaced session_state key."""
        return f"{self.session_prefix}__{name}"

    # ------------------------------------------------------------------ #
    # persistence (replaces set_layout/get_layout in both managers)
    # ------------------------------------------------------------------ #
    def get_layout(self) -> Optional[Tuple[list, bool]]:
        """Return ``(layout_per_experiment, side_by_side)`` or ``None`` if unset.

        ``layout_per_experiment``: ``List[experiment]``, experiment = ``List[row]``,
        row = ``List[comp_name]`` (trimmed internal names).
        """
        if not self.store.result_exists(self.layout_id, self.layout_tag):
            return None
        stored = self.store.get_results(self.layout_id, [self.layout_tag])[
            self.layout_tag
        ]
        return stored["layout"], stored["side_by_side"]

    def set_layout(self, layout: list, side_by_side: bool = False) -> None:
        """Persist the trimmed layout + side-by-side flag (a plain dict)."""
        self.store.store_data(
            self.layout_id,
            self.layout_tag,
            {"layout": layout, "side_by_side": side_by_side},
        )

    # ------------------------------------------------------------------ #
    # label<->name transforms (oracle getTrimmed/getExpanded)
    # ------------------------------------------------------------------ #
    def trim(self, expanded: list) -> list:
        """labels -> internal names, dropping empty cells/rows/experiments."""
        trimmed = []
        for exp in expanded:
            rows = []
            for row in exp:
                cols = []
                for col in row:
                    if col:
                        cols.append(
                            self.component_names[self.component_options.index(col)]
                        )
                if cols:
                    rows.append(cols)
            if rows:
                trimmed.append(rows)
        return trimmed

    def expand(self, trimmed: list) -> list:
        """internal names -> labels, dropping empty cells/rows/experiments."""
        expanded = []
        for exp in trimmed:
            rows = []
            for row in exp:
                cols = []
                for col in row:
                    if col:
                        cols.append(
                            self.component_options[self.component_names.index(col)]
                        )
                if cols:
                    rows.append(cols)
            if rows:
                expanded.append(rows)
        return expanded

    # ------------------------------------------------------------------ #
    # validation (oracle validateSubmittedLayout: non-empty + "(... needed)" deps)
    # ------------------------------------------------------------------ #
    def validate(self, layout: Optional[list] = None) -> str:
        """Return ``''`` if the layout is OK, else a human-readable error message.

        ``layout`` is in *label* form (the edit-mode representation). When ``None``, the
        current edit-mode session layout is validated. Checks (verbatim from the oracle):
        the layout must be non-empty, and every ``"<Component> (X needed)"`` label requires
        another component starting with ``X`` to be present in the *same* experiment.
        """
        layout_setting = (
            layout if layout is not None else st.session_state.get(self._k("layout"))
        )
        if not layout_setting:
            return "Empty input"

        # check if submitted layout is empty
        if not any(
            col for exp in layout_setting for row in exp for col in row if col
        ):
            return "Empty input"

        # check if submitted layout contains "needed" components
        for exp in layout_setting:
            submitted_components = [col for row in exp for col in row if col]
            required_components = [
                comp.split("(")[1].split("needed")[0].rstrip()
                for comp in submitted_components
                if "needed" in comp
            ]
            if required_components:
                for required in required_components:
                    required_exist = False
                    for submitted in submitted_components:
                        if submitted.startswith(required):
                            required_exist = True
                    if not required_exist:
                        return "Required component is missing"
        return ""

    # ------------------------------------------------------------------ #
    # extension hook (oracle setSequenceView)
    # ------------------------------------------------------------------ #
    def add_options(self, options: List[str], names: List[str]) -> None:
        """Append ``(label, name)`` pairs at runtime.

        Mirrors the oracle's dynamic option injection (e.g. adding "Sequence view" once an
        input sequence exists). Idempotent: pairs whose internal name is already known are
        skipped, so repeated calls across reruns do not duplicate options.
        """
        if len(options) != len(names):
            raise ValueError(
                "options and names must be the same length "
                f"({len(options)} != {len(names)})"
            )
        for label, name in zip(options, names):
            if name not in self.component_names:
                self.component_options.append(label)
                self.component_names.append(name)

    # ------------------------------------------------------------------ #
    # internal: reset to a default (empty) layout
    # ------------------------------------------------------------------ #
    def _reset_to_default(self, num_of_exp: int = 1) -> None:
        # 1D: experiment, 2D: row, 3D: column, element = component label
        layout_setting = [[[""]]]
        for _ in range(1, num_of_exp):
            layout_setting.append([[""]])
        st.session_state[self._k("layout")] = layout_setting
        st.session_state[self._k("num_experiments")] = num_of_exp
        if self.store.result_exists(self.layout_id, self.layout_tag):
            self.store.remove_results(self.layout_id)
        st.session_state[self._k("edit_mode")] = True

    # ------------------------------------------------------------------ #
    # internal: edit-mode per-experiment editor
    # ------------------------------------------------------------------ #
    def _container_for_new_component(self, exp_index, row_index, col_index) -> None:
        sel_key = self._k(f"select_new_{exp_index}_{row_index}_{col_index}")

        def _is_unique(new_option) -> bool:
            layout_setting = st.session_state[self._k("layout")]
            if any(
                col
                for row in layout_setting[exp_index]
                for col in row
                if col == new_option
            ):
                st.session_state[self._k("component_error")] = "Duplicated component!"
                return False
            return True

        def _add_new_component() -> None:
            new_option = st.session_state[sel_key]
            if new_option and new_option != "Select..." and _is_unique(new_option):
                st.session_state[self._k("layout")][exp_index][row_index][
                    col_index
                ] = new_option

        st.selectbox(
            "New component to add",
            ["Select..."] + self.component_options,
            key=sel_key,
            on_change=_add_new_component,
            placeholder="Select...",
        )

    def _layout_editor_per_experiment(self, exp_index) -> None:
        layout_info = st.session_state[self._k("layout")][exp_index]

        for row_index, row in enumerate(layout_info):
            st_cols = st.columns(
                len(row) + 1 if len(row) < self.max_columns else len(row)
            )
            for col_index, col in enumerate(row):
                if not col:  # empty -> show the "add component" selector
                    with st_cols[col_index].container():
                        self._container_for_new_component(
                            exp_index, row_index, col_index
                        )
                else:
                    with st_cols[col_index]:
                        c1, c2 = st.columns([5, 1])
                        c1.info(col)
                        if c2.button(
                            "x",
                            key=self._k(f"del_{exp_index}_{row_index}_{col_index}"),
                            type="primary",
                        ):
                            layout_info[row_index].pop(col_index)
                            st.rerun()

            # new column button (capped at max_columns)
            if len(row) < self.max_columns:
                if st_cols[-1].button(
                    "***+***", key=self._k(f"new_col_{exp_index}_{row_index}")
                ):
                    layout_info[row_index].append("")
                    st.rerun()

        # new row button
        if st.button("***+***", key=self._k(f"new_row_{exp_index}")):
            layout_info.append([""])
            st.rerun()

    # ------------------------------------------------------------------ #
    # internal: button handlers (edit/save/reset/upload)
    # ------------------------------------------------------------------ #
    def _handle_setting_buttons(self) -> None:
        if st.session_state.get(self._k("reset_clicked")):
            self._reset_to_default()

        uploaded = st.session_state.get(self._k("uploaded_json"))
        if uploaded is not None:
            uploaded_layout = json.load(uploaded)
            # Validate the uploaded (trimmed, internal-name) layout BEFORE expanding,
            # matching the oracle handleSettingButtons: internal names never contain
            # the "(... needed)" dependency labels, so only the empty-input check
            # fires on upload (dependency validation happens later, at Save time).
            # Validating the expanded labels here would wrongly reject hand-crafted
            # uploads, diverging from the oracle.
            validated = self.validate(uploaded_layout)
            if validated != "":
                st.session_state[self._k("component_error")] = validated
            else:
                st.session_state[self._k("layout")] = self.expand(uploaded_layout)
                st.session_state[self._k("num_experiments")] = len(uploaded_layout)

    def _handle_edit_and_save_buttons(self) -> None:
        # "Edit" clicked: re-enter edit mode, seeded from the saved layout
        if st.session_state.get(self._k("edit_clicked")):
            st.session_state[self._k("edit_mode")] = True
            saved = self.get_layout()
            st.session_state[self._k("num_experiments")] = (
                len(saved[0]) if saved is not None else 1
            )
            if saved is not None:
                st.session_state[self._k("layout")] = self.expand(saved[0])

        # "Save" clicked: validate, persist trimmed layout + side_by_side, leave edit mode
        if st.session_state.get(self._k("save_clicked")):
            got_error = self.validate()
            st.session_state[self._k("save_error")] = got_error
            if not got_error:
                self.set_layout(
                    self.trim(st.session_state[self._k("layout")]),
                    side_by_side=st.session_state.get(self._k("side_by_side"), False),
                )
                st.session_state[self._k("edit_mode")] = False

    # ------------------------------------------------------------------ #
    # the whole editor page
    # ------------------------------------------------------------------ #
    def render(self) -> None:
        """Draw the full Layout Manager page (edit/saved modes, buttons, upload/download, tips)."""
        # default edit mode
        if st.session_state.get(self._k("edit_mode")) is None:
            st.session_state[self._k("edit_mode")] = True

        # handle button onclicks
        self._handle_setting_buttons()
        self._handle_edit_and_save_buttons()

        # initialize layout setting
        if self._k("layout") not in st.session_state:
            saved = self.get_layout()
            if saved is not None:
                st.session_state[self._k("layout")] = self.expand(saved[0])
                st.session_state[self._k("num_experiments")] = len(
                    st.session_state[self._k("layout")]
                )
                st.session_state[self._k("side_by_side")] = saved[1]
                st.session_state[self._k("edit_mode")] = False
            else:
                self._reset_to_default()
        # the number of experiments changed -> reset to that count
        elif (
            self._k("num_experiments") in st.session_state
            and len(st.session_state[self._k("layout")])
            != st.session_state[self._k("num_experiments")]
        ):
            self._reset_to_default(st.session_state[self._k("num_experiments")])

        edit_mode = st.session_state[self._k("edit_mode")]
        saved = self.get_layout()

        # title and setting buttons
        c1, c2, c3, c4, c5 = st.columns([6, 1, 1, 1, 1])
        c1.title(self.title)

        # side-by-side view option for exactly 2 experiments
        if self._k("side_by_side") not in st.session_state:
            st.session_state[self._k("side_by_side")] = False
        show_side_by_side = (
            st.session_state.get(self._k("num_experiments")) == 2
        ) or (not edit_mode and saved is not None and len(saved[0]) == 2)
        if show_side_by_side:
            self._v_space(1, c2)
            st.session_state[self._k("side_by_side")] = c2.checkbox(
                "Side-by-Side View",
                value=st.session_state[self._k("side_by_side")],
                help="If checked, experiments will be shown side-by-side",
                disabled=(not edit_mode),
            )

        # Load existing layout setting file
        self._v_space(1, c3)
        c3.button("Load Setting", key=self._k("load_clicked"))

        # Save current layout setting (JSON download of the trimmed layout)
        self._v_space(1, c4)
        c4.download_button(
            label="Save Setting",
            data=json.dumps(self.trim(st.session_state[self._k("layout")])),
            file_name=self.download_name,
            mime="json",
            disabled=(self.validate() != ""),
        )

        # Reset settings to default
        self._v_space(1, c5)
        c5.button("Reset Setting", key=self._k("reset_clicked"))

        # File uploader, shown when "Load Setting" was clicked
        if st.session_state.get(self._k("load_clicked")):
            st.file_uploader(
                "Choose a json file", type="json", key=self._k("uploaded_json")
            )

        # Main part
        if (not edit_mode) and (saved is not None):
            # saved-mode
            for exp_index in range(len(saved[0])):
                layout_per_exp = saved[0][exp_index]
                with st.expander("Experiment #%d" % (exp_index + 1), expanded=True):
                    for row in layout_per_exp:
                        st_cols = st.columns(len(row))
                        for col_index, col in enumerate(row):
                            st_cols[col_index].info(
                                self.component_options[
                                    self.component_names.index(col)
                                ]
                            )
        else:
            # edit-mode
            st.selectbox(
                "**#Experiments to view at once**",
                list(range(1, self.max_experiments + 1)),
                key=self._k("num_experiments"),
            )
            for exp_index in range(st.session_state[self._k("num_experiments")]):
                with st.expander("Experiment #%d" % (exp_index + 1)):
                    self._layout_editor_per_experiment(exp_index)

        # edit/save buttons
        _, edit_btn_col, save_btn_col = st.columns([9, 1, 1])
        edit_btn_col.button("Edit", key=self._k("edit_clicked"), disabled=edit_mode)
        save_btn_col.button(
            "Save", key=self._k("save_clicked"), disabled=(not edit_mode)
        )

        # error/success messages
        if self._k("save_error") in st.session_state and st.session_state.get(
            self._k("save_clicked")
        ):
            error_message = st.session_state[self._k("save_error")]
            if error_message:
                st.error("Error: " + error_message, icon="🚨")
            else:
                st.success("Layouts Saved", icon="✔️")
        if st.session_state.get(self._k("component_error")):
            st.error(
                "Error: " + st.session_state[self._k("component_error")], icon="🚨"
            )
            del st.session_state[self._k("component_error")]

        # tips
        st.info(
            """
**💡 Tips**

- If nothing is set, the default layout will be used in the Viewer

- Don't forget to click "save" on the bottom-right corner to save your setting
"""
        )

    # ------------------------------------------------------------------ #
    # internal: vertical spacing helper (self-contained; no external import)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _v_space(n: int, col=None) -> None:
        """Insert ``n`` blank lines (markdown ``#``) for vertical alignment of widgets."""
        target = col if col is not None else st
        for _ in range(n):
            target.markdown("#")
