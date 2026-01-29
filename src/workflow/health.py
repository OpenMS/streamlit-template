"""
Health check utilities for Redis queue monitoring.

Provides functions to check Redis and worker health status
for display in the sidebar metrics. Supports standalone, cluster,
and sentinel Redis deployment modes.
"""

import os


def check_redis_health() -> dict:
    """
    Check Redis connection health.

    Supports all Redis deployment modes (standalone, cluster, sentinel).

    Returns:
        Dictionary with health status and metrics
    """
    try:
        from .RedisConnection import get_redis_health, get_redis_mode

        health = get_redis_health()

        # Add mode to response
        if "mode" not in health:
            try:
                health["mode"] = get_redis_mode().value
            except Exception:
                health["mode"] = "unknown"

        return health

    except ImportError:
        # Fall back to legacy standalone check if RedisConnection not available
        return _check_redis_health_legacy()
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


def _check_redis_health_legacy() -> dict:
    """Legacy health check for standalone Redis (backward compatibility)"""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    try:
        from redis import Redis

        redis = Redis.from_url(redis_url)
        redis.ping()
        info = redis.info()

        return {
            "status": "healthy",
            "mode": "standalone",
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
    try:
        from .RedisConnection import get_redis_connection, get_redis_mode
        from rq import Worker, Queue

        redis = get_redis_connection()
        queue = Queue("openms-workflows", connection=redis)
        workers = Worker.all(connection=redis)

        busy_workers = [w for w in workers if w.get_state() == "busy"]
        idle_workers = [w for w in workers if w.get_state() == "idle"]

        return {
            "status": "healthy",
            "redis_mode": get_redis_mode().value,
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
        # Fall back to legacy check
        return _check_worker_health_legacy()
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


def _check_worker_health_legacy() -> dict:
    """Legacy worker health check (backward compatibility)"""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    try:
        from redis import Redis
        from rq import Worker, Queue

        redis = Redis.from_url(redis_url)
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
    # Check for any Redis configuration (standalone, cluster, or sentinel)
    has_redis_config = (
        os.environ.get("REDIS_URL") or
        os.environ.get("REDIS_CLUSTER_NODES") or
        os.environ.get("REDIS_SENTINEL_HOSTS")
    )

    if not has_redis_config:
        return {}

    try:
        from .RedisConnection import get_redis_connection, get_redis_mode, RedisMode
        from rq import Worker, Queue

        redis = get_redis_connection()

        # Test connection
        redis.ping()

        queue = Queue("openms-workflows", connection=redis)
        workers = Worker.all(connection=redis)

        busy_count = len([w for w in workers if w.get_state() == "busy"])

        mode = get_redis_mode()

        metrics = {
            "available": True,
            "redis_mode": mode.value,
            "total_workers": len(workers),
            "busy_workers": busy_count,
            "idle_workers": len(workers) - busy_count,
            "queued_jobs": len(queue),
            "started_jobs": len(queue.started_job_registry),
            "finished_jobs": len(queue.finished_job_registry),
            "failed_jobs": len(queue.failed_job_registry),
        }

        # Add cluster-specific metrics
        if mode == RedisMode.CLUSTER:
            try:
                cluster_info = redis.cluster_info()
                cluster_nodes = redis.cluster_nodes()
                masters = sum(1 for n in cluster_nodes.values() if "master" in n.get("flags", ""))
                replicas = sum(1 for n in cluster_nodes.values() if "slave" in n.get("flags", ""))

                metrics["cluster_state"] = cluster_info.get("cluster_state", "unknown")
                metrics["cluster_nodes"] = cluster_info.get("cluster_known_nodes", 0)
                metrics["master_nodes"] = masters
                metrics["replica_nodes"] = replicas
            except Exception:
                pass  # Cluster info not available

        return metrics

    except ImportError:
        # Fall back to legacy metrics
        return _get_queue_metrics_legacy()
    except Exception:
        return {"available": False}


def _get_queue_metrics_legacy() -> dict:
    """Legacy queue metrics (backward compatibility)"""
    if not os.environ.get("REDIS_URL"):
        return {}

    try:
        from redis import Redis
        from rq import Worker, Queue

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        redis = Redis.from_url(redis_url)

        # Test connection
        redis.ping()

        queue = Queue("openms-workflows", connection=redis)
        workers = Worker.all(connection=redis)

        busy_count = len([w for w in workers if w.get_state() == "busy"])

        return {
            "available": True,
            "redis_mode": "standalone",
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


def get_cluster_topology() -> dict:
    """
    Get Redis cluster topology information.

    Only returns meaningful data when running in cluster mode.

    Returns:
        Dictionary with cluster topology or empty dict if not in cluster mode
    """
    try:
        from .RedisConnection import get_redis_connection, get_redis_mode, RedisMode

        mode = get_redis_mode()
        if mode != RedisMode.CLUSTER:
            return {"mode": mode.value, "is_cluster": False}

        redis = get_redis_connection()
        cluster_info = redis.cluster_info()
        cluster_nodes = redis.cluster_nodes()

        nodes = []
        for node_id, node_info in cluster_nodes.items():
            nodes.append({
                "id": node_id[:8],  # Shortened ID
                "host": node_info.get("host", "unknown"),
                "port": node_info.get("port", 0),
                "role": "master" if "master" in node_info.get("flags", "") else "replica",
                "slots": node_info.get("slots", []),
                "connected": "connected" in node_info.get("flags", ""),
            })

        return {
            "mode": "cluster",
            "is_cluster": True,
            "state": cluster_info.get("cluster_state", "unknown"),
            "slots_assigned": cluster_info.get("cluster_slots_assigned", 0),
            "slots_ok": cluster_info.get("cluster_slots_ok", 0),
            "known_nodes": cluster_info.get("cluster_known_nodes", 0),
            "nodes": nodes,
        }

    except Exception as e:
        return {"error": str(e), "is_cluster": False}
