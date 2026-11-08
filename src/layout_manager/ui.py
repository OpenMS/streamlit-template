"""Streamlit side of the layout manager: the editor and the grid renderer.

The editor runs entirely in the browser (``frontend/index.html``, plain
JavaScript with no build step), so arranging components never reruns the
script. Python only hears from it when the user presses Save or Reset.
"""

import copy
import functools
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import streamlit as st
import streamlit.components.v1 as st_components

from src.layout_manager.layout import (
    ANNOTATIONS_PREFIX,
    MAX_COLUMNS,
    ZOOM_PREFIX,
    Layout,
    analysis_label,
    apply_defaults,
    apply_preset,
    capture_defaults,
    differs_from_defaults,
    has_defaults,
    join_labels,
    missing_analyses,
    clear_layout,
    load_layout,
    load_views,
    match_preset,
    resolve_layout,
    save_layout,
    save_views,
    select_view,
    set_view_defaults,
    validate_layout,
    validate_views,
)

_editor = st_components.declare_component(
    "layout_manager_editor", path=str(Path(__file__).parent / "frontend")
)
_view_bar = st_components.declare_component(
    "layout_manager_view_bar", path=str(Path(__file__).parent / "view_bar")
)


def layout_editor(
    path: Path,
    components: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    max_experiments: int = 1,
    max_columns: int = MAX_COLUMNS,
    target: str = "the Viewer",
    experiment_label: str = "Experiment",
    export_filename: str = "layout.json",
) -> bool:
    """Drag-and-drop editor that saves a layout to ``path`` (JSON).

    Returns True in the run that saved or reset the layout (not after a
    refused save), so a caller drawing it in a dialog can rerun the page.

    Args:
        path: Where the layout is stored, e.g. ``<workspace>/layouts/viewer.json``.
            The page that shows the components reads it with ``resolve_layout``.
        components: Catalog entries ``{"name", "label", "group", "requires"?}``.
        default_layout: Rows of component names used until a layout is saved.
        key: Streamlit key of the editor.
        max_experiments: More than 1 lets users add experiments (one grid per
            file, e.g. to compare runs) and put two of them side by side.
        max_columns: Components per row.
        target: How the editor refers to the page that shows the layout.
        experiment_label: What one experiment is called in the editor.
        export_filename: File name of the Export download.
    """
    revision_key = f"{key}_revision"
    handled_key = f"{key}_handled"
    st.session_state.setdefault(revision_key, 0)

    # A submitted value is in session state at the start of the rerun it
    # triggers, so persist it before rendering and the editor gets fresh args.
    submitted = st.session_state.get(key)
    error = ""
    done = False
    if submitted and submitted.get("nonce") != st.session_state.get(handled_key):
        st.session_state[handled_key] = submitted.get("nonce")
        if submitted.get("action") == "save":
            layout = submitted.get("layout")
            error = validate_layout(layout, components, max_experiments, max_columns)
            if not error:
                save_layout(path, layout, bool(submitted.get("side_by_side")))
                done = True
        elif submitted.get("action") == "reset":
            clear_layout(path)
            st.session_state[revision_key] += 1
            done = True

    saved = load_layout(path)
    _editor(
        components=list(components),
        default_layout=default_layout,
        saved_layout=saved[0] if saved else None,
        side_by_side=saved[1] if saved else False,
        max_experiments=max_experiments,
        max_columns=max_columns,
        revision=st.session_state[revision_key],
        server_error=error,
        target=target,
        experiment_label=experiment_label,
        export_filename=export_filename,
        key=key,
        default=None,
    )
    return done


def render_layout(
    rows: List[List[str]],
    renderers: Mapping[str, Callable[[], Any]],
    labels: Mapping[str, str] | None = None,
    components: Optional[Sequence[Dict[str, Any]]] = None,
    available: Optional[Any] = None,
    analyses: Optional[Dict[str, Any]] = None,
    on_missing: Optional[Callable[[List[str], str], Any]] = None,
    key: str = "layout",
    dataset_label: str = "run",
) -> None:
    """Render one experiment: each row in ``st.columns``, each cell by its renderer.

    ``renderers`` maps component names to functions that draw the component in
    the current container. A component without a renderer shows a notice instead
    of stopping the page.

    With ``components`` and ``available`` (the analyses the shown dataset has),
    a component that ``needs`` an analysis the dataset lacks draws a note in its
    place, with a button that calls ``on_missing(missing, component_name)`` (as
    a button callback, so it may set state the next run reads, such as
    ``request_analysis``). ``analyses`` names the analyses (see ``view_bar``).
    """
    by_name = {c["name"]: c for c in components or []}
    for row in rows:
        columns = st.columns(len(row)) if len(row) > 1 else [st.container()]
        for column, name in zip(columns, row):
            with column:
                label = (labels or {}).get(name) or by_name.get(name, {}).get("label", name)
                missing = missing_analyses([name], components or [], available) if components else []
                if missing:
                    missing_note(label, missing, analyses, on_missing, f"{key}_missing_{name}", name,
                                  dataset_label)
                    continue
                renderer = renderers.get(name)
                if renderer is None:
                    st.info(f"{label} is not available here.")
                else:
                    renderer()


