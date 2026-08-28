"""
Health check utilities for Redis queue and shared storage monitoring.

Provides functions to check Redis and worker health status for display in the
sidebar metrics, plus the shared storage heartbeat: `probe_storage()` runs on
the node that holds the mount (from the rq-worker readiness probe),
`get_storage_status()` is what the sidebar fragment renders.

Three constraints hold for everything in this module:

* **No Streamlit.** The heartbeat writer runs next to the RQ worker, which has
  no ScriptRunContext - the same constraint `tasks.py` carries.
* **The readers never touch the filesystem.** A `stat` on a `hard` NFS mount
  that has wedged blocks in uninterruptible sleep and cannot be killed, so a
  sidebar fragment re-running every 5 seconds would accumulate unkillable
  threads: the indicator would become the very hang it exists to report. The
  mount is touched only by `probe_storage()`, which runs from the readiness
  probe under a shell `timeout`, in a process nobody waits on.
* **Every Redis call is bounded.** All of them go through `_redis_client()`,
  which sets a connect and a socket timeout. An unbounded call is reachable
  from the sidebar - `get_queue_metrics()` drives a fragment on the session's
  ScriptRunner thread - so a Redis that is black-holing packets would otherwise
  freeze the session rather than show it as unavailable.
"""

import logging
import os
import socket
import sys
import time

logger = logging.getLogger(__name__)

# Shared storage heartbeat: an inverted health check.
#
#   rq-worker readiness probe                            sidebar
#     SET storage:node:<node>  (a worker lives here)  --> reads Redis only
#     touch .nfs-probe --ok--> SET storage:ok:<node>  -->
#          \-- blocks on a wedged mount --> storage:ok expires --> goes red
#
# Redis' TTL *is* the liveness mechanism, so there is no timeout logic here to
# get wrong, and nothing in the Streamlit process ever calls into the mount.
#
# Two keys, not one, and the order between them is the whole design:
#
#   storage:node:<node>  published *before* the mount is touched, so it keeps
#                        being refreshed by a node whose mount has wedged. This
#                        is the expected-node baseline. Without it "no key" and
#                        "no such node" are indistinguishable, and a healthy
#                        node silently covers for a wedged one.
#   storage:ok:<node>    published *after* the mount answered. Its absence
#                        against a present storage:node:<node> is exactly the
#                        signal the indicator exists to show.
#
# STORAGE_SENTINEL_NAME is named here and nowhere else. The readiness probe in
# k8s/base/rq-worker-deployment.yaml runs `--probe` rather than spelling the
# path out in YAML, precisely so there is no second copy to drift from this
# one - drift would show up as a permanently red indicator, not as a lint
# error. tests/test_storage_health.py runs the probe's command to keep that
# delegation honest.
STORAGE_SENTINEL_NAME = ".nfs-probe"
STORAGE_HEARTBEAT_PREFIX = "storage:ok:"
STORAGE_NODE_PREFIX = "storage:node:"
# Four times the readiness probe's periodSeconds (30s): three refreshes may be
# missed before the indicator goes red, which keeps a slow probe - a cold
# interpreter on a CPU-saturated worker, a DNS hiccup on the way to Redis -
# from turning it red while the mount is healthy. It still goes red before the
# probe's failureThreshold marks the worker NotReady (4 x 30s plus a 20s
# timeout, ~140s): degradation should be visible before it is fatal. Keep the
# two in step - a TTL below periodSeconds makes the indicator flicker red
# between healthy probes.
STORAGE_HEARTBEAT_TTL = 120
# Ten probe periods. A node stops being *expected* five minutes after its
# worker stopped probing at all - a drain, a scale-down, a deleted node - so a
# node that legitimately went away does not leave the indicator permanently
# degraded. A wedged mount does not clear it: the registration is written
# before the mount is touched, so a wedged node keeps re-registering and stays
# visible for as long as its worker is alive.
STORAGE_NODE_TTL = 300

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_WORKSPACES_DIR = "/workspaces-streamlit-template"
# Every Redis call made from the Streamlit process is bounded: the sidebar
# fragment re-runs every 5 seconds and must not sit in a connect() to a Redis
# that is black-holing packets.
REDIS_SOCKET_TIMEOUT = 2


