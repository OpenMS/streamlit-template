"""
Declarative description of a workflow's upload, configure and results pages.

In the Streamlit app, ``upload()``/``configure()``/``results()`` are code that
draws widgets. A Svelte frontend cannot run that code, so the same pages are
described as data here and rendered by ``frontend/src/lib/workflow/``. The
names follow the StreamlitUI calls they replace, so porting a workflow is a
line-by-line translation:

    self.ui.upload_widget(key, file_types, name, fallback) -> Upload(...)
    self.ui.select_input_file(key, multiple=True)          -> SelectFiles(...)
    self.ui.input_TOPP(tool, custom_defaults=...)          -> TOPP(...)
    self.ui.input_python(script)                           -> Python(...)
    self.ui.input_widget(key, default, name, ...)          -> Widget(...)
    st.tabs([...])                                         -> Tab(...)
    reactive=True + an ``if`` on the value                 -> visible_if={...}

``execution()`` is not described here: it stays a method of the workflow's
WorkflowManager subclass and runs unchanged (see server/runner.py).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class Upload:
    key: str
    file_types: list[str]
    name: str = ""
    fallback: list[str] = field(default_factory=list)
    type: str = "upload"


@dataclass
class SelectFiles:
    key: str
    name: str = ""
    multiple: bool = True
    visible_if: Optional[dict] = None
    type: str = "select-files"


@dataclass
class Widget:
    key: str
    default: Any = None
    name: str = ""
    help: str = ""
    # auto, text, textarea, number, selectbox, slider, checkbox, multiselect, password
    widget_type: str = "auto"
    options: Optional[list] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step_size: Optional[float] = None
    visible_if: Optional[dict] = None
    type: str = "widget"


@dataclass
class TOPP:
    tool: str
    exclude_parameters: list[str] = field(default_factory=list)
    include_parameters: list[str] = field(default_factory=list)
    flag_parameters: list[str] = field(default_factory=list)
    custom_defaults: dict = field(default_factory=dict)
    tool_instance_name: Optional[str] = None
    display_tool_name: bool = True
    display_subsections: bool = True
    visible_if: Optional[dict] = None
    type: str = "topp"

    @property
    def instance(self) -> str:
        return self.tool_instance_name or self.tool


@dataclass
class Python:
    script: str
    visible_if: Optional[dict] = None
    type: str = "python"


@dataclass
class Markdown:
    text: str
    type: str = "markdown"


@dataclass
class Tab:
    label: str
    items: list
    type: str = "tab"


@dataclass
class ResultView:
    """
    One block on the results page. ``component`` names a Svelte component in
    ``frontend/src/lib/results/registry.ts``; ``props`` are passed to it.
    Built in: ``table`` (server-paginated TSV/CSV), ``download``, and
    ``insight``, which runs the OpenMS-Insight dashboard function named in
    ``props["dashboard"]`` (``"module:function"``, see ``server/dashboards.py``).
    """

    component: str
    title: str = ""
    props: dict = field(default_factory=dict)
    type: str = "result"


@dataclass
class WorkflowSpec:
    name: str
    module: str
    cls: str
    upload: list = field(default_factory=list)
    configure: list = field(default_factory=list)
    results: list = field(default_factory=list)
    download_exclude: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def slug(self) -> str:
        # Same rule as WorkflowManager: "TOPP Workflow" -> "topp-workflow"
        return self.name.replace(" ", "-").lower()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["slug"] = self.slug
        return d

    def iter_items(self, kind: str):
        def walk(items):
            for it in items:
                if isinstance(it, Tab):
                    yield from walk(it.items)
                elif getattr(it, "type", None) == kind:
                    yield it

        yield from walk(self.configure)