def missing_note(label: str, missing: Sequence[str], analyses: Optional[Dict[str, Any]],
                 on_missing: Optional[Callable[[List[str], str], Any]], key: str, name: str,
                 dataset_label: str = "run") -> None:
    """The note component ``name`` draws in place of itself when its dataset lacks ``missing``.

    ``render_layout`` draws it; an app with a grid renderer of its own calls it
    the same way. The button calls ``on_missing(missing, name)``.
    """
    needed = join_labels([analysis_label(a, analyses) for a in missing])
    with st.container(border=True):
        st.markdown(f"**{label}**  \n:gray[Needs {needed}, which this {dataset_label} was not processed with.]")
        if on_missing is not None:
            st.button(f"Add {needed}…", key=key, icon=":material/add_circle:",
                      on_click=on_missing, args=(list(missing), name))


def _dataset_missing(on_missing, dataset, index, missing, name) -> None:
    """``render_layout``'s callback for one experiment of ``render_experiments``."""
    on_missing(missing, name, dataset, index)


def request_analysis(key: str, missing: Sequence[str], view: Optional[str] = None,
                     component: Optional[str] = None) -> None:
    """Open the dialog of ``view_bar(key=key)`` that offers the analyses ``missing``.

    Call it from a button callback (``on_click``), e.g. as ``on_missing`` of
    ``render_layout``/``render_experiments``, so the bar drawn in the same run
    opens the dialog.
    """
    st.session_state[f"{key}_missing"] = {"missing": list(missing), "view": view, "component": component}


def missing_analysis_dialog(
    key: str,
    title: str,
    message: str,
    options: Sequence[Dict[str, Any]],
) -> None:
    """A dialog offering ways to get results a view or component needs.

    ``options`` are ``{"label", "help"?, "icon"?, "on_click", "primary"?}``. A
    click closes the dialog, calls ``on_click()`` (which may switch pages or
    change the layout) and reruns. Drawn by ``view_bar``; call it yourself only
    on a page without a bar. ``key`` is the flag ``request_analysis`` sets.
    """
    flag = f"{key}_missing"

    def _closed() -> None:
        st.session_state.pop(flag, None)

    @st.dialog(title, on_dismiss=_closed)
    def _dialog() -> None:
        st.markdown(message)
        if not options:
            st.caption("This page offers no way to add it here.")
        for index, option in enumerate(options):
            with st.container(border=True):
                clicked = st.button(
                    option["label"], key=f"{key}_missing_option_{index}", icon=option.get("icon"),
                    type="primary" if option.get("primary", index == 0) else "secondary",
                    width="stretch",
                )
                if option.get("help"):
                    st.caption(option["help"])
            if clicked:
                _closed()
                if option.get("on_click"):
                    option["on_click"]()
                st.rerun()
        if st.button("Cancel", key=f"{key}_missing_cancel"):
            _closed()
            st.rerun()

    _dialog()


def layout_button(
    path: Path,
    components: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    label: str = "Edit layout",
    help_text: str = "",
    **editor_args: Any,
) -> None:
    """A button that opens ``layout_editor`` in a dialog over the page.

    A dialog reruns on its own when its widgets change, so after a save or a
    reset it reruns the whole page, which closes the dialog and shows the new
    layout. A refused save keeps the dialog open with the editor's message.
    The dialog stays open over a rerun of the page it did not ask for (a
    component on the page can rerun it right after the click), until it is
    closed or saved. ``editor_args`` go to ``layout_editor``
    (``max_experiments``, ``experiment_label``, ...).
    """
    open_key = f"{key}_dialog_open"

    def _closed() -> None:
        st.session_state[open_key] = False

    @st.dialog(label, width="large", on_dismiss=_closed)
    def _dialog() -> None:
        if help_text:
            st.caption(help_text)
        if layout_editor(path, components, default_layout, key=key, **editor_args):
            _closed()
            st.rerun()

    if st.button(label, key=f"{key}_open", icon=":material/dashboard_customize:"):
        st.session_state[open_key] = True
    if st.session_state.get(open_key):
        _dialog()


