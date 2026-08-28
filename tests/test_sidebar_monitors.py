"""
Tests for the sidebar's "Resource Utilization" expander (Step 2 of the
multi-node plan).

Two decisions live there, and both are about *which machine* the numbers
describe:

* ``monitor_hardware()`` reads psutil in the Streamlit process. Once the
  workers are spread across nodes that process runs no workflow at all, so the
  panel would show an idle 2Gi pod while a 64Gi worker saturates.
* ``monitor_storage()`` reads the shared volume's heartbeat out of Redis, and
  must distinguish "no shared storage here" from "the shared storage is gone"
  from "I cannot tell, because Redis is down". Each of the three sends an
  operator somewhere different.

The obvious gate for the first one - ``online_deployment`` - is wrong, and
wrong in a way that is invisible from Kubernetes: ``Dockerfile_simple`` bakes
``online_deployment: true`` and ships no Redis, so the workflows run in this
very process, and gating psutil on that flag empties the expander completely.
``Dockerfile`` bakes it too, and ``docker/entrypoint.sh`` starts Redis, the RQ
workers *and* Streamlit in one container, where psutil is once again measuring
exactly the right machine. So the question is answered from the queue - are any
workers registered, and are they all on some other host - not from a flag.

``src/common/common.py`` imports Streamlit at module scope, so it is imported
here with the heavy dependencies mocked at the ``sys.modules`` level and the
originals restored immediately afterwards, mirroring
``tests/test_legal_links.py`` (and, for ``src.workflow``,
``tests/test_topp_flag_parameters.py``). Every other test module - and
``test_gui.py``'s AppTest smoke tests in particular - still gets the real
packages.
"""
import importlib
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)


def _identity_decorator(*args, **kwargs):
    """Stand in for `st.fragment(run_every=5)`, which wraps the monitors."""

    def _wrap(function):
        return function

    return _wrap


mock_streamlit = MagicMock()
mock_streamlit.session_state = {}
# A real function, not a MagicMock attribute: `@st.fragment(...)` applied to a
# MagicMock replaces the decorated function with another MagicMock, and the
# module's monitors would then be uncallable stand-ins rather than the code
# under test.
mock_streamlit.fragment = _identity_decorator

_MOCKED_MODULES = {
    "streamlit": mock_streamlit,
    "streamlit.components": MagicMock(),
    "streamlit.components.v1": MagicMock(),
    "streamlit.source_util": MagicMock(),
    "pandas": MagicMock(),
    "psutil": MagicMock(),
    # Local submodules with their own heavy deps (e.g. the captcha image library).
    "src.common.captcha_": MagicMock(),
    "src.common.admin": MagicMock(),
}
_saved_modules = {name: sys.modules.get(name) for name in _MOCKED_MODULES}
sys.modules.update(_MOCKED_MODULES)

# Force a FRESH import under the mocks, even if an earlier test module (e.g.
# test_gui.py, or tests/test_legal_links.py, which mocks Streamlit differently)
# already imported a version bound to something else.
#
# `import_module`, not `from src.common import common`: the second form is
# satisfied by the *attribute* the import system left on the `src.common`
# package object, which survives popping `sys.modules["src.common.common"]`.
# It would hand back the module another test file imported under its own mock,
# where `st.fragment` is a plain MagicMock - so every monitor here would be a
# MagicMock stand-in, calling them would do nothing, and these tests would pass
# or fail depending on which files ran first.
_package = sys.modules.get("src.common")
_saved_attribute = getattr(_package, "common", None) if _package is not None else None
_saved_common = sys.modules.pop("src.common.common", None)

common = importlib.import_module("src.common.common")  # noqa: E402

for _name, _original in _saved_modules.items():
    if _original is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _original
if _saved_common is None:
    sys.modules.pop("src.common.common", None)
else:
    sys.modules["src.common.common"] = _saved_common
if _package is not None:
    if _saved_attribute is None:
        delattr(_package, "common")
    else:
        setattr(_package, "common", _saved_attribute)


# ---------------------------------------------------------------------------
# Stubbing health
#
# The monitors import `src.workflow.health` inside their own bodies, so the
# stub is installed in `sys.modules` rather than patched onto a module object.
# Several test files purge `src.workflow.*` from `sys.modules` after importing
# under mocks, and pytest imports every test module before running any test -
# so by the time these run, the `health` this file imported at collection time
# may no longer be the one the function-level import resolves to. Patching
# `sys.modules` is immune to that.
# ---------------------------------------------------------------------------
def _stub_health(monkeypatch, **functions):
    stub = types.ModuleType("src.workflow.health")
    for name, value in functions.items():
        setattr(stub, name, value)
    monkeypatch.setitem(sys.modules, "src.workflow.health", stub)
    return stub


@pytest.fixture
def rendered(monkeypatch):
    """Record which panels the expander rendered, without running them."""
    mock_streamlit.reset_mock()
    mock_streamlit.fragment = _identity_decorator
    panels = []
    for name in ("monitor_queue", "monitor_storage", "monitor_hardware"):
        monkeypatch.setattr(
            common, name, (lambda captured: lambda: panels.append(captured))(name)
        )
    return panels


def _deployment(monkeypatch, *, queue: dict, workers_remote: bool):
    _stub_health(
        monkeypatch,
        get_queue_metrics=lambda: queue,
        queue_workers_are_remote=lambda: workers_remote,
    )