def _redis_client(redis_url: str):
    """Connect to Redis with every socket operation bounded."""
    from redis import Redis

    return Redis.from_url(
        redis_url,
        socket_connect_timeout=REDIS_SOCKET_TIMEOUT,
        socket_timeout=REDIS_SOCKET_TIMEOUT,
    )


def check_redis_health() -> dict:
    """
    Check Redis connection health.

    Returns:
        Dictionary with health status and metrics
    """
    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)

    try:
        redis = _redis_client(redis_url)
        redis.ping()
        info = redis.info()

        return {
            "status": "healthy",
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "unknown"),
            "uptime_days": info.get("uptime_in_days", 0),
        }
    except ImportError:
        return {
            "status": "unavailable",
            "error": "redis package not installed",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


def check_worker_health() -> dict:
    """
    Check RQ worker health.

    Returns:
        Dictionary with worker status and metrics
    """
    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)

    try:
        from rq import Worker, Queue

        redis = _redis_client(redis_url)
        queue = Queue("openms-workflows", connection=redis)
        workers = Worker.all(connection=redis)

        busy_workers = [w for w in workers if w.get_state() == "busy"]
        idle_workers = [w for w in workers if w.get_state() == "idle"]

        return {
            "status": "healthy",
            "worker_count": len(workers),
            "busy_workers": len(busy_workers),
            "idle_workers": len(idle_workers),
            "queue_length": len(queue),
            "workers": [
                {
                    "name": w.name,
                    "state": w.get_state(),
                    "current_job": w.get_current_job_id(),
                }
                for w in workers
            ]
        }
    except ImportError:
        return {
            "status": "unavailable",
            "error": "rq package not installed",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


def get_queue_metrics() -> dict:
    """
    Get comprehensive queue metrics for sidebar display.

    Returns:
        Dictionary with all queue metrics or empty dict if unavailable
    """
    # Only attempt if REDIS_URL is set (online mode)
    if not os.environ.get("REDIS_URL"):
        return {}

    try:
        from rq import Worker, Queue

        redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)
        redis = _redis_client(redis_url)

        # Test connection
        redis.ping()

        queue = Queue("openms-workflows", connection=redis)
        workers = Worker.all(connection=redis)

        busy_count = len([w for w in workers if w.get_state() == "busy"])

        return {
            "available": True,
            "total_workers": len(workers),
            "busy_workers": busy_count,
            "idle_workers": len(workers) - busy_count,
            "queued_jobs": len(queue),
            "started_jobs": len(queue.started_job_registry),
            "finished_jobs": len(queue.finished_job_registry),
            "failed_jobs": len(queue.failed_job_registry),
        }
    except Exception:
        return {"available": False}


def _as_text(value) -> str:
    """Redis hands back bytes or str depending on the client's decoding."""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return "" if value is None else str(value)


def queue_workers_are_remote() -> bool:
    """
    Whether the workflows run on a machine other than this one.

    The sidebar's psutil panel measures *this* process. Whether that is the
    right machine depends on the deployment, not on `online_deployment`:

    - Kubernetes: Streamlit and rq-worker are separate pods, usually on
      separate nodes. psutil here would show an idle 2Gi pod while a 64Gi
      worker saturates, so the panel is hidden.
    - The full Docker image (and docker-compose): `docker/entrypoint.sh` starts
      Redis, the RQ workers *and* Streamlit in one container, so psutil is
      measuring exactly the machine that runs the workflows. The panel stays.
    - `Dockerfile_simple`: no Redis at all, workflows run in-process. The panel
      stays - it is the only thing that expander has to show.

    RQ records each worker's hostname at birth, so the question answers itself
    from data the queue already holds. Uncertainty resolves to False: a
    possibly-wrong number beats an empty panel, and every failure here (no
    Redis, no RQ, an unreachable queue, no workers registered) means nothing
    has *proved* the workers are elsewhere.

    Returns:
        bool: True only when the queue is reachable, workers are registered,
            and none of them runs on this host.
    """
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return False

    try:
        from rq import Worker

        client = _redis_client(redis_url)
        client.ping()
        hostnames = {
            _as_text(getattr(worker, "hostname", "")) for worker in Worker.all(connection=client)
        }
        hostnames.discard("")
    except Exception:
        return False

    return bool(hostnames) and socket.gethostname() not in hostnames