CUSTOM = "_custom"


def layout_presets(
    path: Path,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    label: str = "View",
    custom_label: str = "Custom",
) -> Optional[str]:
    """A selector of preset views; picking one stores its layout at ``path``.

    ``presets`` are ``{"name", "label", "layout": rows, "help"?}``. The
    selector shows the preset the current layout is, or ``custom_label`` for a
    layout saved in the editor that is none of them. Picking a preset keeps
    the experiments and their datasets, only their components change. Returns
    the name of the preset shown, or None for a custom layout.
    """
    layout, _ = resolve_layout(path, components, default_layout)
    current = match_preset(layout, presets, components)
    labels = {p["name"]: p["label"] for p in presets}
    options = list(labels) + ([] if current else [CUSTOM])
    labels[CUSTOM] = custom_label
    # The selector follows the stored layout, also after a save in the editor
    st.session_state[key] = current or CUSTOM

    def _picked() -> None:
        preset = next((p for p in presets if p["name"] == st.session_state.get(key)), None)
        if preset is not None:
            apply_preset(path, preset["layout"])

    tips = [f"**{p['label']}**: {p['help']}" for p in presets if p.get("help")]
    # A radio rather than st.segmented_control, whose string value AppTest
    # cannot hold (it reads it as a list of characters on the next run)
    st.radio(
        label, options, format_func=lambda name: labels.get(name, name), key=key,
        on_change=_picked, help="\n\n".join(tips) or None, horizontal=True,
    )
    return current


def _views(path, components, presets, default_layout, default_view) -> Dict[str, Any]:
    """``load_views``, with ``default_view`` current while nothing is saved."""
    state = load_views(path, components, presets, default_layout)
    if default_view and load_layout(path) is None and any(v["name"] == default_view for v in state["views"]):
        state["current"] = default_view
    return state


def views_editor(
    path: Path,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    max_experiments: int = 1,
    max_columns: int = MAX_COLUMNS,
    target: str = "the Viewer",
    experiment_label: str = "Experiment",
    new_view: bool = False,
    default_view: Optional[str] = None,
) -> bool:
    """The editor of a page's views: their order, which are in the bar, their components.

    Ready-made views (``presets``) can be reordered and kept out of the bar but
    not changed; users duplicate one to change it, or start a new view. Returns
    True in the run that saved or reset (not after a refused save).
    ``new_view`` opens the editor on a new view, a copy of the current one; until
    its components change, a "Start from" choice swaps in another view's.
    ``default_view`` is the current view while nothing is saved (see ``view_bar``).
    """
    revision_key = f"{key}_revision"
    handled_key = f"{key}_handled"
    st.session_state.setdefault(revision_key, 0)
    submitted = st.session_state.get(key)
    error = ""
    done = False
    if submitted and submitted.get("nonce") != st.session_state.get(handled_key):
        st.session_state[handled_key] = submitted.get("nonce")
        if submitted.get("action") == "save":
            state = load_views(path, components, presets, default_layout)
            by_name = {v["name"]: v for v in state["views"]}
            for sent in submitted.get("views") or []:
                # A view the assistant made is read-only like a ready-made one: its stored label and rows count
                stored = by_name.get(sent.get("name")) if isinstance(sent, dict) else None
                if stored and stored.get("by") == "assistant":
                    sent.update(label=stored["label"], rows=stored["rows"])
            error = validate_views(submitted, components, presets, default_layout, max_experiments, max_columns)
            if not error:
                views = []
                for sent in submitted["views"]:
                    view = dict(by_name.get(sent["name"], {}))
                    if not view.get("preset"):
                        view.update(name=sent["name"], label=str(sent["label"]).strip(),
                                    rows=sent["rows"], preset=False)
                    source = by_name.get(sent.get("copy_of")) if sent["name"] not in by_name else None
                    if source and source.get("defaults") and not view.get("defaults"):
                        # A duplicate keeps the zoom and selection saved with the view it copies
                        view["defaults"] = copy.deepcopy(source["defaults"])
                    view["in_bar"] = bool(sent.get("in_bar", True))
                    views.append(view)
                save_views(path, {"views": views, "current": submitted["current"],
                                  "experiments": submitted.get("experiments", 1),
                                  "side_by_side": submitted.get("side_by_side")})
                done = True
        elif submitted.get("action") == "reset":
            clear_layout(path)
            st.session_state[revision_key] += 1
            done = True

    state = _views(path, components, presets, default_layout, default_view)
    fresh = fresh_from = None
    if new_view:
        source = next(v for v in state["views"] if v["name"] == state["current"])
        taken = {v["name"] for v in state["views"]}
        number = next(n for n in range(1, len(taken) + 2) if f"custom-{n}" not in taken)
        labels = {v["label"].lower() for v in state["views"]}
        base = f"{source['label']} (copy)"
        label = next(c for c in [base] + [f"{base} {n}" for n in range(2, len(labels) + 3)]
                     if c.lower() not in labels)
        fresh = f"custom-{number}"
        # Right after the view it starts from, or at the end of the bar
        index = state["views"].index(source) + 1 if source["in_bar"] else sum(v["in_bar"] for v in state["views"])
        state["views"].insert(index, {"name": fresh, "label": label,
                                      "rows": [list(r) for r in source["rows"]],
                                      "preset": False, "in_bar": True})
        state["current"] = fresh
        fresh_from = source["name"]
    _editor(
        components=list(components),
        default_layout=default_layout,
        saved_layout=None,
        side_by_side=state["side_by_side"],
        # The assistant's views are locked like ready-made ones (Duplicate to edit)
        views=[dict(v, preset=True) if v.get("by") == "assistant" else v for v in state["views"]],
        current=state["current"],
        experiments=state["experiments"],
        fresh=fresh,
        fresh_from=fresh_from,
        max_experiments=max_experiments,
        max_columns=max_columns,
        revision=f"{st.session_state[revision_key]}-{int(new_view)}",
        server_error=error,
        target=target,
        experiment_label=experiment_label,
        key=key,
        default=None,
    )
    return done


