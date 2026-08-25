"""
Tests for the sidebar storage indicator (Step 2 of the multi-node plan).

Once the workspace volume is a shared NFS mount, its failure mode is a *hang*,
not an error, and nothing in the app detected one: ``health.py`` inspected only
Redis and RQ, ``/_stcore/health`` is filesystem-blind, and RQ's parent process
keeps heartbeating while its work horse is blocked in an NFS syscall.

The design (docs/a16-storage-decisions.md section 8) inverts the check rather than adding one
to the UI::

    rq-worker readiness probe                            sidebar
      SET storage:node:<node>  (a worker lives here)  --> reads Redis only
      touch .nfs-probe --ok--> SET storage:ok:<node>  -->
           \\-- blocks on wedged NFS --> storage:ok expires --> goes red

Redis' TTL *is* the liveness mechanism, so there is no timeout logic to get
wrong, and the sidebar never touches the filesystem: a ``stat`` on a ``hard``
mount blocks in uninterruptible sleep, so a fragment re-running every 5 seconds
would accumulate unkillable threads - the indicator would *become* the hang.

------------------------------------------------------------------------------
Contract these tests pin
------------------------------------------------------------------------------

In ``src/workflow/health.py``, which must stay importable in the RQ worker with
no Streamlit:

* ``STORAGE_HEARTBEAT_PREFIX`` / ``STORAGE_NODE_PREFIX`` / ``STORAGE_SENTINEL_NAME``
  / ``STORAGE_HEARTBEAT_TTL`` - shared constants.
* ``storage_heartbeat_key(node)``, ``storage_node_key(node)`` - per node keys,
  because one healthy node must not mask a wedged one.
* ``probe_storage()`` - what the readiness probe runs, and where the ordering
  lives: register the node, *then* write to the volume, and publish the
  heartbeat only if that write succeeded. Wrapping the volume check in
  ``|| true`` - or publishing before it - reports Ready on a wedged mount, and
  that mutation must not survive.
* ``get_storage_status()`` - the reader, called by the sidebar fragment.
  Extends ``get_queue_metrics()``'s existing ``{}`` vs ``{"available": False}``
  distinction:

  ===============================  =========================================
  ``{}``                           no ``REDIS_URL``, or nothing has ever
                                   published a heartbeat: render nothing
  ``{"available": False, ...}``    Redis is down: state ``"unknown"``
  ``{"available": True, ...}``     state ``"connected"`` / ``"degraded"`` /
                                   ``"unreachable"``, plus ``nodes`` and
                                   ``stale_nodes``
  ===============================  =========================================

  Neither of the extra states is cosmetic. A red tick caused by a dead Redis
  sends an operator to debug storage when the fault is in the queue; a red tick
  in a deployment that has no heartbeat writer at all - every docker-compose
  and apptainer run of the image, which bakes in both ``online_deployment`` and
  a ``REDIS_URL`` - is a permanent false alarm pointing at the wrong layer; and
  a *green* tick while one node's mount is wedged is the outage the per node
  keys exist to make visible.
"""

import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest

fakeredis = pytest.importorskip("fakeredis")
import redis as redis_module  # noqa: E402  (fakeredis guarantees this import)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.workflow import health  # noqa: E402

RQ_WORKER_DEPLOYMENT = REPO_ROOT / "k8s" / "base" / "rq-worker-deployment.yaml"
CLEANUP_CRONJOB = REPO_ROOT / "k8s" / "base" / "cleanup-cronjob.yaml"


class _DeadRedis:
    """A client whose every call fails the way an unreachable Redis does."""

    def __getattr__(self, name):
        def _refused(*args, **kwargs):
            raise redis_module.exceptions.ConnectionError("Connection refused")

        return _refused