def storage_heartbeat_key(node: str) -> str:
    """
    Redis key carrying one node's storage heartbeat: its mount answered.

    Keyed per node, never a single shared key: with one key a healthy node
    would keep refreshing it while another node's mount is wedged, and the
    indicator would stay green straight through a real outage. The per node
    keys only deliver that if something also says which nodes are *expected* -
    see `storage_node_key()`.

    Args:
        node: Node name, as the Downward API reports `spec.nodeName`.

    Returns:
        str: The Redis key for that node.
    """
    return f"{STORAGE_HEARTBEAT_PREFIX}{node}"


def storage_node_key(node: str) -> str:
    """
    Redis key registering that a worker lives on this node.

    The expected-node baseline. It is written before the mount is touched, so
    it survives a wedged mount and makes that node's missing heartbeat visible
    instead of merely absent. It expires (`STORAGE_NODE_TTL`) so a node that
    was drained stops being expected.

    Args:
        node: Node name, as the Downward API reports `spec.nodeName`.

    Returns:
        str: The Redis key for that node.
    """
    return f"{STORAGE_NODE_PREFIX}{node}"


def current_node_name() -> str:
    """
    Name of the node this process runs on.

    `NODE_NAME` is injected from the Downward API (`spec.nodeName`) in
    k8s/base/rq-worker-deployment.yaml. Outside Kubernetes - docker-compose, a
    local run - the container hostname is the closest analogue and keeps the
    key per writer rather than shared.

    Returns:
        str: The node name.
    """
    return os.environ.get("NODE_NAME") or socket.gethostname()


def register_storage_node(node: str = "", ttl: int = STORAGE_NODE_TTL) -> bool:
    """
    Register that a worker is running on this node.

    Deliberately says nothing about the mount, and is therefore called *before*
    the mount is touched: a node whose mount has wedged must keep answering
    "I exist" so that its missing heartbeat reads as a fault rather than as an
    absent node.

    Never raises: a Redis that is down says nothing about the mount, and the
    caller's exit code is a statement about storage.

    Args:
        node: Node name to register. Defaults to `current_node_name()`.
        ttl: Seconds the registration stays valid.

    Returns:
        bool: True if the registration was published.
    """
    node = node or current_node_name()
    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)

    try:
        client = _redis_client(redis_url)
        client.set(storage_node_key(node), str(int(time.time())), ex=int(ttl))
        return True
    except Exception as e:
        logger.warning("Could not register the storage node %s: %s", node, e)
        return False


def touch_storage_sentinel(workspaces_dir: str = "") -> bool:
    """
    Write to the shared volume, the way the readiness probe means it.

    A write, not a `stat`: with the default `actimeo` a stat can be answered
    from the client's attribute cache while the server is gone, which is a
    false green. `utime` is a metadata write, so it always reaches the server,
    and creating the file first means a fresh volume passes instead of failing
    forever on a file nothing else makes. The sentinel is dot-named and is not
    a directory, so clean-up-workspaces.py skips it twice over.

    This is the one function in this module that touches the filesystem, and it
    is only ever called from `probe_storage()` in the worker's readiness probe:
    on a `hard` mount this call can block in uninterruptible sleep, which is
    survivable only in a process nobody waits on and a shell `timeout` is
    holding the stopwatch for.

    Args:
        workspaces_dir: Directory holding the sentinel. Defaults to
            `$WORKSPACES_DIR`, then `DEFAULT_WORKSPACES_DIR`.

    Returns:
        bool: True if the volume accepted the write.
    """
    directory = (
        workspaces_dir
        or os.environ.get("WORKSPACES_DIR")
        or DEFAULT_WORKSPACES_DIR
    )
    sentinel = os.path.join(directory, STORAGE_SENTINEL_NAME)

    try:
        # Append mode: create if missing, never truncate. The open alone can be
        # served from the client's cache, which is why utime follows.
        with open(sentinel, "ab"):
            pass
        os.utime(sentinel, None)
        return True
    except Exception as e:
        logger.warning("The shared volume did not accept a write at %s: %s", sentinel, e)
        return False