def view_bar(
    path: Path,
    components: Sequence[Dict[str, Any]],
    presets: Sequence[Dict[str, Any]],
    default_layout: List[List[str]],
    key: str,
    actions: Optional[Sequence[Dict[str, Any]]] = None,
    details: bool = False,
    label: str = "View",
    dialog_title: str = "Customize views",
    help_text: str = "",
    default_view: Optional[str] = None,
    available: Optional[Any] = None,
    analyses: Optional[Dict[str, Any]] = None,
    unavailable_options: Optional[Callable[[List[str], Optional[Dict[str, Any]]], Sequence[Dict[str, Any]]]] = None,
    dataset_label: str = "run",
    states: Optional[Callable[[int], Any]] = None,
    datasets: Optional[Callable[[int], Optional[str]]] = None,
    **editor_args: Any,
) -> str:
    """The view bar: as many views as fit, the rest in More, and ✏️ Customize.

    **Views the data was not processed for.** Components may name the analyses
    they need (``"needs": "identification"``). ``available`` is the set of
    analyses the shown dataset has (None: all); a view with a component needing
    another one is drawn disabled, and clicking it opens a dialog instead of
    switching. ``analyses`` names them, ``{"identification": "Identification"}``
    or ``{"identification": {"label": ..., "help": ...}}``.
    ``unavailable_options(missing, view)`` returns the dialog's choices
    (``missing_analysis_dialog``), e.g. run the missing analysis on this run,
    add more files, or bring in another run for a comparison. The same dialog
    opens for a component's note (``render_layout(on_missing=...)`` with
    ``request_analysis(key, ...)``).

    Views are the page's ``presets`` (``{"name", "label", "layout", "help"?}``)
    and the views users make in the editor, in the order users give them.
    Picking one stores its components as the layout ``resolve_layout`` reads,
    so call this before ``resolve_layout``. The bar ends in +, which opens the
    editor on a new view that starts as a copy of the current one. ``details`` adds the number of components below each
    name while there is room. ``actions`` are icon
    buttons drawn after ✏️, ``{"id", "icon", "help", "on_click"}``; their
    ``on_click`` runs in the rerun after the click (open a dialog there).
    ``default_view`` names the view that is current while nothing is saved
    (the default is the first): a page that picks its default by what a
    dataset holds renders that view's rows itself until the user picks one.
    ``editor_args`` go to ``views_editor`` (``max_experiments``, ...).

    **Zoom and selection.** ``states(index)`` returns the OpenMS-Insight
    ``StateManager`` of experiment ``index`` (``experiment_state(...)`` with the
    same arguments the renderers use), and ``datasets(index)`` the id of the
    dataset it shows (optional). A view of the user's own can then keep the
    zoom and selection shown as its defaults (📌), opening it applies them,
    and ↺ brings them back after the user changed them. Components keep their
    zoom in the state only when given ``zoom_identifier=zoom_identifier(name)``.
    Returns the name of the current view.
    """
    open_key = f"{key}_dialog_open"
    new_key = f"{key}_dialog_new"
    handled_key = f"{key}_bar_handled"
    clicked = None
    submitted = st.session_state.get(f"{key}_bar")
    if submitted and submitted.get("nonce") != st.session_state.get(handled_key):
        st.session_state[handled_key] = submitted.get("nonce")
        if submitted.get("action") == "pick":
            select_view(path, submitted.get("view"), components, presets, default_layout)
        elif submitted.get("action") == "edit":
            st.session_state[open_key] = True
            st.session_state[new_key] = bool(submitted.get("new_view"))
        elif submitted.get("action") == "button":
            clicked = submitted.get("id")
            if clicked == _SAVE_DEFAULTS:
                st.session_state[f"{key}_defaults_dialog"] = True
        elif submitted.get("action") == "unavailable":
            view = submitted.get("view")
            request_analysis(key, [], view=view)

    state = _views(path, components, presets, default_layout, default_view)
    missing_of = {v["name"]: missing_analyses(v["rows"], components, available) for v in state["views"]}
    # A view the shown dataset cannot fill is locked, the current one too: show
    # the first view it can fill instead (left as it is when none can be)
    if missing_of.get(state["current"]):
        fallback = next((v["name"] for v in state["views"] if not missing_of[v["name"]]), None)
        if fallback is not None:
            state["current"] = fallback
            save_views(path, state)

    current_view = next((v for v in state["views"] if v["name"] == state["current"]), None)
    experiments = int(state.get("experiments") or 1)
    builtin: List[Dict[str, Any]] = []
    if states is not None:
        applied_key = f"{key}_defaults_applied"
        # Opening a view (also the one shown when the session starts) applies its defaults
        if st.session_state.get(applied_key) != state["current"]:
            st.session_state[applied_key] = state["current"]
            if has_defaults(current_view):
                _apply_view_defaults(current_view, states, datasets, experiments)
        if clicked == _RESTORE_DEFAULTS and has_defaults(current_view):
            _apply_view_defaults(current_view, states, datasets, experiments)
        builtin = _defaults_actions(current_view, states, datasets, experiments)

    def _bar_view(v: Dict[str, Any]) -> Dict[str, Any]:
        out = {k: v[k] for k in ("name", "label", "rows", "preset", "in_bar", "help") if k in v}
        if missing_of.get(v["name"]):
            out["missing"] = join_labels([analysis_label(a, analyses) for a in missing_of[v["name"]]])
            out["dataset_label"] = dataset_label
        return out

    _view_bar(
        views=[_bar_view(v) for v in state["views"]],
        current=state["current"],
        details=details,
        label=label,
        customize_help="Customize views",
        actions=builtin + [{k: a[k] for k in ("id", "icon", "label", "help") if k in a} for a in actions or []],
        key=f"{key}_bar",
        default=None,
    )

    def _closed() -> None:
        st.session_state[open_key] = False
        st.session_state[new_key] = False

    @st.dialog(dialog_title, width="large", on_dismiss=_closed)
    def _dialog() -> None:
        if help_text:
            st.caption(help_text)
        new = st.session_state.get(new_key, False)
        shown = components
        if available is not None:
            # The palette marks what the shown dataset was not processed for
            shown = []
            for c in components:
                lacking = missing_analyses([c["name"]], components, available)
                shown.append(dict(c, unavailable="add " + join_labels(
                    [analysis_label(a, analyses) for a in lacking]) + f" to this {dataset_label} to use it")
                    if lacking else c)
        if views_editor(path, shown, presets, default_layout, key=f"{key}_editor",
                        new_view=new, default_view=default_view, **editor_args):
            _closed()
            st.rerun()

    if st.session_state.get(open_key):
        _dialog()
    elif states is not None and st.session_state.get(f"{key}_defaults_dialog") and current_view:
        _defaults_dialog(key, path, current_view, components, presets, default_layout,
                         states, datasets, experiments, dataset_label)
    request = st.session_state.get(f"{key}_missing")
    if request and not st.session_state.get(open_key):
        view = next((v for v in state["views"] if v["name"] == request.get("view")), None)
        missing = list(request.get("missing") or (missing_of.get(view["name"], []) if view else []))
        if not missing:
            st.session_state.pop(f"{key}_missing", None)
        else:
            needed = join_labels([analysis_label(a, analyses) for a in missing])
            what = f"The view **{view['label']}**" if view else (
                f"**{request['component']}**" if request.get("component") else "This")
            label_of = {c["name"]: c["label"] for c in components}
            if not view and request.get("component") in label_of:
                what = f"**{label_of[request['component']]}**"
            message = f"{what} needs {needed}, which this {dataset_label} was not processed with."
            details = [analyses[m]["help"] for m in missing
                       if isinstance((analyses or {}).get(m), dict) and analyses[m].get("help")]
            if details:
                message += "\n\n" + "\n\n".join(details)
            options = list(unavailable_options(missing, view) if unavailable_options else [])
            missing_analysis_dialog(key, f"Add {needed}", message, options)
    for action in actions or []:
        if action.get("id") == clicked and action.get("on_click"):
            action["on_click"]()
    return state["current"]