def _patch_from_url(monkeypatch, client):
    """Point every `Redis.from_url(...)` in health.py at `client`."""
    monkeypatch.setattr(
        redis_module.Redis,
        "from_url",
        classmethod(lambda cls, *args, **kwargs: client),
        raising=False,
    )
    monkeypatch.setattr(
        redis_module, "from_url", lambda *args, **kwargs: client, raising=False
    )


@pytest.fixture
def fake_redis(monkeypatch):
    client = fakeredis.FakeStrictRedis()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    _patch_from_url(monkeypatch, client)
    return client


def _nodes(status: dict) -> set:
    """The reporting nodes, however the implementation chooses to carry them."""
    return set(status.get("nodes") or [])


def _decode(value):
    return value.decode() if isinstance(value, bytes) else value


def _heartbeat_keys(client) -> set:
    return {
        _decode(key)
        for key in client.keys("*")
        if _decode(key).startswith(health.STORAGE_HEARTBEAT_PREFIX)
    }


def _probe_node(node: str, workspaces_dir) -> bool:
    """Run the readiness probe's own entry point for one node."""
    return health.probe_storage(workspaces_dir=str(workspaces_dir), node=node)


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------
def test_indicator_three_states(fake_redis, monkeypatch, tmp_path):
    """fresh key -> connected; expired key -> unreachable; no Redis -> unknown."""
    monkeypatch.setenv("NODE_NAME", "node-a")
    assert _probe_node("node-a", tmp_path) is True

    status = health.get_storage_status()
    assert status.get("available") is True, status
    assert status.get("state") == "connected", status
    assert _nodes(status) == {"node-a"}, status

    # The key expires because nothing refreshed it - the worker is blocked in
    # an NFS syscall and never got to its SETEX.
    key = health.storage_heartbeat_key("node-a")
    fake_redis.psetex(key, 20, b"1")
    time.sleep(0.1)
    assert fake_redis.exists(key) == 0, "precondition: the heartbeat has expired"

    status = health.get_storage_status()
    assert status.get("available") is True, status
    assert status.get("state") == "unreachable", status
    assert _nodes(status) == set(), status

    # Redis itself is gone. This must NOT read as unreachable storage, or the
    # operator debugs the wrong layer.
    _patch_from_url(monkeypatch, _DeadRedis())

    status = health.get_storage_status()
    assert status.get("available") is False, status
    assert status.get("state") == "unknown", (
        "a dead Redis says nothing about the mount; reporting it as "
        f"'unreachable' sends the operator to the wrong layer: {status}"
    )


def test_a_wedged_node_is_not_masked_by_a_healthy_one(fake_redis, monkeypatch, tmp_path):
    """
    Two nodes, one of them wedged. This is the whole reason the heartbeat is
    keyed per node, and collapsing the keys with `any()` gives it away: the
    indicator would report "connected - 1 node reporting a healthy shared
    volume" and stay green straight through the outage, which is exactly what
    a single shared key would have done.
    """
    assert _probe_node("node-a", tmp_path) is True
    assert _probe_node("node-b", tmp_path) is True
    assert health.get_storage_status().get("state") == "connected"

    # node-b's mount wedges: its readiness probe blocks in the write and never
    # reaches its heartbeat. Its registration keeps being refreshed, because
    # that happens before anything can block.
    fake_redis.delete(health.storage_heartbeat_key("node-b"))
    health.register_storage_node("node-b")

    status = health.get_storage_status()
    assert status.get("state") != "connected", (
        "one node's mount is wedged and the indicator is still green: the per "
        f"node keys are being collapsed rather than compared: {status}"
    )
    assert status.get("state") == "degraded", status
    assert _nodes(status) == {"node-a"}, status
    assert set(status.get("stale_nodes") or []) == {"node-b"}, (
        "the wedged node has to be named, or an operator cannot tell which "
        f"node to look at: {status}"
    )


