"""
Health check utilities for Redis queue monitoring.

Provides functions to check Redis and worker health status
for display in the sidebar metrics.
"""

import os


def check_redis_health() -> dict:
    """
    Check Redis connection health.

    Returns:
        Dictionary with health status and metrics
    """
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    try:
        from redis import Redis

        redis = Redis.from_url(redis_url)
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
    # Only attempt if REDIS_URL is set (online mode)
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