_SAVE_DEFAULTS = "_save_view_defaults"
_RESTORE_DEFAULTS = "_restore_view_defaults"


def _keeps_defaults(view: Optional[Dict[str, Any]]) -> bool:
    """Whether the user can store a zoom and selection on ``view``.

    Not on a ready-made view, nor on one the AI assistant made: those are
    read-only (Duplicate to edit).
    """
    return bool(view) and not view.get("preset") and view.get("by") != "assistant"


def _dataset_of(datasets: Optional[Callable[[int], Optional[str]]], index: int) -> Optional[str]:
    return datasets(index) if datasets is not None else None


def _apply_view_defaults(view: Dict[str, Any], states: Callable[[int], Any],
                         datasets: Optional[Callable[[int], Optional[str]]], experiments: int) -> None:
    for index, entry in enumerate((view.get("defaults") or [])[:experiments]):
        if entry:
            apply_defaults(states(index), entry, _dataset_of(datasets, index))


def _defaults_actions(view: Optional[Dict[str, Any]], states: Callable[[int], Any],
                      datasets: Optional[Callable[[int], Optional[str]]], experiments: int) -> List[Dict[str, Any]]:
    """The bar's 📌 and ↺ for the current view."""
    actions: List[Dict[str, Any]] = []
    if has_defaults(view):
        changed = any(
            entry and differs_from_defaults(_stored(states(i)), entry, _dataset_of(datasets, i))
            for i, entry in enumerate((view.get("defaults") or [])[:experiments]))
        actions.append({
            "id": _RESTORE_DEFAULTS, "icon": "↺",
            "help": ("Back to the zoom and selection saved with this view" if changed
                     else "The zoom and selection saved with this view are shown"),
        })
    if _keeps_defaults(view):
        actions.append({
            "id": _SAVE_DEFAULTS, "icon": "📌",
            "help": ("Replace the zoom and selection saved with this view" if has_defaults(view)
                     else "Save the zoom and selection shown now with this view"),
        })
    return actions


