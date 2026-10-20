"""
OpenMS-Insight components outside Streamlit.

An Insight component renders through ``openms_insight.rendering.bridge``,
which relies on three Streamlit pieces: ``st.session_state``, ``st.rerun()``
and a declared component whose frontend is Insight's Vue bundle in an iframe.
This module runs the unchanged bridge with those three replaced: a dict per
viewer as session state, a rerun that restarts the dashboard function here,
and a component function that records each component's arguments for the
browser. The browser hosts the unchanged Vue bundle and speaks the Streamlit
component protocol to it (``frontend/src/lib/results/InsightView.svelte``).

A dashboard is a plain function that builds Insight components and calls
them, as a Streamlit results page would::

    def my_dashboard(workflow_dir: Path) -> None:
        state = StateManager()
        Table(cache_id="ids", data_path=..., cache_path=...)(key="ids", state_manager=state)

openms-insight is optional: it belongs to the app built from the template,
not to the template itself.
"""

from __future__ import annotations

import base64
import copy
import importlib
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

MAX_RUNS = 12  # reruns per request before giving up on convergence
MAX_SESSIONS = 64

# The bridge is patched process-wide while a dashboard runs, so runs are serial.
_lock = threading.Lock()
_sessions: OrderedDict[str, "_Session"] = OrderedDict()


class _SessionState(dict):
    """Stands in for st.session_state: item and attribute access to one dict."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        self.pop(name, None)


class _Rerun(Exception):
    pass


class _Session:
    def __init__(self) -> None:
        self.state = _SessionState()
        # The last value each component sent, returned on every run as
        # Streamlit returns a component's current value.
        self.values: dict[str, Any] = {}


def available() -> bool:
    try:
        import openms_insight  # noqa: F401
    except ImportError:
        return False
    return True


def dist_dir() -> Path:
    import openms_insight

    return Path(openms_insight.__file__).parent / "js-component" / "dist"


def load_dashboard(ref: str) -> Callable[..., None]:
    """``"package.module:function"`` to the dashboard function."""
    module, _, name = ref.partition(":")
    return getattr(importlib.import_module(module), name)


def _session(session_id: str, dashboard: str) -> _Session:
    key = f"{session_id}|{dashboard}"
    sess = _sessions.pop(key, None) or _Session()
    _sessions[key] = sess
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)
    return sess


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _ipc(table) -> str:
    import pyarrow as pa

    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return base64.b64encode(sink.getvalue().to_pybytes()).decode()


def _small_types(table):
    """Large string/binary columns as plain ones: the bundle's Arrow reader lacks the large types."""
    import pyarrow as pa

    def small(t):
        if pa.types.is_large_string(t):
            return pa.string()
        if pa.types.is_large_binary(t):
            return pa.binary()
        if pa.types.is_large_list(t):
            return pa.list_(small(t.value_type))
        return t

    schema = pa.schema([f.with_type(small(f.type)) for f in table.schema], metadata=table.schema.metadata)
    return table if schema.equals(table.schema) else table.cast(schema)


def _arrow_frame(df: pd.DataFrame) -> dict[str, str]:
    """A DataFrame argument as Streamlit sends it: data, index, columns as Arrow IPC."""
    import pyarrow as pa

    return {
        "data": _ipc(_small_types(pa.Table.from_pandas(df))),
        "index": _ipc(pa.table({"index": pa.array(range(len(df)), pa.int64())})),
        "columns": _ipc(pa.table({"columns": pa.array([str(c) for c in df.columns], pa.string())})),
    }


def _is_frame(value: Any) -> bool:
    if isinstance(value, pd.DataFrame):
        return True
    try:
        import polars as pl
    except ImportError:
        return False
    return isinstance(value, (pl.DataFrame, pl.LazyFrame))


def _to_pandas(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    import polars as pl

    if isinstance(value, pl.LazyFrame):
        value = value.collect()
    return value.to_pandas()


def _marshal(call: dict[str, Any]) -> dict[str, Any]:
    """Split a component call into JSON args and DataFrame args, as Streamlit does."""
    args, dfs = {}, []
    for k, v in call.items():
        if k == "key":
            continue
        if _is_frame(v):
            dfs.append({"key": k, "value": _arrow_frame(_to_pandas(v))})
        else:
            args[k] = _json_safe(v)
    return {"key": call["key"], "height": call.get("height"), "args": args, "dfs": dfs}


def render(
    session_id: str,
    dashboard: str,
    context: dict[str, Any],
    update: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Run a dashboard until its components settle, as Streamlit's rerun loop would.

    ``update`` is ``{"key", "value"}`` from a component's setComponentValue.
    Returns every component the last run rendered, in order, ready for the
    browser's ``streamlit:render`` message.
    """
    import streamlit

    from openms_insight.rendering import bridge

    fn = load_dashboard(dashboard)
    with _lock:
        sess = _session(session_id, dashboard)
        if update is not None:
            sess.values[update["key"]] = update.get("value")

        calls: dict[str, dict[str, Any]] = {}

        def vue_func(**kwargs: Any) -> Any:
            calls[kwargs["key"]] = kwargs
            # update_from_vue pops keys off the value, so each run gets a copy
            return copy.deepcopy(sess.values.get(kwargs["key"]))

        def rerun(*_args: Any, **_kwargs: Any) -> None:
            raise _Rerun()

        saved = {
            "session_state": getattr(streamlit, "session_state"),
            "rerun": streamlit.rerun,
            "vue": bridge.get_vue_component_function,
        }
        streamlit.session_state = sess.state
        streamlit.rerun = rerun
        bridge.get_vue_component_function = lambda: vue_func
        try:
            settled: dict[str, dict[str, Any]] | None = None
            for _ in range(MAX_RUNS):
                calls = {}
                try:
                    fn(**context)
                except _Rerun:
                    continue
                settled = calls
                break
            result = settled if settled is not None else calls
        finally:
            streamlit.session_state = saved["session_state"]
            streamlit.rerun = saved["rerun"]
            bridge.get_vue_component_function = saved["vue"]
        return [_marshal(c) for c in result.values()]