# ---------------------------------------------------------------------------
# Which panels apply
# ---------------------------------------------------------------------------
def test_monitor_hardware_hidden_online(monkeypatch, rendered):
    """
    Kubernetes: separate Streamlit and rq-worker pods. psutil here describes a
    process that runs no workflow, so the panel is hidden and the queue and the
    shared volume - what the user's job actually waits on - take its place.
    """
    _deployment(
        monkeypatch,
        queue={"available": True, "total_workers": 2},
        workers_remote=True,
    )

    common.render_resource_utilization()

    assert "monitor_hardware" not in rendered, (
        "the psutil panel describes the Streamlit pod, which does no work; an "
        "idle 2Gi container shown while a 64Gi worker saturates is worse than "
        "showing nothing"
    )
    assert rendered == ["monitor_queue", "monitor_storage"], rendered


def test_monitor_hardware_shown_when_the_workers_share_this_container(
    monkeypatch, rendered
):
    """
    The full image under docker/docker-compose: `docker/entrypoint.sh` runs
    Redis, the RQ workers and Streamlit in one container, so psutil is
    measuring exactly the machine the workflows run on.
    """
    _deployment(
        monkeypatch,
        queue={"available": True, "total_workers": 2},
        workers_remote=False,
    )

    common.render_resource_utilization()

    assert rendered == ["monitor_queue", "monitor_storage", "monitor_hardware"], rendered


def test_the_expander_is_never_empty_without_a_queue(monkeypatch, rendered):
    """
    `Dockerfile_simple` bakes `online_deployment: true`, installs no
    redis-server, and runs the workflows in this process. Gating the psutil
    panel on that flag left the expander rendering an empty body - the queue
    and storage panels draw nothing without a queue, and the one panel that had
    real numbers was the one being suppressed.
    """
    _deployment(monkeypatch, queue={}, workers_remote=False)

    common.render_resource_utilization()

    assert rendered == ["monitor_hardware"], rendered


# ---------------------------------------------------------------------------
# What the storage indicator says
# ---------------------------------------------------------------------------
def _render_storage(monkeypatch, status):
    mock_streamlit.reset_mock()
    mock_streamlit.fragment = _identity_decorator
    _stub_health(
        monkeypatch,
        get_storage_status=status if callable(status) else (lambda: status),
    )
    common.monitor_storage()


def _markdown() -> str:
    return " ".join(
        str(call.args[0]) for call in mock_streamlit.markdown.call_args_list if call.args
    )


def _captions() -> str:
    return " ".join(
        str(call.args[0]) for call in mock_streamlit.caption.call_args_list if call.args
    )


def test_storage_indicator_renders_each_state(monkeypatch):
    """
    Colour is the whole payload here, so it is what gets asserted:

    - green while every node's mount answers,
    - amber naming the node whose mount stopped answering, because a healthy
      node must not cover for a wedged one,
    - red when no node answers at all,
    - grey, never red, when Redis is down: that says nothing about the mount,
      and reporting it as a storage fault sends the operator to the wrong layer.
    """
    _render_storage(
        monkeypatch, {"available": True, "state": "connected", "nodes": ["node-a"]}
    )
    assert ":green[" in _markdown(), _markdown()

    _render_storage(
        monkeypatch,
        {
            "available": True,
            "state": "degraded",
            "nodes": ["node-a"],
            "stale_nodes": ["node-b"],
        },
    )
    degraded = _markdown()
    assert ":green[" not in degraded, (
        "one node's mount is wedged; a green tick is the outage the per node "
        f"heartbeats exist to make visible: {degraded}"
    )
    assert ":orange[" in degraded, degraded
    assert "node-b" in _captions(), (
        "an operator needs to know which node to look at, not just that one "
        f"broke: {_captions()}"
    )

    _render_storage(
        monkeypatch,
        {
            "available": True,
            "state": "unreachable",
            "nodes": [],
            "stale_nodes": ["node-a"],
        },
    )
    assert ":red[" in _markdown(), _markdown()

    _render_storage(monkeypatch, {"available": False, "state": "unknown", "nodes": []})
    unknown = _markdown()
    assert ":red[" not in unknown, (
        f"a dead Redis must not be reported as failed storage: {unknown}"
    )
    assert ":gray[" in unknown, unknown


def test_storage_indicator_renders_nothing_where_nothing_publishes(monkeypatch):
    """
    `{}` is "no shared storage is being reported here", which is every local
    run, every docker-compose run and every apptainer run of the image. A red
    tick there would be a permanent false alarm about a mechanism that is not
    deployed.
    """
    _render_storage(monkeypatch, {})

    assert _markdown() == ""
    assert _captions() == ""


def test_a_broken_storage_indicator_is_not_silent(monkeypatch, caplog):
    """
    The indicator must never break the sidebar, but swallowing the failure
    leaves a broken indicator indistinguishable from a deployment that has no
    shared storage - undetectable in production and in CI alike.
    """

    def _explode():
        raise RuntimeError("redis client blew up")

    with caplog.at_level("ERROR"):
        _render_storage(monkeypatch, _explode)  # must not raise

    assert caplog.records, (
        "the indicator swallowed an exception without logging it, so a broken "
        "indicator is silent in production and invisible in CI"
    )
    assert any(
        "redis client blew up" in str(record.exc_info) or "redis client blew up" in record.getMessage()
        for record in caplog.records
    ), [record.getMessage() for record in caplog.records]