def _describe(entry: Dict[str, Any], labels: Dict[str, str]) -> List[str]:
    """Lines saying what one experiment's defaults hold."""
    def short(value: Any) -> str:
        text = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        return text if len(text) <= 40 else text[:39] + "…"

    def number(x: float) -> str:
        return f"{x:.4g}"

    lines = []
    for identifier, value in (entry.get("selection") or {}).items():
        name, _, owner = identifier.partition("@")
        where = f" ({labels.get(owner, owner)})" if owner else ""
        lines.append(f"Selected {name.replace('_', ' ')}{where}: `{short(value)}`")
    for component, zoom in (entry.get("zoom") or {}).items():
        axes = ", ".join(f"{axis} {number(r[0])} to {number(r[1])}" for axis, r in zoom.items())
        lines.append(f"Zoom of {labels.get(component, component)}: {axes}")
    for component, points in (entry.get("annotations") or {}).items():
        lines.append(f"{len(points)} annotated points in {labels.get(component, component)}")
    return lines


def _defaults_dialog(key: str, path: Path, view: Dict[str, Any], components, presets, default_layout,
                     states: Callable[[int], Any], datasets: Optional[Callable[[int], Optional[str]]],
                     experiments: int, dataset_label: str) -> None:
    open_key = f"{key}_defaults_dialog"

    def _closed() -> None:
        st.session_state[open_key] = False

    @st.dialog("Zoom and selection of this view", on_dismiss=_closed)
    def _dialog() -> None:
        labels = {c["name"]: c["label"] for c in components}
        captured = [capture_defaults(_stored(states(i)), _dataset_of(datasets, i))
                    for i in range(experiments)]
        st.markdown(f"Opening **{view['label']}** will show this again; ↺ in the bar brings it back "
                    "after you change it.")
        anything = False
        for index, entry in enumerate(captured):
            lines = _describe(entry, labels)
            anything = anything or bool(lines)
            if experiments > 1:
                st.markdown(f"**{dataset_label.capitalize()} {index + 1}**")
            st.markdown("\n".join(f"- {line}" for line in lines) if lines
                        else "Nothing selected or zoomed.")
        save_col, remove_col = st.columns(2)
        if save_col.button("Save with this view", type="primary", disabled=not anything,
                           key=f"{key}_defaults_save", width="stretch"):
            set_view_defaults(path, view["name"], captured, components, presets, default_layout)
            # Shown as saved: opening it again need not apply anything now
            st.session_state[f"{key}_defaults_applied"] = view["name"]
            _closed()
            st.rerun()
        if has_defaults(view) and remove_col.button("Remove the saved ones", key=f"{key}_defaults_remove",
                                                    width="stretch"):
            set_view_defaults(path, view["name"], None, components, presets, default_layout)
            _closed()
            st.rerun()

    _dialog()