def write_storage_heartbeat(node: str = "", ttl: int = STORAGE_HEARTBEAT_TTL) -> bool:
    """
    Publish this node's storage heartbeat: its mount answered just now.

    **Verifies nothing.** Call `probe_storage()` unless the mount has already
    been confirmed in this same process - this function on its own publishes a
    green light for a volume it never touched. It is separate so that the
    blocking half lives in `touch_storage_sentinel()`, in a process that may
    block forever and be abandoned, which the Redis write must not be.

    Expiry is the whole mechanism - a heartbeat is a claim with a deadline, not
    a flag somebody has to remember to clear. The node registration is
    refreshed alongside it, in one round trip, so a heartbeat always implies an
    expected node.

    Never raises: a Redis that is down says nothing about the mount, and the
    caller's exit code is a statement about storage.

    Args:
        node: Node name to key the heartbeat under. Defaults to
            `current_node_name()`.
        ttl: Seconds the heartbeat stays valid.

    Returns:
        bool: True if the heartbeat was published.
    """
    node = node or current_node_name()
    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)

    try:
        client = _redis_client(redis_url)
        # SET ... EX rather than SETEX: same single atomic write-with-deadline,
        # without the command Redis deprecated in 2.6.12. Pipelined so the two
        # keys cost one round trip, not two.
        stamp = str(int(time.time()))
        pipeline = client.pipeline()
        pipeline.set(storage_heartbeat_key(node), stamp, ex=int(ttl))
        pipeline.set(storage_node_key(node), stamp, ex=int(STORAGE_NODE_TTL))
        pipeline.execute()
        return True
    except Exception as e:
        # Not an error worth failing a probe over, but an operator chasing a red
        # indicator against a healthy mount needs to find this line.
        logger.warning("Could not publish the storage heartbeat for %s: %s", node, e)
        return False


def probe_storage(workspaces_dir: str = "", node: str = "") -> bool:
    """
    The rq-worker readiness probe, in one process.

    Ordering is the contract, and it is load-bearing in both directions:

    1. `register_storage_node()` - unconditional, before anything can block, so
       a node with a wedged mount still counts as expected.
    2. `touch_storage_sentinel()` - the only call that can block. If it fails
       or never returns, the probe fails and no heartbeat is published.
    3. `write_storage_heartbeat()` - reached only from a mount that answered.

    Publishing is best effort in both directions: a Redis that is down says
    nothing about the mount, so it must not fail the probe, and a mount that
    did not answer must not publish regardless of how healthy Redis is.

    Args:
        workspaces_dir: Directory holding the sentinel. Defaults to
            `$WORKSPACES_DIR`.
        node: Node name. Defaults to `current_node_name()`.

    Returns:
        bool: True if the shared volume accepted a write.
    """
    node = node or current_node_name()

    register_storage_node(node)
    if not touch_storage_sentinel(workspaces_dir):
        return False
    write_storage_heartbeat(node)
    return True