def test_local_mode_reports_nothing(monkeypatch):
    """No REDIS_URL means local mode; the sidebar renders no indicator at all."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    _patch_from_url(monkeypatch, _DeadRedis())

    assert health.get_storage_status() == {}, (
        "with no REDIS_URL the indicator is not applicable, which is the empty "
        "dict get_queue_metrics() already returns - not an error state"
    )


def test_a_deployment_with_no_heartbeat_writer_reports_nothing(fake_redis):
    """
    A reachable Redis that nobody publishes a heartbeat to is not a storage
    outage - it is a deployment with no shared storage to report on.

    This is not hypothetical: `Dockerfile` bakes in `online_deployment: true`
    *and* `ENV REDIS_URL`, `docker/entrypoint.sh` starts Redis in the same
    container, and the only heartbeat writer in the repo is the Kubernetes
    readiness probe. Reading "no keys" as "unreachable" puts a permanent red
    "running workflows may be stalled" in every docker-compose and apptainer
    deployment of the image, pointing at a layer that does not exist there.
    """
    assert health.get_storage_status() == {}, (
        "nothing has ever published a heartbeat here, so there is nothing to "
        "report; a red tick would be a false alarm about a mechanism that is "
        "not deployed"
    )


def test_indicator_never_touches_filesystem(fake_redis, monkeypatch, tmp_path):
    """
    The sidebar fragment re-runs every 5 seconds. A `stat` on a `hard`-mounted
    wedged path blocks in uninterruptible sleep and cannot be killed, so the
    indicator would become the very hang it exists to report.

    The tripwires below record *and* raise: recording alone would miss a call
    swallowed by a broad `except`, and raising alone would let one be reported
    as an ordinary unavailable status.
    """
    assert _probe_node("node-a", tmp_path) is True
    # Warm up any lazy imports before the filesystem is booby-trapped.
    health.get_storage_status()

    touched = []

    def _tripwire(name):
        def _blocked(*args, **kwargs):
            touched.append((name, args[:1]))
            raise AssertionError(f"the storage indicator called {name}{args[:1]}")

        return _blocked

    targets = (
        "os.stat",
        "os.lstat",
        "os.open",
        "os.listdir",
        "os.scandir",
        "os.access",
        "os.utime",
        "builtins.open",
    )
    with ExitStack() as stack:
        for target in targets:
            stack.enter_context(mock.patch(target, new=_tripwire(target)))
        status = health.get_storage_status()

    assert touched == [], (
        f"the sidebar must reach the mount only through Redis: {touched}"
    )
    assert status.get("state") in {"connected", "degraded", "unreachable", "unknown"}, status


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------
def test_heartbeat_key_is_per_node(fake_redis, monkeypatch, tmp_path):
    """
    Two writers on two nodes produce two keys, each with an expiry. A single
    shared key would let a healthy node keep refreshing it while another node's
    mount is wedged, and expiry is the entire liveness mechanism - a heartbeat
    written without one never goes stale.
    """
    monkeypatch.setenv("NODE_NAME", "node-a")
    health.write_storage_heartbeat()
    monkeypatch.setenv("NODE_NAME", "node-b")
    health.write_storage_heartbeat()

    assert health.storage_heartbeat_key("node-a") == (
        health.STORAGE_HEARTBEAT_PREFIX + "node-a"
    )
    assert _heartbeat_keys(fake_redis) == {
        health.storage_heartbeat_key("node-a"),
        health.storage_heartbeat_key("node-b"),
    }

    for key in _heartbeat_keys(fake_redis):
        ttl = fake_redis.ttl(key)
        assert 0 < ttl <= health.STORAGE_HEARTBEAT_TTL, (
            f"{key} has ttl {ttl}; expiry is the whole liveness mechanism, so a "
            "heartbeat written without one never goes stale"
        )

    assert _nodes(health.get_storage_status()) == {"node-a", "node-b"}


def test_the_probe_publishes_only_after_the_volume_answers(
    fake_redis, monkeypatch, tmp_path
):
    """
    The ordering inside the probe, asserted where a mutation to it cannot hide.

    A probe that publishes the heartbeat regardless - the `|| true` the shell
    version wrapped it in - reports a healthy shared volume while the volume is
    gone, and the indicator goes green through the outage it exists to show.
    """
    monkeypatch.setenv("NODE_NAME", "node-a")
    missing = tmp_path / "not" / "a" / "mount"

    assert health.probe_storage(workspaces_dir=str(missing)) is False, (
        "a volume that will not accept a write must fail the probe; the "
        "readiness verdict is a statement about storage"
    )
    assert fake_redis.exists(health.storage_heartbeat_key("node-a")) == 0, (
        "the probe published a healthy-storage heartbeat for a volume that "
        "rejected the write"
    )
    assert fake_redis.exists(health.storage_node_key("node-a")) == 1, (
        "a node whose mount is wedged must still register, or its missing "
        "heartbeat is indistinguishable from a node that does not exist and "
        "the indicator quietly goes green"
    )
    assert health.get_storage_status().get("state") == "unreachable"

    # The volume comes back.
    assert health.probe_storage(workspaces_dir=str(tmp_path)) is True
    assert (tmp_path / health.STORAGE_SENTINEL_NAME).exists(), (
        "the probe must *write*: with the default actimeo a stat can be "
        "answered from the client's attribute cache while the server is gone"
    )
    assert health.get_storage_status().get("state") == "connected"


def test_the_probe_survives_a_dead_redis(monkeypatch, tmp_path):
    """
    A Redis that is down says nothing about the mount, so it must not fail the
    readiness probe: the worker would be marked NotReady for a fault in another
    component entirely.
    """
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("NODE_NAME", "node-a")
    _patch_from_url(monkeypatch, _DeadRedis())

    assert health.probe_storage(workspaces_dir=str(tmp_path)) is True
    assert (tmp_path / health.STORAGE_SENTINEL_NAME).exists()


def test_heartbeat_writer_needs_no_streamlit(tmp_path):
    """
    The writer runs in the RQ worker, which has no Streamlit session and must
    stay importable without the package - the same constraint tasks.py carries.

    The functions are *called*, not merely looked up: an `import streamlit`
    inside a function body would sail past a `hasattr` check and only fail in
    the worker, at the one moment nobody is watching.
    """
    code = textwrap.dedent(
        """
        import json
        import sys

        sys.modules["streamlit"] = None  # any `import streamlit` now raises

        from src.workflow import health

        for name in (
            "STORAGE_HEARTBEAT_PREFIX",
            "STORAGE_NODE_PREFIX",
            "STORAGE_HEARTBEAT_TTL",
            "STORAGE_SENTINEL_NAME",
            "storage_heartbeat_key",
            "storage_node_key",
            "write_storage_heartbeat",
            "register_storage_node",
            "probe_storage",
            "get_storage_status",
        ):
            assert hasattr(health, name), "health." + name + " is missing"

        # Redis is deliberately unreachable: publishing must degrade to False,
        # never raise, and never fail the probe on the mount's behalf.
        assert health.probe_storage(workspaces_dir=sys.argv[1]) is True
        assert health.write_storage_heartbeat(node="node-a") is False
        assert health.register_storage_node(node="node-a") is False
        assert health.storage_heartbeat_key("n") == health.STORAGE_HEARTBEAT_PREFIX + "n"
        assert json.dumps(health.get_storage_status()) is not None
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=dict(
            os.environ,
            PYTHONPATH=str(REPO_ROOT),
            # Port 1 is reserved and never listening: connection refused,
            # immediately, with no dependency on the network.
            REDIS_URL="redis://127.0.0.1:1/0",
        ),
    )
    assert result.returncode == 0, (
        "src/workflow/health.py must expose *and run* the storage heartbeat API "
        f"without importing Streamlit.\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert (tmp_path / health.STORAGE_SENTINEL_NAME).exists()


# ---------------------------------------------------------------------------
# Bounding
#
# The sidebar re-runs its fragments every 5 seconds on the session's own
# ScriptRunner thread, so an unbounded Redis call does not degrade an
# indicator - it freezes the session. Bounding only the storage reader closes
# half the hang: `get_queue_metrics()` drives the fragment rendered directly
# above it, on the same cadence and the same thread.
# ---------------------------------------------------------------------------
REDIS_READERS = (
    "check_redis_health",
    "check_worker_health",
    "get_queue_metrics",
    "get_storage_status",
    "queue_workers_are_remote",
)


@pytest.mark.parametrize("call", REDIS_READERS)
def test_every_redis_call_is_bounded(monkeypatch, call):
    """
    Every client this module builds carries both timeouts.

    Asserted on the construction rather than on the clock, because redis-py's
    own defaults have moved over the versions this repo floats across
    (`redis>=5.0.0`, unpinned): on one of them an "unbounded" call happens to
    fail after five seconds and a stopwatch cannot tell the two apart.
    """
    built = []

    def _record(*args, **kwargs):
        built.append(kwargs)
        return _DeadRedis()

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(
        redis_module.Redis,
        "from_url",
        classmethod(lambda cls, *args, **kwargs: _record(*args, **kwargs)),
        raising=False,
    )

    getattr(health, call)()

    assert built, f"health.{call}() never built a Redis client"
    for kwargs in built:
        assert kwargs.get("socket_connect_timeout") == health.REDIS_SOCKET_TIMEOUT, (
            f"health.{call}() connects without a bound: {kwargs}"
        )
        assert kwargs.get("socket_timeout") == health.REDIS_SOCKET_TIMEOUT, (
            f"health.{call}() reads without a bound, so a Redis that accepts "
            f"the connection and then never answers hangs the caller: {kwargs}"
        )


def test_a_redis_that_never_answers_does_not_hang_the_sidebar(monkeypatch):
    """
    The same property end to end, against a socket that completes the TCP
    handshake and then says nothing - a Redis behind a partition, a wedged
    host, a dropped conntrack entry. A connect timeout alone does not cover it:
    the connect succeeds and the read blocks. Nothing accepts the connection
    here; the kernel's backlog completes the handshake on its own.
    """
    import socket as socket_module
    import threading

    server = socket_module.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    monkeypatch.setenv("REDIS_URL", f"redis://127.0.0.1:{server.getsockname()[1]}/0")

    finished = threading.Event()

    def _call():
        try:
            health.get_queue_metrics()
        finally:
            finished.set()

    worker = threading.Thread(target=_call, daemon=True)
    started = time.monotonic()
    worker.start()
    try:
        completed = finished.wait(timeout=30)
    finally:
        server.close()
    elapsed = time.monotonic() - started

    assert completed, (
        "get_queue_metrics() never returned against a Redis that accepts the "
        "connection and then never answers; called from a sidebar fragment "
        f"that is the whole session frozen (waited {elapsed:.0f}s)"
    )


# ---------------------------------------------------------------------------
# Where the psutil panel applies
# ---------------------------------------------------------------------------
def _register_worker(client, hostname: str, name: str) -> None:
    from rq import Worker

    worker = Worker(["openms-workflows"], connection=client, name=name)
    worker.hostname = hostname
    worker.register_birth()


def test_workers_in_this_container_are_not_remote(fake_redis):
    """
    The full image runs Redis, the RQ workers and Streamlit in one container
    (`docker/entrypoint.sh`), so psutil in the Streamlit process measures
    exactly the machine the workflows run on. Hiding the panel there - which
    gating it on `online_deployment` did, because the image bakes that flag
    true - leaves the "Resource Utilization" expander with nothing in it.
    """
    import socket

    _register_worker(fake_redis, socket.gethostname(), "worker-1")

    assert health.queue_workers_are_remote() is False


def test_workers_in_other_pods_are_remote(fake_redis):
    """
    In Kubernetes the workers are separate pods, usually on separate nodes, so
    psutil here describes an idle 2Gi Streamlit pod while a 64Gi worker
    saturates.
    """
    _register_worker(fake_redis, "template-app-rq-worker-7c9f-abcde", "worker-1")
    _register_worker(fake_redis, "template-app-rq-worker-7c9f-fghij", "worker-2")

    assert health.queue_workers_are_remote() is True


def test_an_unreachable_queue_is_not_proof_of_remote_workers(monkeypatch):
    """
    `Dockerfile_simple` has no Redis at all, and the apptainer branch of the
    entrypoint exports `REDIS_URL` before checking whether redis-server exists.
    Neither says the workflows run elsewhere - they run in this process - so
    the panel stays.
    """
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    _patch_from_url(monkeypatch, _DeadRedis())
    assert health.queue_workers_are_remote() is False

    monkeypatch.delenv("REDIS_URL", raising=False)
    assert health.queue_workers_are_remote() is False


# ---------------------------------------------------------------------------
# The manifests
#
# The probe is a shell command in YAML, so it is extracted and *run* rather
# than grepped: a substring check for "readinessProbe" survives replacing the
# storage check's `|| exit 1` with `|| true`, which reports Ready on a wedged
# mount and is the entire failure the probe exists to catch.
# ---------------------------------------------------------------------------
def _readiness_probe_script() -> str:
    """The shell body of rq-worker's readiness probe, dedented."""
    manifest = RQ_WORKER_DEPLOYMENT.read_text(encoding="utf-8")
    assert "readinessProbe:" in manifest, (
        "rq-worker has no readiness probe, so a wedged mount is invisible: the "
        "RQ parent keeps heartbeating while its work horse is blocked"
    )
    block = manifest[manifest.index("readinessProbe:"):]
    marker = "- |\n"
    assert marker in block, "the probe's command is not a literal block scalar"
    lines = block[block.index(marker) + len(marker):].splitlines()
    indent = len(lines[0]) - len(lines[0].lstrip())
    body = []
    for line in lines:
        if line.strip() and (len(line) - len(line.lstrip())) < indent:
            break
        body.append(line[indent:])
    return "\n".join(body).rstrip() + "\n"


def _require_probe_prerequisites() -> str:
    """The bash that can run the probe, or a skip."""
    bash = _bash()
    if bash is None:
        pytest.skip("no bash to run the readiness probe with")
    probe = subprocess.run(
        [bash, "-c", "command -v timeout"], capture_output=True, text=True, check=False
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        pytest.skip("no `timeout` for the probe to bound itself with")
    return bash


def _bash():
    found = shutil.which("bash")
    if found:
        return found
    for candidate in (
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path("C:/Program Files/Git/usr/bin/bash.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _posix(path) -> str:
    text = Path(path).as_posix()
    if os.name == "nt" and len(text) > 1 and text[1] == ":":
        text = "/" + text[0].lower() + text[2:]
    return text


def _run_readiness_probe(workspaces_dir) -> subprocess.CompletedProcess:
    """
    Run the manifest's probe command, with only the container's interpreter
    path swapped for this one. Everything else - the `timeout`, the module it
    invokes, the exit status handling - is the shipped text.
    """
    bash = _require_probe_prerequisites()
    script = _readiness_probe_script()
    script, count = re.subn(
        r"(?m)^py=.*$", "py=" + _posix(sys.executable), script, count=1
    )
    assert count == 1, (
        "the probe no longer names its interpreter on a `py=` line; update "
        f"this substitution:\n{script}"
    )
    return subprocess.run(
        [bash, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=dict(
            os.environ,
            PYTHONPATH=str(REPO_ROOT),
            WORKSPACES_DIR=str(workspaces_dir),
            # Unreachable on purpose: the probe's verdict is about storage, and
            # a dead Redis must not change it in either direction.
            REDIS_URL="redis://127.0.0.1:1/0",
            NODE_NAME="node-a",
        ),
        timeout=120,
    )


def test_readiness_probe_passes_on_a_volume_that_accepts_a_write(tmp_path):
    result = _run_readiness_probe(tmp_path)

    assert result.returncode == 0, (
        f"the probe failed on a healthy volume.\nstdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert (tmp_path / health.STORAGE_SENTINEL_NAME).exists(), (
        "the probe did not write the sentinel; `stat` alone can be answered "
        "from the client's attribute cache while the server is gone"
    )


def test_readiness_probe_fails_when_the_volume_rejects_a_write(tmp_path):
    """
    The mutation that matters: replacing the storage check's `|| exit 1` with
    `|| true` leaves every assertion about the probe's *shape* green while the
    probe reports Ready on a wedged mount and publishes a heartbeat with it.
    """
    result = _run_readiness_probe(tmp_path / "not" / "a" / "mount")

    assert result.returncode != 0, (
        "the probe reported Ready for a volume that would not accept a write.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_readiness_probe_has_no_escape_hatch():
    """
    Nothing in the probe may swallow a failure. Kept alongside the behavioural
    tests above because `|| true` is how this gets broken - it looks like
    defensive shell and it silently inverts the verdict.
    """
    script = _readiness_probe_script()

    assert "src.workflow.health" in script, (
        "the probe must run the module that owns the sentinel name and the "
        f"ordering, not a second copy of the logic in YAML:\n{script}"
    )
    assert "--probe" in script, f"the probe must run `--probe`:\n{script}"
    assert "|| true" not in script, (
        "a `|| true` in the readiness probe reports Ready on a wedged mount, "
        f"which is the whole failure it exists to catch:\n{script}"
    )
    assert "exit 0" not in script, (
        "an unconditional `exit 0` has the same effect as `|| true`:\n" + script
    )


def test_readiness_probe_uses_the_containers_own_interpreter():
    """
    The probe names an interpreter path outright instead of activating the
    environment, because `conda activate` costs a few hundred milliseconds of
    shell hooks on every probe. That buys a hardcoded path, which drifts
    silently: rename the env or move the conda root and every probe fails with
    "No such file or directory", the workers go NotReady, and the sidebar goes
    red - all for a rename nothing pointed at this file.
    """
    manifest = RQ_WORKER_DEPLOYMENT.read_text(encoding="utf-8")

    activate = re.search(r"source\s+(\S+)/bin/activate\s+(\S+)", manifest)
    assert activate, (
        "the rq-worker container no longer activates a conda environment; the "
        "probe's interpreter path has nothing left to agree with"
    )
    conda_root, environment = activate.group(1), activate.group(2)

    interpreter = re.search(r"(?m)^py=(\S+)$", _readiness_probe_script())
    assert interpreter, "the probe does not name its interpreter on a `py=` line"
    assert interpreter.group(1) == f"{conda_root}/envs/{environment}/bin/python", (
        f"the probe runs {interpreter.group(1)}, but the container itself runs "
        f"in {environment} under {conda_root}"
    )


def test_worker_gets_its_node_name_from_the_downward_api():
    """
    Without `NODE_NAME`, `current_node_name()` falls back to the hostname -
    the *pod* name in Kubernetes, which changes on every restart. The
    heartbeat would then be keyed per pod, the registry would fill with dead
    pod names, and the per node visibility the design turns on would be gone.
    """
    manifest = RQ_WORKER_DEPLOYMENT.read_text(encoding="utf-8")
    downward = re.search(
        r"-\s+name:\s+NODE_NAME\s+valueFrom:\s+fieldRef:\s+fieldPath:\s+(\S+)",
        manifest,
    )
    assert downward, (
        "rq-worker does not take NODE_NAME from the Downward API:\n" + manifest
    )
    assert downward.group(1) == "spec.nodeName", (
        f"NODE_NAME reads {downward.group(1)}, not the node's name"
    )


def test_worker_has_no_liveness_probe():
    manifest = RQ_WORKER_DEPLOYMENT.read_text(encoding="utf-8")

    assert "livenessProbe" not in manifest, (
        "never a liveness probe on rq-worker: it would kill in-flight TOPP jobs, "
        "and restarting cannot fix NFS"
    )


def test_probe_timing_outlasts_the_nfs_grace_period():
    """
    A Ganesha restart imposes a ~90s NFSv4 grace period during which all I/O
    blocks. Probe timing has to outlast it, or every routine restart flaps the
    worker - and the sidebar must go red *before* the worker is marked
    NotReady, so degradation is visible before it is fatal.
    """
    manifest = RQ_WORKER_DEPLOYMENT.read_text(encoding="utf-8")

    def _value(field: str) -> int:
        match = re.search(rf"(?m)^\s+{field}:\s+(\d+)\s*$", manifest)
        assert match, f"the readiness probe declares no {field}"
        return int(match.group(1))

    period = _value("periodSeconds")
    threshold = _value("failureThreshold")
    kubelet_timeout = _value("timeoutSeconds")

    to_not_ready = (threshold - 1) * period + kubelet_timeout
    assert to_not_ready > 90, (
        f"{to_not_ready}s of failure before NotReady does not outlast the ~90s "
        "NFSv4 grace period; every Ganesha restart would flap the worker"
    )
    assert health.STORAGE_HEARTBEAT_TTL >= 2 * period, (
        f"a heartbeat TTL of {health.STORAGE_HEARTBEAT_TTL}s against a "
        f"{period}s probe period turns the indicator red on a single slow "
        "probe, while the mount is healthy"
    )
    assert health.STORAGE_HEARTBEAT_TTL < to_not_ready, (
        "the indicator must go red before the worker is marked NotReady: "
        "degradation should be visible before it is fatal"
    )

    inner = re.search(r"timeout\s+-k\s+\d+\s+(\d+)", _readiness_probe_script())
    assert inner, "the probe does not bound itself with `timeout`"
    assert int(inner.group(1)) < kubelet_timeout, (
        f"the probe's own bound ({inner.group(1)}s) is not inside kubelet's "
        f"({kubelet_timeout}s), so a slow-but-alive mount never produces a "
        "clean exit status"
    )


def test_cleanup_cronjob_cannot_wedge_forever():
    """
    `concurrencyPolicy: Forbid` means one Active Job suppresses every later
    schedule, so a run hung on the shared mount silently ends nightly cleanup
    forever.

    Both bounds are required. `activeDeadlineSeconds` is a control-plane bound
    applied to a syscall-level hang: a pod in D-state cannot terminate, and on
    recent Kubernetes the Job's terminal Failed condition is only added once
    every pod has terminated, so Forbid can still suppress the next schedule.
    The in-container `timeout` closes the reachable-but-slow cases without
    depending on the cluster version.
    """
    manifest = CLEANUP_CRONJOB.read_text(encoding="utf-8")

    assert "concurrencyPolicy: Forbid" in manifest, (
        "this test is about what Forbid does to a hung run; if the policy "
        "changed, revisit both bounds below"
    )
    deadline = re.search(r"(?m)^\s+activeDeadlineSeconds:\s+(\d+)\s*$", manifest)
    assert deadline, (
        "the cleanup CronJob has no activeDeadlineSeconds, so one run wedged "
        "on the workspaces mount blocks every subsequent night"
    )

    inner = re.search(r"timeout\s+-k\s+\d+\s+(\d+)\s", manifest)
    assert inner, (
        "the cleanup command is not wrapped in `timeout`; activeDeadlineSeconds "
        "alone leaves the container itself unbounded"
    )
    assert int(inner.group(1)) < int(deadline.group(1)), (
        f"the in-container bound ({inner.group(1)}s) must fire before the Job "
        f"deadline ({deadline.group(1)}s), or it never fires at all"
    )