def _selection_key(key: str, index: int) -> str:
    return f"{key}_experiment_{index}"


def selected_datasets(key: str, count: int) -> List[Optional[str]]:
    """The dataset ids picked in the selectors of ``render_experiments``."""
    return [st.session_state.get(_selection_key(key, i)) for i in range(count)]


def _selector(
    key: str,
    index: int,
    datasets: Mapping[str, str],
    label: str,
    buttons: Optional[Callable[[int], Any]],
) -> Optional[str]:
    """The dataset selector of experiment ``index``; returns the picked id."""
    ids = list(datasets)
    state = _selection_key(key, index)
    widget = f"{state}_select"
    # Keep the pick by id, so a renamed or added dataset does not move it.
    picked = st.session_state.get(state)
    if picked not in datasets:
        picked = ids[index] if index < len(ids) else (ids[0] if ids else None)
        st.session_state[state] = picked
    if st.session_state.get(widget) != picked:
        st.session_state[widget] = picked

    def _changed() -> None:
        st.session_state[state] = st.session_state.get(widget)

    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.selectbox(
            label, ids, key=widget, format_func=lambda i: datasets.get(i, i),
            on_change=_changed,
        )
        if buttons is not None:
            buttons(index)
    return st.session_state.get(state)


def render_experiments(
    layout: Layout,
    side_by_side: bool,
    datasets: Mapping[str, str],
    renderers: Callable[[str, int], Mapping[str, Callable[[], Any]]],
    key: str,
    labels: Optional[Mapping[str, str]] = None,
    experiment_label: str = "Experiment",
    buttons: Optional[Callable[[int], Any]] = None,
    components: Optional[Sequence[Dict[str, Any]]] = None,
    available: Optional[Callable[[str], Any]] = None,
    analyses: Optional[Dict[str, Any]] = None,
    on_missing: Optional[Callable[[List[str], str, str, int], Any]] = None,
    dataset_label: str = "run",
) -> List[Optional[str]]:
    """Render every experiment of ``layout``, each below its own dataset selector.

    This is FLASHApp's Viewer: one grid per experiment, each showing the dataset
    (a run, a file, a comparison) picked above it, so users compare datasets by
    adding experiments in the layout editor. Two experiments marked side by side
    share the width; any other number are drawn one below the other.

    Args:
        layout: Experiments as ``resolve_layout`` returns them.
        side_by_side: Draw two experiments in two columns.
        datasets: Dataset id -> label, in the order the selectors offer them.
            Experiment ``n`` starts on the ``n``-th dataset.
        renderers: ``renderers(dataset_id, index)`` returns the renderers of
            experiment ``index`` for that dataset (component name -> function).
            Give each experiment its own widget keys and, with Insight, its own
            ``StateManager``, so selections in one do not move the other.
        key: Prefix of the selectors' session keys.
        labels: Component name -> label, for the notice of a missing renderer.
        experiment_label: Label of each selector.
        buttons: ``buttons(index)`` draws buttons right of a selector, such as
            ``layout_button``.
        components, available, analyses: With ``available(dataset_id)``
            returning the analyses a dataset has, components that need another
            draw a note (see ``render_layout``); its button calls
            ``on_missing(missing, component, dataset_id, index)``.

    Returns:
        The dataset id picked in each experiment (None without datasets).
    """
    if not datasets:
        return [None] * len(layout)

    def one(index: int, rows: List[List[str]]) -> Optional[str]:
        dataset = _selector(key, index, datasets, experiment_label, buttons)
        if dataset is not None:
            has = available(dataset) if available is not None else None
            missing_cb = None
            if on_missing is not None:
                missing_cb = functools.partial(_dataset_missing, on_missing, dataset, index)
            render_layout(rows, renderers(dataset, index), labels, components=components,
                          available=has, analyses=analyses, on_missing=missing_cb,
                          key=f"{key}_{index}", dataset_label=dataset_label)
        return dataset

    if side_by_side and len(layout) == 2:
        picked = []
        for column, (index, rows) in zip(st.columns(2), enumerate(layout)):
            with column:
                picked.append(one(index, rows))
        return picked
    picked = []
    for index, rows in enumerate(layout):
        if index:
            st.divider()
        picked.append(one(index, rows))
    return picked



