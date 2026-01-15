# Dual-Framework Core Library Architecture

## Executive Summary

This document outlines an architecture for a core library that supports both Streamlit and NiceGUI frontends. The approach uses **protocol-based abstractions** with **backend adapters** to allow the same workflow code to run on either framework with minimal changes.

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Architecture Overview](#2-architecture-overview)
3. [Core Abstractions](#3-core-abstractions)
4. [Backend Adapters](#4-backend-adapters)
5. [State Management](#5-state-management)
6. [Widget Factory](#6-widget-factory)
7. [File Handling](#7-file-handling)
8. [Navigation & Layout](#8-navigation--layout)
9. [Execution Model](#9-execution-model)
10. [Migration Path](#10-migration-path)
11. [Implementation Plan](#11-implementation-plan)
12. [Trade-offs & Considerations](#12-trade-offs--considerations)

---

## 1. Design Philosophy

### Principles

1. **Protocol-First Design**: Define interfaces (protocols) that both backends must implement
2. **Dependency Injection**: Inject the appropriate backend at runtime
3. **Minimal Leaky Abstractions**: Hide framework-specific details behind clean APIs
4. **Progressive Enhancement**: Allow framework-specific features when needed
5. **Zero-Copy Migration**: Existing workflow code should work with minimal changes

### Goals

- **Single Workflow Definition**: Write `Workflow.upload()`, `configure()`, `execution()`, `results()` once
- **Backend Swappable**: Switch between Streamlit and NiceGUI via configuration
- **Testable**: Core logic can be tested independently of UI framework
- **Extensible**: Easy to add future backends (e.g., Panel, Gradio)

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Application Layer                            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Workflow Classes                        │    │
│  │   (Workflow, CustomWorkflow, etc.)                        │    │
│  │   - upload(), configure(), execution(), results()         │    │
│  └─────────────────────────────────────────────────────────┘    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ uses
┌───────────────────────────▼─────────────────────────────────────┐
│                     Core Library (openms-workflow-core)          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Protocol Layer                         │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐    │   │
│  │  │ UIProtocol  │ │StateProtocol│ │ ExecutorProtocol │    │   │
│  │  └─────────────┘ └─────────────┘ └──────────────────┘    │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐    │   │
│  │  │FileProtocol │ │LayoutProto  │ │ NavigationProto  │    │   │
│  │  └─────────────┘ └─────────────┘ └──────────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Manager Layer                            │   │
│  │  WorkflowManager, WidgetFactory, ParameterManager,        │   │
│  │  FileManager, CommandExecutor, Logger                     │   │
│  │  (Framework-agnostic business logic)                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ implements
┌───────────────────────────▼─────────────────────────────────────┐
│                     Backend Adapters                             │
│  ┌────────────────────────┐    ┌────────────────────────────┐   │
│  │   Streamlit Backend    │    │    NiceGUI Backend         │   │
│  │  ┌──────────────────┐  │    │  ┌──────────────────────┐  │   │
│  │  │ StreamlitUI      │  │    │  │ NiceGUIUI            │  │   │
│  │  │ StreamlitState   │  │    │  │ NiceGUIState         │  │   │
│  │  │ StreamlitLayout  │  │    │  │ NiceGUILayout        │  │   │
│  │  │ StreamlitFiles   │  │    │  │ NiceGUIFiles         │  │   │
│  │  └──────────────────┘  │    │  └──────────────────────┘  │   │
│  └────────────────────────┘    └────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Abstractions

### 3.1 Protocol Definitions

```python
# src/core/protocols.py
from typing import Protocol, Any, List, Dict, Callable, Optional, Union
from pathlib import Path
from abc import abstractmethod

class WidgetProtocol(Protocol):
    """Protocol for UI widgets - represents a single widget instance."""

    @property
    def value(self) -> Any:
        """Get the current value of the widget."""
        ...

    @value.setter
    def value(self, val: Any) -> None:
        """Set the value of the widget."""
        ...

    def on_change(self, callback: Callable[[Any], None]) -> None:
        """Register a callback for value changes."""
        ...


class UIProtocol(Protocol):
    """Protocol for UI operations - widget creation and display."""

    # Text Inputs
    def text_input(
        self,
        key: str,
        label: str,
        value: str = "",
        help: Optional[str] = None,
        password: bool = False,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        """Create a text input widget."""
        ...

    def text_area(
        self,
        key: str,
        label: str,
        value: str = "",
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        """Create a text area widget."""
        ...

    # Numeric Inputs
    def number_input(
        self,
        key: str,
        label: str,
        value: Union[int, float] = 0,
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None,
        step: Union[int, float] = 1,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        """Create a number input widget."""
        ...

    def slider(
        self,
        key: str,
        label: str,
        value: Union[int, float] = 0,
        min_value: Union[int, float] = 0,
        max_value: Union[int, float] = 100,
        step: Union[int, float] = 1,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        """Create a slider widget."""
        ...

    # Selection Inputs
    def checkbox(
        self,
        key: str,
        label: str,
        value: bool = False,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        """Create a checkbox widget."""
        ...

    def selectbox(
        self,
        key: str,
        label: str,
        options: List[Any],
        value: Optional[Any] = None,
        format_func: Optional[Callable[[Any], str]] = None,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        """Create a selectbox widget."""
        ...

    def multiselect(
        self,
        key: str,
        label: str,
        options: List[Any],
        value: Optional[List[Any]] = None,
        format_func: Optional[Callable[[Any], str]] = None,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        """Create a multiselect widget."""
        ...

    def radio(
        self,
        key: str,
        label: str,
        options: List[Any],
        value: Optional[Any] = None,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        """Create a radio button group."""
        ...

    # Action Widgets
    def button(
        self,
        label: str,
        key: Optional[str] = None,
        on_click: Optional[Callable] = None,
        disabled: bool = False,
        type: str = "secondary",  # "primary", "secondary"
    ) -> bool:
        """Create a button. Returns True if clicked (Streamlit), triggers callback (NiceGUI)."""
        ...

    # Display Widgets
    def markdown(self, content: str) -> None:
        """Display markdown content."""
        ...

    def text(self, content: str) -> None:
        """Display plain text."""
        ...

    def code(self, content: str, language: Optional[str] = None) -> None:
        """Display code block."""
        ...

    def dataframe(self, data: Any, **kwargs) -> None:
        """Display a dataframe."""
        ...

    def plotly(self, figure: Any) -> None:
        """Display a Plotly figure."""
        ...

    def image(self, source: Union[str, Path, bytes], **kwargs) -> None:
        """Display an image."""
        ...

    # Status & Progress
    def spinner(self, text: str = "Loading...") -> Any:
        """Create a spinner context manager."""
        ...

    def progress(self, value: float = 0.0) -> Any:
        """Create a progress bar."""
        ...

    def success(self, message: str) -> None:
        """Display a success message."""
        ...

    def error(self, message: str) -> None:
        """Display an error message."""
        ...

    def warning(self, message: str) -> None:
        """Display a warning message."""
        ...

    def info(self, message: str) -> None:
        """Display an info message."""
        ...


class StateProtocol(Protocol):
    """Protocol for state management."""

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from state."""
        ...

    def set(self, key: str, value: Any) -> None:
        """Set a value in state."""
        ...

    def delete(self, key: str) -> None:
        """Delete a key from state."""
        ...

    def has(self, key: str) -> bool:
        """Check if key exists in state."""
        ...

    def clear(self) -> None:
        """Clear all state."""
        ...

    def get_all(self) -> Dict[str, Any]:
        """Get all state as dictionary."""
        ...


class LayoutProtocol(Protocol):
    """Protocol for layout management."""

    def columns(self, spec: List[Union[int, float]]) -> List[Any]:
        """Create columns with given widths."""
        ...

    def tabs(self, labels: List[str]) -> List[Any]:
        """Create tabs with given labels."""
        ...

    def expander(self, label: str, expanded: bool = False) -> Any:
        """Create an expandable section."""
        ...

    def container(self, **kwargs) -> Any:
        """Create a container."""
        ...

    def sidebar(self) -> Any:
        """Access the sidebar."""
        ...

    def form(self, key: str) -> Any:
        """Create a form context."""
        ...


class FileProtocol(Protocol):
    """Protocol for file handling."""

    def upload(
        self,
        key: str,
        label: str,
        file_types: Optional[List[str]] = None,
        multiple: bool = False,
        on_upload: Optional[Callable] = None,
    ) -> Any:
        """Create a file upload widget."""
        ...

    def download(
        self,
        label: str,
        data: Union[bytes, str],
        filename: str,
        mime: Optional[str] = None,
    ) -> None:
        """Create a download button/trigger download."""
        ...


class NavigationProtocol(Protocol):
    """Protocol for navigation."""

    def get_query_param(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a query parameter."""
        ...

    def set_query_param(self, key: str, value: str) -> None:
        """Set a query parameter."""
        ...

    def navigate(self, path: str) -> None:
        """Navigate to a path."""
        ...

    def current_page(self) -> str:
        """Get current page/route."""
        ...


class ExecutorProtocol(Protocol):
    """Protocol for async execution and updates."""

    def schedule_update(self, callback: Callable) -> None:
        """Schedule a UI update."""
        ...

    def run_async(self, coro: Any) -> None:
        """Run an async coroutine."""
        ...

    def create_timer(self, interval: float, callback: Callable) -> Any:
        """Create a recurring timer."""
        ...

    def refresh(self) -> None:
        """Trigger a UI refresh (Streamlit rerun, NiceGUI update)."""
        ...
```

### 3.2 Backend Context

```python
# src/core/context.py
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protocols import (
        UIProtocol, StateProtocol, LayoutProtocol,
        FileProtocol, NavigationProtocol, ExecutorProtocol
    )

@dataclass
class FrameworkContext:
    """Container for all framework-specific implementations."""
    ui: 'UIProtocol'
    state: 'StateProtocol'
    layout: 'LayoutProtocol'
    files: 'FileProtocol'
    navigation: 'NavigationProtocol'
    executor: 'ExecutorProtocol'

    # Framework identifier
    framework: str  # "streamlit" or "nicegui"


# Global context - set at application startup
_context: FrameworkContext = None

def set_context(ctx: FrameworkContext) -> None:
    """Set the global framework context."""
    global _context
    _context = ctx

def get_context() -> FrameworkContext:
    """Get the global framework context."""
    if _context is None:
        raise RuntimeError("Framework context not initialized. Call set_context() first.")
    return _context

# Convenience accessors
def ui() -> 'UIProtocol':
    return get_context().ui

def state() -> 'StateProtocol':
    return get_context().state

def layout() -> 'LayoutProtocol':
    return get_context().layout

def files() -> 'FileProtocol':
    return get_context().files

def navigation() -> 'NavigationProtocol':
    return get_context().navigation

def executor() -> 'ExecutorProtocol':
    return get_context().executor
```

---

## 4. Backend Adapters

### 4.1 Streamlit Backend

```python
# src/backends/streamlit/ui.py
import streamlit as st
from typing import Any, List, Dict, Callable, Optional, Union
from pathlib import Path
from ...core.protocols import UIProtocol, WidgetProtocol


class StreamlitWidget:
    """Wrapper around Streamlit widget that provides unified interface."""

    def __init__(self, key: str, initial_value: Any = None):
        self._key = key
        if key not in st.session_state and initial_value is not None:
            st.session_state[key] = initial_value

    @property
    def value(self) -> Any:
        return st.session_state.get(self._key)

    @value.setter
    def value(self, val: Any) -> None:
        st.session_state[self._key] = val

    def on_change(self, callback: Callable[[Any], None]) -> None:
        # Streamlit handles this through the key mechanism
        # Changes trigger rerun automatically
        pass


class StreamlitUI(UIProtocol):
    """Streamlit implementation of UIProtocol."""

    def text_input(
        self,
        key: str,
        label: str,
        value: str = "",
        help: Optional[str] = None,
        password: bool = False,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        widget_type = "password" if password else "default"
        st.text_input(
            label,
            value=value if key not in st.session_state else st.session_state[key],
            key=key,
            help=help,
            type=widget_type,
            on_change=on_change,
        )
        return StreamlitWidget(key, value)

    def number_input(
        self,
        key: str,
        label: str,
        value: Union[int, float] = 0,
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None,
        step: Union[int, float] = 1,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        st.number_input(
            label,
            value=value if key not in st.session_state else st.session_state[key],
            min_value=min_value,
            max_value=max_value,
            step=step,
            key=key,
            help=help,
            on_change=on_change,
        )
        return StreamlitWidget(key, value)

    def selectbox(
        self,
        key: str,
        label: str,
        options: List[Any],
        value: Optional[Any] = None,
        format_func: Optional[Callable[[Any], str]] = None,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        index = 0
        if value is not None and value in options:
            index = options.index(value)
        st.selectbox(
            label,
            options=options,
            index=index,
            format_func=format_func or str,
            key=key,
            help=help,
            on_change=on_change,
        )
        return StreamlitWidget(key, value)

    def checkbox(
        self,
        key: str,
        label: str,
        value: bool = False,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        st.checkbox(
            label,
            value=value if key not in st.session_state else st.session_state[key],
            key=key,
            help=help,
            on_change=on_change,
        )
        return StreamlitWidget(key, value)

    def button(
        self,
        label: str,
        key: Optional[str] = None,
        on_click: Optional[Callable] = None,
        disabled: bool = False,
        type: str = "secondary",
    ) -> bool:
        return st.button(
            label,
            key=key,
            on_click=on_click,
            disabled=disabled,
            type=type,
        )

    def markdown(self, content: str) -> None:
        st.markdown(content)

    def plotly(self, figure: Any) -> None:
        st.plotly_chart(figure, use_container_width=True)

    def spinner(self, text: str = "Loading..."):
        return st.spinner(text)

    def progress(self, value: float = 0.0):
        return st.progress(value)

    def success(self, message: str) -> None:
        st.success(message)

    def error(self, message: str) -> None:
        st.error(message)

    def warning(self, message: str) -> None:
        st.warning(message)

    def info(self, message: str) -> None:
        st.info(message)

    # ... implement remaining methods


class StreamlitState(StateProtocol):
    """Streamlit implementation of StateProtocol."""

    def __init__(self, prefix: str = ""):
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}" if self._prefix else key

    def get(self, key: str, default: Any = None) -> Any:
        return st.session_state.get(self._key(key), default)

    def set(self, key: str, value: Any) -> None:
        st.session_state[self._key(key)] = value

    def delete(self, key: str) -> None:
        k = self._key(key)
        if k in st.session_state:
            del st.session_state[k]

    def has(self, key: str) -> bool:
        return self._key(key) in st.session_state

    def clear(self) -> None:
        if self._prefix:
            keys_to_delete = [k for k in st.session_state if k.startswith(self._prefix)]
            for k in keys_to_delete:
                del st.session_state[k]
        else:
            st.session_state.clear()

    def get_all(self) -> Dict[str, Any]:
        if self._prefix:
            return {
                k[len(self._prefix):]: v
                for k, v in st.session_state.items()
                if k.startswith(self._prefix)
            }
        return dict(st.session_state)


class StreamlitLayout(LayoutProtocol):
    """Streamlit implementation of LayoutProtocol."""

    def columns(self, spec: List[Union[int, float]]) -> List[Any]:
        return st.columns(spec)

    def tabs(self, labels: List[str]) -> List[Any]:
        return st.tabs(labels)

    def expander(self, label: str, expanded: bool = False) -> Any:
        return st.expander(label, expanded=expanded)

    def container(self, **kwargs) -> Any:
        return st.container(**kwargs)

    def sidebar(self) -> Any:
        return st.sidebar

    def form(self, key: str) -> Any:
        return st.form(key)


class StreamlitExecutor(ExecutorProtocol):
    """Streamlit implementation of ExecutorProtocol."""

    def refresh(self) -> None:
        st.rerun()

    def schedule_update(self, callback: Callable) -> None:
        # In Streamlit, this is typically handled by rerun
        callback()
        st.rerun()

    def run_async(self, coro: Any) -> None:
        # Streamlit doesn't have native async, use experimental
        import asyncio
        asyncio.run(coro)

    def create_timer(self, interval: float, callback: Callable) -> Any:
        # Streamlit doesn't have timers, use time.sleep + rerun
        import time
        time.sleep(interval)
        callback()
        return None
```

### 4.2 NiceGUI Backend

```python
# src/backends/nicegui/ui.py
from nicegui import ui, app
from typing import Any, List, Dict, Callable, Optional, Union
from pathlib import Path
from ...core.protocols import UIProtocol, WidgetProtocol


class NiceGUIWidget:
    """Wrapper around NiceGUI widget that provides unified interface."""

    def __init__(self, element: Any):
        self._element = element
        self._callbacks: List[Callable] = []

    @property
    def value(self) -> Any:
        return self._element.value

    @value.setter
    def value(self, val: Any) -> None:
        self._element.value = val

    def on_change(self, callback: Callable[[Any], None]) -> None:
        self._callbacks.append(callback)
        self._element.on_value_change(lambda e: callback(e.value))


class NiceGUIUI(UIProtocol):
    """NiceGUI implementation of UIProtocol."""

    def __init__(self, state: 'NiceGUIState'):
        self._state = state

    def text_input(
        self,
        key: str,
        label: str,
        value: str = "",
        help: Optional[str] = None,
        password: bool = False,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        # Get stored value or use default
        stored_value = self._state.get(key, value)

        element = ui.input(
            label=label,
            value=stored_value,
            password=password,
        )

        if help:
            element.tooltip(help)

        # Sync with state on change
        def handle_change(e):
            self._state.set(key, e.value)
            if on_change:
                on_change()

        element.on_value_change(handle_change)
        return NiceGUIWidget(element)

    def number_input(
        self,
        key: str,
        label: str,
        value: Union[int, float] = 0,
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None,
        step: Union[int, float] = 1,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        stored_value = self._state.get(key, value)

        element = ui.number(
            label=label,
            value=stored_value,
            min=min_value,
            max=max_value,
            step=step,
        )

        if help:
            element.tooltip(help)

        def handle_change(e):
            self._state.set(key, e.value)
            if on_change:
                on_change()

        element.on_value_change(handle_change)
        return NiceGUIWidget(element)

    def selectbox(
        self,
        key: str,
        label: str,
        options: List[Any],
        value: Optional[Any] = None,
        format_func: Optional[Callable[[Any], str]] = None,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        stored_value = self._state.get(key, value or (options[0] if options else None))

        # NiceGUI select uses dict for options with custom labels
        if format_func:
            options_dict = {opt: format_func(opt) for opt in options}
            element = ui.select(options_dict, value=stored_value, label=label)
        else:
            element = ui.select(options, value=stored_value, label=label)

        if help:
            element.tooltip(help)

        def handle_change(e):
            self._state.set(key, e.value)
            if on_change:
                on_change()

        element.on_value_change(handle_change)
        return NiceGUIWidget(element)

    def checkbox(
        self,
        key: str,
        label: str,
        value: bool = False,
        help: Optional[str] = None,
        on_change: Optional[Callable] = None,
    ) -> WidgetProtocol:
        stored_value = self._state.get(key, value)

        element = ui.checkbox(label, value=stored_value)

        if help:
            element.tooltip(help)

        def handle_change(e):
            self._state.set(key, e.value)
            if on_change:
                on_change()

        element.on_value_change(handle_change)
        return NiceGUIWidget(element)

    def button(
        self,
        label: str,
        key: Optional[str] = None,
        on_click: Optional[Callable] = None,
        disabled: bool = False,
        type: str = "secondary",
    ) -> bool:
        color = "primary" if type == "primary" else None
        btn = ui.button(label, on_click=on_click, color=color)
        if disabled:
            btn.disable()
        # NiceGUI buttons don't return bool, they use callbacks
        return False

    def markdown(self, content: str) -> None:
        ui.markdown(content)

    def plotly(self, figure: Any) -> None:
        ui.plotly(figure)

    def spinner(self, text: str = "Loading..."):
        return ui.spinner(text)

    def progress(self, value: float = 0.0):
        return ui.linear_progress(value=value)

    def success(self, message: str) -> None:
        ui.notify(message, type="positive")

    def error(self, message: str) -> None:
        ui.notify(message, type="negative")

    def warning(self, message: str) -> None:
        ui.notify(message, type="warning")

    def info(self, message: str) -> None:
        ui.notify(message, type="info")


class NiceGUIState(StateProtocol):
    """NiceGUI implementation of StateProtocol using app.storage."""

    def __init__(self, storage_type: str = "user"):
        """
        Args:
            storage_type: "user" (server-side per user), "browser" (localStorage),
                         "tab" (per tab), "general" (global)
        """
        self._storage_type = storage_type

    @property
    def _storage(self) -> Dict:
        if self._storage_type == "user":
            return app.storage.user
        elif self._storage_type == "browser":
            return app.storage.browser
        elif self._storage_type == "tab":
            return app.storage.tab
        else:
            return app.storage.general

    def get(self, key: str, default: Any = None) -> Any:
        return self._storage.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._storage[key] = value

    def delete(self, key: str) -> None:
        if key in self._storage:
            del self._storage[key]

    def has(self, key: str) -> bool:
        return key in self._storage

    def clear(self) -> None:
        self._storage.clear()

    def get_all(self) -> Dict[str, Any]:
        return dict(self._storage)


class NiceGUILayout(LayoutProtocol):
    """NiceGUI implementation of LayoutProtocol."""

    def columns(self, spec: List[Union[int, float]]) -> List[Any]:
        # NiceGUI uses row + columns
        row = ui.row()
        cols = []
        for width in spec:
            col = ui.column().classes(f'w-{int(width)}/12')
            cols.append(col)
        return cols

    def tabs(self, labels: List[str]) -> List[Any]:
        tabs = ui.tabs()
        panels = []
        for label in labels:
            with tabs:
                tab = ui.tab(label)
            panels.append(tab)
        return panels

    def expander(self, label: str, expanded: bool = False) -> Any:
        return ui.expansion(label, value=expanded)

    def container(self, **kwargs) -> Any:
        return ui.card(**kwargs)

    def sidebar(self) -> Any:
        return ui.left_drawer()

    def form(self, key: str) -> Any:
        # NiceGUI doesn't have forms, return a card as container
        return ui.card()


class NiceGUIExecutor(ExecutorProtocol):
    """NiceGUI implementation of ExecutorProtocol."""

    def refresh(self) -> None:
        # NiceGUI updates automatically via WebSocket
        ui.update()

    def schedule_update(self, callback: Callable) -> None:
        ui.timer(0, callback, once=True)

    async def run_async(self, coro: Any) -> None:
        await coro

    def create_timer(self, interval: float, callback: Callable) -> Any:
        return ui.timer(interval, callback)
```

---

## 5. State Management

### 5.1 Unified State Store

```python
# src/core/state.py
from typing import Any, Dict, Optional, Callable, List
from pathlib import Path
import json
from .context import state as get_state


class ParameterStore:
    """
    High-level parameter management that works with any backend.
    Handles persistence to JSON and framework state synchronization.
    """

    def __init__(self, workflow_dir: Path, prefix: str = ""):
        self.workflow_dir = workflow_dir
        self.prefix = prefix
        self.params_file = workflow_dir / "params.json"
        self._listeners: Dict[str, List[Callable]] = {}

    def _full_key(self, key: str) -> str:
        return f"{self.prefix}{key}" if self.prefix else key

    def get(self, key: str, default: Any = None) -> Any:
        """Get parameter value, checking framework state first, then JSON."""
        full_key = self._full_key(key)

        # Check framework state first (for current session values)
        framework_state = get_state()
        if framework_state.has(full_key):
            return framework_state.get(full_key)

        # Fall back to persisted JSON
        persisted = self._load_from_json()
        if key in persisted:
            return persisted[key]

        return default

    def set(self, key: str, value: Any, persist: bool = True) -> None:
        """Set parameter value in framework state and optionally persist."""
        full_key = self._full_key(key)

        # Update framework state
        get_state().set(full_key, value)

        # Persist to JSON if requested
        if persist:
            self._save_to_json(key, value)

        # Notify listeners
        self._notify(key, value)

    def _load_from_json(self) -> Dict[str, Any]:
        if self.params_file.exists():
            with open(self.params_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_to_json(self, key: str, value: Any) -> None:
        params = self._load_from_json()
        params[key] = value
        self.params_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.params_file, 'w') as f:
            json.dump(params, f, indent=2)

    def subscribe(self, key: str, callback: Callable[[Any], None]) -> None:
        """Subscribe to parameter changes."""
        if key not in self._listeners:
            self._listeners[key] = []
        self._listeners[key].append(callback)

    def _notify(self, key: str, value: Any) -> None:
        for callback in self._listeners.get(key, []):
            callback(value)

    def export_all(self) -> Dict[str, Any]:
        """Export all parameters as dictionary."""
        return self._load_from_json()

    def import_all(self, params: Dict[str, Any]) -> None:
        """Import parameters from dictionary."""
        for key, value in params.items():
            self.set(key, value)

    def reset(self) -> None:
        """Reset all parameters to defaults."""
        if self.params_file.exists():
            self.params_file.unlink()

        # Clear framework state with prefix
        framework_state = get_state()
        all_state = framework_state.get_all()
        for key in list(all_state.keys()):
            if key.startswith(self.prefix):
                framework_state.delete(key)
```

### 5.2 TOPP Parameter Integration

```python
# src/core/topp_parameters.py
from typing import Dict, Any, List, Optional
from pathlib import Path
import subprocess
import pyopenms as poms


class TOPPParameterManager:
    """
    Framework-agnostic TOPP tool parameter management.
    Handles INI file generation, parsing, and parameter extraction.
    """

    def __init__(self, ini_dir: Path):
        self.ini_dir = ini_dir
        self.ini_dir.mkdir(parents=True, exist_ok=True)

    def get_tool_parameters(
        self,
        tool_name: str,
        exclude: List[str] = None,
        include: List[str] = None,
        custom_defaults: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get parameters for a TOPP tool as a list of parameter specs.

        Returns list of dicts with:
            - key: parameter key
            - name: display name
            - value: current value
            - type: widget type (text, number, checkbox, selectbox, etc.)
            - options: valid options for selectbox
            - help: description
            - advanced: bool
            - section: parameter section
        """
        ini_path = self.ini_dir / f"{tool_name}.ini"

        # Generate INI if needed
        if not ini_path.exists():
            self._generate_ini(tool_name, ini_path, custom_defaults)

        # Parse INI
        param = poms.Param()
        poms.ParamXMLFile().load(str(ini_path), param)

        # Build parameter specs
        exclude = exclude or []
        default_exclude = ["log", "debug", "threads", "no_progress", "force", "version", "test"]
        exclude.extend(default_exclude)

        params = []
        for key in param.keys():
            # Filter
            if include:
                if not any(k.encode() in key for k in include):
                    continue
            else:
                if any(k.encode() in key for k in exclude):
                    continue
                if b"input file" in param.getTags(key) or b"output file" in param.getTags(key):
                    continue

            entry = param.getEntry(key)
            spec = self._entry_to_spec(entry, key, param)

            # Apply custom defaults
            if custom_defaults:
                param_name = key.decode().split(":1:")[1] if ":1:" in key.decode() else key.decode()
                if param_name in custom_defaults:
                    spec["value"] = custom_defaults[param_name]

            params.append(spec)

        return params

    def _generate_ini(self, tool_name: str, ini_path: Path, custom_defaults: Dict[str, Any] = None) -> None:
        """Generate INI file for TOPP tool."""
        subprocess.call([tool_name, "-write_ini", str(ini_path)])

        if custom_defaults:
            param = poms.Param()
            poms.ParamXMLFile().load(str(ini_path), param)
            for key, value in custom_defaults.items():
                encoded_key = f"{tool_name}:1:{key}".encode()
                if encoded_key in param.keys():
                    param.setValue(encoded_key, value)
            poms.ParamXMLFile().store(str(ini_path), param)

    def _entry_to_spec(self, entry, key: bytes, param: poms.Param) -> Dict[str, Any]:
        """Convert pyopenms Param entry to parameter spec."""
        value = entry.value
        valid_strings = [v.decode() for v in entry.valid_strings]

        # Determine widget type
        if isinstance(value, bool):
            widget_type = "checkbox"
        elif isinstance(value, int):
            widget_type = "number"
        elif isinstance(value, float):
            widget_type = "number"
        elif isinstance(value, str):
            widget_type = "selectbox" if valid_strings else "text"
        elif isinstance(value, list):
            widget_type = "textarea"
        else:
            widget_type = "text"

        # Extract section
        key_str = key.decode()
        section = ""
        if ":1:" in key_str:
            parts = key_str.split(":1:")[1].split(":")[:-1]
            section = ":".join(parts)

        return {
            "key": key_str,
            "name": entry.name.decode(),
            "value": value,
            "type": widget_type,
            "options": valid_strings,
            "help": entry.description.decode(),
            "advanced": b"advanced" in param.getTags(key),
            "section": section,
        }
```

---

## 6. Widget Factory

### 6.1 Universal Widget Factory

```python
# src/core/widget_factory.py
from typing import Any, Dict, List, Optional, Union, Callable
from pathlib import Path
from .context import ui, layout
from .state import ParameterStore
from .topp_parameters import TOPPParameterManager


class WidgetFactory:
    """
    Framework-agnostic widget factory.
    Creates widgets using the current framework's UI protocol.
    """

    def __init__(self, parameter_store: ParameterStore, topp_manager: TOPPParameterManager):
        self.params = parameter_store
        self.topp = topp_manager

    def create_widget(
        self,
        key: str,
        widget_type: str = "auto",
        default: Any = None,
        label: Optional[str] = None,
        help: Optional[str] = None,
        options: Optional[List[Any]] = None,
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None,
        step: Union[int, float] = 1,
        on_change: Optional[Callable] = None,
    ) -> Any:
        """
        Create a widget with automatic type detection and state binding.
        """
        # Get current value from parameter store
        value = self.params.get(key, default)
        label = label or key.replace("-", " ").replace("_", " ").title()

        # Auto-detect widget type
        if widget_type == "auto":
            widget_type = self._detect_type(value, options)

        # Handle change with state persistence
        def handle_change():
            # Value is already updated via widget binding
            self.params.set(key, ui().get(key))
            if on_change:
                on_change()

        # Create widget based on type
        if widget_type == "text":
            return ui().text_input(key, label, value or "", help, on_change=handle_change)

        elif widget_type == "textarea":
            return ui().text_area(key, label, value or "", help, on_change=handle_change)

        elif widget_type == "number":
            return ui().number_input(
                key, label, value or 0, min_value, max_value, step, help, on_change=handle_change
            )

        elif widget_type == "checkbox":
            return ui().checkbox(key, label, value or False, help, on_change=handle_change)

        elif widget_type == "selectbox":
            return ui().selectbox(key, label, options or [], value, help=help, on_change=handle_change)

        elif widget_type == "multiselect":
            return ui().multiselect(key, label, options or [], value or [], help=help, on_change=handle_change)

        elif widget_type == "slider":
            return ui().slider(
                key, label, value or min_value or 0,
                min_value or 0, max_value or 100, step, help, on_change=handle_change
            )

        elif widget_type == "password":
            return ui().text_input(key, label, value or "", help, password=True, on_change=handle_change)

        else:
            raise ValueError(f"Unknown widget type: {widget_type}")

    def _detect_type(self, value: Any, options: Optional[List]) -> str:
        """Auto-detect widget type from value and options."""
        if isinstance(value, bool):
            return "checkbox"
        elif isinstance(value, (int, float)) and options is None:
            return "number"
        elif isinstance(value, list) and options is not None:
            return "multiselect"
        elif options is not None:
            return "selectbox"
        elif isinstance(value, str) and "\n" in (value or ""):
            return "textarea"
        else:
            return "text"

    def create_topp_form(
        self,
        tool_name: str,
        num_cols: int = 4,
        exclude: List[str] = None,
        include: List[str] = None,
        custom_defaults: Dict[str, Any] = None,
        show_advanced: bool = False,
        show_sections: bool = True,
    ) -> None:
        """
        Create a form for TOPP tool parameters.
        """
        params = self.topp.get_tool_parameters(
            tool_name, exclude, include, custom_defaults
        )

        # Group by section
        sections: Dict[str, List] = {}
        for p in params:
            if not show_advanced and p["advanced"]:
                continue
            section = p["section"] or "General"
            if section not in sections:
                sections[section] = []
            sections[section].append(p)

        # Render sections
        for section, section_params in sections.items():
            if show_sections and section != "General":
                ui().markdown(f"**{section}**")

            cols = layout().columns([1] * num_cols)
            for i, p in enumerate(section_params):
                col_idx = i % num_cols
                with cols[col_idx]:
                    self.create_widget(
                        key=f"TOPP-{p['key']}",
                        widget_type=p["type"],
                        default=p["value"],
                        label=p["name"],
                        help=p["help"],
                        options=p["options"] if p["options"] else None,
                    )

    def create_python_form(
        self,
        script_path: Path,
        num_cols: int = 3,
        show_advanced: bool = False,
    ) -> None:
        """
        Create a form from Python script DEFAULTS.
        """
        import importlib.util
        import sys

        # Load DEFAULTS from script
        if script_path.parent not in sys.path:
            sys.path.append(str(script_path.parent))

        spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        defaults = getattr(module, "DEFAULTS", None)

        if not defaults:
            ui().error(f"No DEFAULTS found in {script_path}")
            return

        cols = layout().columns([1] * num_cols)
        for i, entry in enumerate(defaults):
            if entry.get("hide", False):
                continue
            if not show_advanced and entry.get("advanced", False):
                continue

            col_idx = i % num_cols
            with cols[col_idx]:
                self.create_widget(
                    key=f"{script_path.name}:{entry['key']}",
                    widget_type=entry.get("widget_type", "auto"),
                    default=entry.get("value"),
                    label=entry.get("name", entry["key"]),
                    help=entry.get("help"),
                    options=entry.get("options"),
                    min_value=entry.get("min"),
                    max_value=entry.get("max"),
                    step=entry.get("step_size", 1),
                )
```

---

## 7. File Handling

### 7.1 Universal File Handler

```python
# src/core/file_handler.py
from typing import List, Optional, Union, Callable, Any
from pathlib import Path
import shutil
from .context import ui, files, layout, state


class FileHandler:
    """
    Framework-agnostic file upload and download handling.
    """

    def __init__(self, workflow_dir: Path):
        self.workflow_dir = workflow_dir
        self.input_dir = workflow_dir / "input-files"

    def upload_widget(
        self,
        key: str,
        file_types: Union[str, List[str]],
        label: Optional[str] = None,
        fallback_files: Optional[List[Path]] = None,
        allow_multiple: bool = True,
        on_upload: Optional[Callable[[List[Path]], None]] = None,
    ) -> None:
        """
        Create a file upload widget with storage management.
        """
        files_dir = self.input_dir / key
        files_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(file_types, str):
            file_types = [file_types]

        label = label or key.replace("-", " ").title()

        # Create upload widget
        def handle_upload(uploaded_files: List[Any]):
            for f in uploaded_files:
                # Handle both file objects and paths
                if hasattr(f, 'read'):
                    # File-like object (web upload)
                    content = f.read()
                    dest = files_dir / f.name
                    with open(dest, 'wb') as out:
                        out.write(content)
                else:
                    # Path (local file)
                    shutil.copy(f, files_dir / Path(f).name)

            if on_upload:
                on_upload(list(files_dir.iterdir()))

            ui().success(f"Successfully uploaded {len(uploaded_files)} file(s)")

        cols = layout().columns([1, 1])

        with cols[0]:
            ui().markdown(f"**Upload {label}**")
            files().upload(
                key=f"{key}-upload",
                label=label,
                file_types=file_types,
                multiple=allow_multiple,
                on_upload=handle_upload,
            )

        # Show current files
        current_files = self.get_files(key)

        if not current_files and fallback_files:
            # Use fallback files
            for f in fallback_files:
                shutil.copy(f, files_dir / f.name)
            current_files = self.get_files(key)
            ui().warning("Using example data files")

        if current_files:
            with cols[1]:
                ui().markdown(f"**Current {label} files:**")
                for f in current_files:
                    ui().text(f"• {f.name}")

                if ui().button(f"🗑️ Clear {label} files", key=f"{key}-clear"):
                    shutil.rmtree(files_dir)
                    files_dir.mkdir()

    def get_files(self, key: str) -> List[Path]:
        """Get list of uploaded files for a key."""
        files_dir = self.input_dir / key
        if not files_dir.exists():
            return []
        return [f for f in files_dir.iterdir() if f.is_file() and f.name != "external_files.txt"]

    def select_files_widget(
        self,
        key: str,
        label: Optional[str] = None,
        multiple: bool = True,
    ) -> Union[Path, List[Path], None]:
        """
        Create a widget to select from uploaded files.
        """
        files = self.get_files(key)

        if not files:
            ui().warning(f"No {key} files uploaded")
            return None

        label = label or f"Select {key.replace('-', ' ')}"
        options = [str(f) for f in files]

        if multiple:
            selected = ui().multiselect(
                f"{key}-select",
                label,
                options=options,
                format_func=lambda x: Path(x).name,
            )
            return [Path(s) for s in (selected.value if hasattr(selected, 'value') else [])]
        else:
            selected = ui().selectbox(
                f"{key}-select",
                label,
                options=options,
                format_func=lambda x: Path(x).name,
            )
            return Path(selected.value) if hasattr(selected, 'value') and selected.value else None

    def download_results(
        self,
        directory: Path,
        filename: str = "results.zip",
    ) -> None:
        """
        Create a download button for a directory as ZIP.
        """
        import zipfile
        from io import BytesIO

        if not directory.exists() or not any(directory.iterdir()):
            ui().error("No results to download")
            return

        # Create ZIP in memory
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in directory.rglob('*'):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(directory.parent))

        buffer.seek(0)
        files().download(
            label="⬇️ Download Results",
            data=buffer.getvalue(),
            filename=filename,
            mime="application/zip",
        )
```

---

## 8. Navigation & Layout

### 8.1 Page Manager

```python
# src/core/navigation.py
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass
from .context import get_context, navigation


@dataclass
class PageConfig:
    """Configuration for a page."""
    name: str
    path: str
    icon: Optional[str] = None
    handler: Optional[Callable] = None
    category: Optional[str] = None


class PageManager:
    """
    Framework-agnostic page/navigation manager.
    """

    def __init__(self):
        self.pages: Dict[str, PageConfig] = {}
        self.categories: Dict[str, List[str]] = {}

    def register_page(
        self,
        name: str,
        path: str,
        handler: Callable,
        icon: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        """Register a page."""
        config = PageConfig(name, path, icon, handler, category)
        self.pages[path] = config

        if category:
            if category not in self.categories:
                self.categories[category] = []
            self.categories[category].append(path)

    def get_page(self, path: str) -> Optional[PageConfig]:
        """Get page config by path."""
        return self.pages.get(path)

    def navigate_to(self, path: str) -> None:
        """Navigate to a page."""
        navigation().navigate(path)

    def current_page(self) -> Optional[PageConfig]:
        """Get current page config."""
        current = navigation().current_page()
        return self.pages.get(current)

    def render_navigation(self) -> None:
        """Render navigation menu (sidebar)."""
        ctx = get_context()

        if ctx.framework == "streamlit":
            self._render_streamlit_nav()
        else:
            self._render_nicegui_nav()

    def _render_streamlit_nav(self) -> None:
        """Render Streamlit navigation."""
        import streamlit as st

        pages = {}
        for category, paths in self.categories.items():
            pages[category] = [
                st.Page(self.pages[p].handler, title=self.pages[p].name, icon=self.pages[p].icon)
                for p in paths
            ]

        pg = st.navigation(pages)
        pg.run()

    def _render_nicegui_nav(self) -> None:
        """Render NiceGUI navigation."""
        from nicegui import ui

        with ui.left_drawer():
            for category, paths in self.categories.items():
                ui.label(category).classes('text-bold')
                for path in paths:
                    page = self.pages[path]
                    icon = page.icon or ""
                    ui.link(f"{icon} {page.name}", path)
```

### 8.2 Workspace Manager

```python
# src/core/workspace.py
from typing import Optional
from pathlib import Path
import uuid
import shutil
from .context import navigation, state


class WorkspaceManager:
    """
    Framework-agnostic workspace management.
    """

    def __init__(self, base_dir: Path, online_mode: bool = False):
        self.base_dir = base_dir
        self.online_mode = online_mode

    def get_current_workspace(self) -> Path:
        """Get current workspace path."""
        workspace_id = navigation().get_query_param("workspace")

        if not workspace_id:
            if self.online_mode:
                # Create new UUID workspace
                workspace_id = str(uuid.uuid4())
                navigation().set_query_param("workspace", workspace_id)
            else:
                workspace_id = "default"

        workspace_path = self.base_dir / workspace_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Store in state
        state().set("workspace", str(workspace_path))
        state().set("workspace_id", workspace_id)

        return workspace_path

    def list_workspaces(self) -> list[str]:
        """List all workspace IDs."""
        if not self.base_dir.exists():
            return []
        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]

    def create_workspace(self, name: Optional[str] = None) -> Path:
        """Create a new workspace."""
        workspace_id = name or str(uuid.uuid4())
        workspace_path = self.base_dir / workspace_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        return workspace_path

    def delete_workspace(self, workspace_id: str) -> None:
        """Delete a workspace."""
        workspace_path = self.base_dir / workspace_id
        if workspace_path.exists():
            shutil.rmtree(workspace_path)

    def switch_workspace(self, workspace_id: str) -> Path:
        """Switch to a different workspace."""
        navigation().set_query_param("workspace", workspace_id)
        return self.get_current_workspace()

    def get_workspace_url(self, workspace_id: Optional[str] = None) -> str:
        """Get shareable URL for a workspace."""
        workspace_id = workspace_id or state().get("workspace_id")
        base_url = state().get("base_url", "http://localhost:8501")
        return f"{base_url}?workspace={workspace_id}"
```

---

## 9. Execution Model

### 9.1 Async Execution Bridge

```python
# src/core/execution.py
from typing import Callable, Optional, Any, AsyncGenerator
from pathlib import Path
import multiprocessing
import asyncio
import time
from .context import get_context, ui, executor
from .logger import Logger


class ExecutionManager:
    """
    Framework-agnostic execution manager for long-running tasks.
    Bridges the gap between Streamlit's sync model and NiceGUI's async model.
    """

    def __init__(self, workflow_dir: Path, logger: Logger):
        self.workflow_dir = workflow_dir
        self.logger = logger
        self.pid_dir = workflow_dir / "pids"

    def is_running(self) -> bool:
        """Check if a workflow is currently running."""
        return self.pid_dir.exists() and any(self.pid_dir.iterdir())

    def start(self, target: Callable, args: tuple = ()) -> None:
        """
        Start a workflow in a separate process.
        Works the same for both frameworks.
        """
        # Clean up
        if self.pid_dir.exists():
            import shutil
            shutil.rmtree(self.pid_dir)

        # Start process
        process = multiprocessing.Process(target=target, args=args)
        process.start()

        # Track PID
        self.pid_dir.mkdir(parents=True)
        (self.pid_dir / str(process.pid)).touch()

    def stop(self) -> None:
        """Stop running workflow."""
        import signal
        import os

        if self.pid_dir.exists():
            for pid_file in self.pid_dir.iterdir():
                try:
                    os.kill(int(pid_file.name), signal.SIGTERM)
                except ProcessLookupError:
                    pass
            import shutil
            shutil.rmtree(self.pid_dir)

    def stream_logs(
        self,
        log_file: Path,
        update_interval: float = 1.0,
    ) -> None:
        """
        Stream logs with framework-appropriate method.
        """
        ctx = get_context()

        if ctx.framework == "streamlit":
            self._stream_logs_streamlit(log_file, update_interval)
        else:
            self._stream_logs_nicegui(log_file, update_interval)

    def _stream_logs_streamlit(self, log_file: Path, interval: float) -> None:
        """Streamlit: Poll and rerun."""
        import streamlit as st

        if not log_file.exists():
            return

        with open(log_file, 'r') as f:
            content = f.read()

        st.code(content, language="neon")

        if self.is_running():
            time.sleep(interval)
            st.rerun()

    def _stream_logs_nicegui(self, log_file: Path, interval: float) -> None:
        """NiceGUI: Use timer and update."""
        from nicegui import ui

        log_display = ui.log()
        last_position = 0

        async def update_logs():
            nonlocal last_position
            if log_file.exists():
                with open(log_file, 'r') as f:
                    f.seek(last_position)
                    new_content = f.read()
                    last_position = f.tell()
                    if new_content:
                        log_display.push(new_content)

            if not self.is_running():
                timer.deactivate()

        timer = ui.timer(interval, update_logs)

    def execution_widget(
        self,
        start_func: Callable,
        log_level: str = "minimal",
    ) -> None:
        """
        Render execution control widget.
        """
        log_file = self.workflow_dir / "logs" / f"{log_level.replace(' ', '-')}.log"

        cols = layout().columns([1, 1])

        with cols[0]:
            if self.is_running():
                if ui().button("Stop Workflow", type="primary"):
                    self.stop()
                    executor().refresh()
            else:
                if ui().button("Start Workflow", type="primary"):
                    start_func()
                    executor().refresh()

        # Show logs
        if log_file.exists():
            self.stream_logs(log_file)
```

---

## 10. Migration Path

### 10.1 Compatibility Layer

For gradual migration, create a compatibility layer that translates old Streamlit calls:

```python
# src/compat/streamlit_compat.py
"""
Compatibility layer that allows old Streamlit code to work with the new abstraction.
Import this instead of streamlit to use the abstraction layer.
"""
from ..core.context import ui, layout, state, files, executor

# Widget functions that delegate to the abstraction
def text_input(label, value="", key=None, help=None, **kwargs):
    return ui().text_input(key or label, label, value, help, **kwargs)

def number_input(label, value=0, key=None, help=None, **kwargs):
    return ui().number_input(key or label, label, value, help=help, **kwargs)

def selectbox(label, options, index=0, key=None, help=None, **kwargs):
    value = options[index] if options else None
    return ui().selectbox(key or label, label, options, value, help=help, **kwargs)

def checkbox(label, value=False, key=None, help=None, **kwargs):
    return ui().checkbox(key or label, label, value, help, **kwargs)

def button(label, key=None, on_click=None, **kwargs):
    return ui().button(label, key, on_click, **kwargs)

def markdown(content):
    return ui().markdown(content)

def columns(spec):
    return layout().columns(spec)

def tabs(labels):
    return layout().tabs(labels)

def expander(label, expanded=False):
    return layout().expander(label, expanded)

# Session state compatibility
class SessionStateProxy:
    def __getitem__(self, key):
        return state().get(key)

    def __setitem__(self, key, value):
        state().set(key, value)

    def __contains__(self, key):
        return state().has(key)

    def get(self, key, default=None):
        return state().get(key, default)

session_state = SessionStateProxy()

# File handling
def file_uploader(label, type=None, key=None, **kwargs):
    return files().upload(key or label, label, type, **kwargs)

def download_button(label, data, file_name, mime=None, **kwargs):
    return files().download(label, data, file_name, mime)

# Refresh
def rerun():
    executor().refresh()

# ... add more as needed
```

### 10.2 Migration Steps

1. **Phase 1**: Install abstraction layer alongside existing code
2. **Phase 2**: Update imports in each file: `import streamlit as st` → `from src.compat import streamlit_compat as st`
3. **Phase 3**: Gradually refactor to use abstraction directly
4. **Phase 4**: Remove compatibility layer, use protocols directly

---

## 11. Implementation Plan

### Phase 1: Core Protocols & Streamlit Backend (Week 1-2)

- [ ] Define all protocol interfaces
- [ ] Implement `StreamlitUI`, `StreamlitState`, `StreamlitLayout`
- [ ] Implement `StreamlitFiles`, `StreamlitNavigation`, `StreamlitExecutor`
- [ ] Create `FrameworkContext` and initialization
- [ ] Basic tests

### Phase 2: State & Parameter Management (Week 2-3)

- [ ] Implement `ParameterStore`
- [ ] Implement `TOPPParameterManager`
- [ ] Implement `WidgetFactory`
- [ ] Migrate `StreamlitUI.input_widget` to use factory
- [ ] Migrate `StreamlitUI.input_TOPP` to use factory

### Phase 3: NiceGUI Backend (Week 3-4)

- [ ] Implement `NiceGUIUI`
- [ ] Implement `NiceGUIState`
- [ ] Implement `NiceGUILayout`
- [ ] Implement `NiceGUIFiles`
- [ ] Implement `NiceGUINavigation`
- [ ] Implement `NiceGUIExecutor`

### Phase 4: WorkflowManager Refactor (Week 4-5)

- [ ] Create framework-agnostic `WorkflowManager`
- [ ] Migrate `show_file_upload_section`
- [ ] Migrate `show_parameter_section`
- [ ] Migrate `show_execution_section`
- [ ] Migrate `show_results_section`

### Phase 5: Page Migration (Week 5-7)

- [ ] Migrate simple tool pages
- [ ] Migrate workflow pages
- [ ] Migrate complex pages
- [ ] Test both backends

### Phase 6: Testing & Documentation (Week 7-8)

- [ ] Comprehensive testing
- [ ] Documentation
- [ ] Example applications
- [ ] Migration guide

---

## 12. Trade-offs & Considerations

### Advantages

1. **Future-Proofing**: Easy to add new backends (Panel, Gradio, etc.)
2. **Testability**: Business logic can be tested without UI framework
3. **Flexibility**: Users can choose their preferred framework
4. **Gradual Migration**: No big-bang rewrite required
5. **Shared Codebase**: One workflow definition works everywhere

### Disadvantages

1. **Abstraction Overhead**: Additional layer adds complexity
2. **Lowest Common Denominator**: May miss framework-specific features
3. **Learning Curve**: Developers need to learn the abstraction
4. **Maintenance**: Must maintain multiple backend implementations
5. **Performance**: Abstraction layer may add slight overhead

### When to Use Framework-Specific Code

Allow escape hatches for framework-specific features:

```python
from src.core.context import get_context

ctx = get_context()

if ctx.framework == "streamlit":
    # Streamlit-specific code
    import streamlit as st
    st.balloons()  # No NiceGUI equivalent
elif ctx.framework == "nicegui":
    # NiceGUI-specific code
    from nicegui import ui
    ui.scene()  # 3D scenes, no Streamlit equivalent
```

### Recommendations

1. **Start with Streamlit backend**: Ensure existing functionality works
2. **Add NiceGUI incrementally**: Page by page
3. **Document escape hatches**: Make framework-specific code obvious
4. **Maintain tests for both**: Ensure parity

---

## Appendix: Project Structure

```
openms-workflow-core/
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── protocols.py          # Protocol definitions
│   │   ├── context.py            # Framework context management
│   │   ├── state.py              # State management
│   │   ├── widget_factory.py     # Widget factory
│   │   ├── file_handler.py       # File handling
│   │   ├── navigation.py         # Navigation/routing
│   │   ├── workspace.py          # Workspace management
│   │   ├── execution.py          # Async execution
│   │   ├── topp_parameters.py    # TOPP parameter handling
│   │   └── logger.py             # Logging
│   │
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── streamlit/
│   │   │   ├── __init__.py
│   │   │   ├── ui.py             # StreamlitUI
│   │   │   ├── state.py          # StreamlitState
│   │   │   ├── layout.py         # StreamlitLayout
│   │   │   ├── files.py          # StreamlitFiles
│   │   │   ├── navigation.py     # StreamlitNavigation
│   │   │   └── executor.py       # StreamlitExecutor
│   │   │
│   │   └── nicegui/
│   │       ├── __init__.py
│   │       ├── ui.py             # NiceGUIUI
│   │       ├── state.py          # NiceGUIState
│   │       ├── layout.py         # NiceGUILayout
│   │       ├── files.py          # NiceGUIFiles
│   │       ├── navigation.py     # NiceGUINavigation
│   │       └── executor.py       # NiceGUIExecutor
│   │
│   ├── compat/
│   │   ├── __init__.py
│   │   └── streamlit_compat.py   # Streamlit compatibility layer
│   │
│   └── workflow/
│       ├── __init__.py
│       ├── manager.py            # WorkflowManager
│       ├── command_executor.py   # CommandExecutor
│       └── file_manager.py       # FileManager
│
├── tests/
│   ├── test_protocols.py
│   ├── test_streamlit_backend.py
│   ├── test_nicegui_backend.py
│   └── test_workflow.py
│
├── examples/
│   ├── streamlit_app.py
│   └── nicegui_app.py
│
├── requirements.txt
├── setup.py
└── README.md
```

---

*Document Version: 1.0*
*Last Updated: 2026-01-15*