def get_storage_status() -> dict:
    """
    Read the shared storage heartbeats for the sidebar indicator.

    Reads Redis and nothing else. Never stat the mount from here: on a `hard`
    mount that call blocks in uninterruptible sleep and the indicator becomes
    the hang it is supposed to report.

    Follows `get_queue_metrics()`'s distinction between "not applicable" and
    "cannot tell":

    - `{}` - no `REDIS_URL`, or a Redis nothing has ever published a heartbeat
      to. Both mean there is no shared storage being reported here and the
      sidebar renders nothing. The second case is what keeps every non
      Kubernetes deployment of the image quiet: `Dockerfile` bakes in both
      `online_deployment` and a `REDIS_URL`, but the readiness probe that
      writes the heartbeat exists only in `k8s/`, and a permanent red tick on
      docker-compose would be exactly the wrong-layer alarm this indicator was
      built to avoid.
    - `{"available": False, "state": "unknown", ...}` - Redis is down, which
      says nothing about the mount. Reporting that as unreachable storage sends
      an operator to debug the wrong layer.
    - `{"available": True, "state": "connected"}` - every expected node's mount
      answered within its TTL.
    - `{"available": True, "state": "degraded"}` - some did and some did not.
      This is the case per node keys exist for: with one shared key, or by
      collapsing the keys with `any()`, a healthy node would cover for a node
      whose mount is wedged and the indicator would stay green through a real
      outage.
    - `{"available": True, "state": "unreachable"}` - no expected node's mount
      answered.

    Returns:
        dict: Empty when not applicable, otherwise `available`, `state`,
            `nodes` (reporting a healthy mount), `stale_nodes` (expected but
            silent) and, when Redis is down, `error`.
    """
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return {}

    try:
        client = _redis_client(redis_url)

        # Test connection
        client.ping()

        # SCAN, not KEYS: KEYS blocks the whole server for the length of the
        # keyspace, and this runs from a sidebar fragment every 5 seconds.
        healthy = _scan_suffixes(client, STORAGE_HEARTBEAT_PREFIX)
        expected = _scan_suffixes(client, STORAGE_NODE_PREFIX)
    except Exception as e:
        return {
            "available": False,
            "state": "unknown",
            "nodes": [],
            "stale_nodes": [],
            "error": str(e),
        }

    # A heartbeat implies an expected node even if the registration expired
    # first (a much longer TTL, so only reachable if Redis lost the key).
    expected |= healthy
    if not expected:
        return {}

    stale = expected - healthy
    if not healthy:
        state = "unreachable"
    elif stale:
        state = "degraded"
    else:
        state = "connected"

    return {
        "available": True,
        "state": state,
        "nodes": sorted(healthy),
        "stale_nodes": sorted(stale),
    }


def _scan_suffixes(client, prefix: str) -> set:
    """Every key under `prefix`, with the prefix stripped off."""
    found = set()
    for key in client.scan_iter(match=f"{prefix}*", count=100):
        found.add(_as_text(key)[len(prefix):])
    found.discard("")
    return found


def _cli(argv=None) -> int:
    """
    Command line entry point, used by the rq-worker readiness probe.

    `--probe` is the probe itself: register the node, write to the shared
    volume, and publish the heartbeat only if that write succeeded. `--status`
    is for a human with a shell (`kubectl exec ... -- python -m
    src.workflow.health --status`).

    There is deliberately no flag that publishes a heartbeat without checking
    the mount. It would look like the obvious remedy for a red indicator and
    would turn it green while the volume stayed wedged.
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="python -m src.workflow.health",
        description="Shared storage heartbeat for the OpenMS web app.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "confirm the shared volume accepts a write and publish this node's "
            "storage heartbeat; exit 1 if the volume did not answer"
        ),
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="print the storage status the sidebar renders, as JSON",
    )
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(get_storage_status(), indent=2))
        return 0
    if args.probe:
        if probe_storage():
            return 0
        directory = os.environ.get("WORKSPACES_DIR") or DEFAULT_WORKSPACES_DIR
        print(
            f"storage probe failed: {os.path.join(directory, STORAGE_SENTINEL_NAME)} "
            "did not accept a write",
            file=sys.stderr,
        )
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