def experiment_state(
    key: str,
    index: int,
    dataset_id: Optional[str] = None,
    private: Sequence[str] = (),
    owner: str = "",
) -> Any:
    """The OpenMS-Insight ``StateManager`` all components of one experiment share.

    Keyed by experiment, not by view or component: a protein, peptide or
    spectrum picked in one view stays picked when the user switches views,
    and two experiments side by side keep their own selections. Pass the
    experiment's ``dataset_id`` so that picking another dataset clears the
    selection.

    An identifier that means something else in each component (a row number
    of that component's own table, say) is listed in ``private`` with the
    component's name as ``owner``: it is then kept apart for that component,
    while every other identifier stays shared. Needs ``openms-insight``, which
    the template does not install.
    """
    from openms_insight import StateManager  # pylint: disable=import-outside-toplevel

    name = f"{key}_state_{index}"
    shown = f"{name}_dataset"
    if dataset_id is not None and st.session_state.get(shown) != dataset_id:
        st.session_state.pop(name, None)
        st.session_state[shown] = dataset_id
    # Also without private identifiers: other components' private ones stay hidden
    return _private_state(StateManager)(name, {i: f"{i}@{owner}" for i in private})


def _stored(state: Any) -> Dict[str, Any]:
    """All of an experiment's selections, those a component keeps apart (``row@table``) too."""
    stored = getattr(state, "stored_selections", None)
    return stored() if callable(stored) else state.get_all_selections()


def _private_state(base: type) -> type:
    """A ``StateManager`` that keeps some identifiers apart under other names."""

    class PrivateState(base):  # type: ignore[misc, valid-type]
        def __init__(self, session_key: str, renamed: Dict[str, str]):
            self._renamed = renamed
            self._back = {v: k for k, v in renamed.items()}
            super().__init__(session_key)

        def _to_store(self, identifier: str) -> str:
            return self._renamed.get(identifier, identifier)

        def _from_store(self, values: Dict[str, Any]) -> Dict[str, Any]:
            # The shared names this component keeps apart are hidden, its own shown under them
            # (a zoom or a view's annotations, ``zoom@`` / ``annotations@<component>``, are shared)
            out = {k: v for k, v in values.items()
                   if k not in self._renamed and ("@" not in k or k.startswith((ZOOM_PREFIX, ANNOTATIONS_PREFIX)))}
            out.update({self._back[k]: v for k, v in values.items() if k in self._back})
            return out

        def get_selection(self, identifier: str) -> Any:
            return super().get_selection(self._to_store(identifier))

        def set_selection(self, identifier: str, value: Any) -> bool:
            return super().set_selection(self._to_store(identifier), value)

        def clear_selection(self, identifier: str) -> bool:
            return super().clear_selection(self._to_store(identifier))

        def get_all_selections(self) -> Dict[str, Any]:
            return self._from_store(super().get_all_selections())

        def stored_selections(self) -> Dict[str, Any]:
            """Every identifier as stored, those kept apart for a component too."""
            return super().get_all_selections()

        def get_state_for_vue(self) -> Dict[str, Any]:
            return self._from_store(super().get_state_for_vue())

        def update_from_vue(self, vue_state: Dict[str, Any]) -> bool:
            if vue_state is None:
                return super().update_from_vue(vue_state)
            return super().update_from_vue({self._to_store(k): v for k, v in vue_state.items()})

    return PrivateState
