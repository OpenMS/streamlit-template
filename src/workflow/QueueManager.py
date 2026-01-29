"""
Redis Queue Manager for Online Mode Workflow Execution

This module provides job queueing functionality for online deployments,
replacing the multiprocessing approach with Redis-backed job queues.
Only activates when running in online mode with Redis available.

Supports multiple Redis deployment modes:
- standalone: Single Redis instance (default, backward compatible)
- cluster: Redis Cluster for horizontal scaling
- sentinel: Redis Sentinel for high availability
"""

import os
import json
import logging
from typing import Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job status enumeration matching RQ states"""
    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    FAILED = "failed"
    DEFERRED = "deferred"
    CANCELED = "canceled"


@dataclass
class JobInfo:
    """Container for job information"""
    job_id: str
    status: JobStatus
    progress: float  # 0.0 to 1.0
    current_step: str
    queue_position: Optional[int] = None
    queue_length: Optional[int] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    enqueued_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


class QueueManager:
    """
    Manages Redis Queue operations for workflow execution.

    Only active in online mode. Falls back to direct execution in local mode.

    Supports multiple Redis deployment modes via environment variables:
    - REDIS_MODE: 'standalone' | 'cluster' | 'sentinel' (default: 'standalone')
    - REDIS_URL: Connection URL for standalone mode
    - REDIS_CLUSTER_NODES: Comma-separated nodes for cluster mode
    - REDIS_SENTINEL_HOSTS: Comma-separated hosts for sentinel mode
    - REDIS_SENTINEL_MASTER: Master name for sentinel mode

    See RedisConnection.py for full configuration options.
    """

    QUEUE_NAME = "openms-workflows"

    def __init__(self):
        self._redis = None
        self._queue = None
        self._connection_factory = None
        self._is_online = self._check_online_mode()
        self._init_attempted = False

        if self._is_online:
            self._init_redis()

    def _check_online_mode(self) -> bool:
        """Check if running in online mode"""
        # Check environment variable first (set in Docker)
        if os.environ.get("REDIS_URL") or os.environ.get("REDIS_CLUSTER_NODES") or os.environ.get("REDIS_SENTINEL_HOSTS"):
            return True

        # Fallback: check settings file
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
                return settings.get("online_deployment", False)
        except Exception:
            return False

    def _init_redis(self) -> None:
        """Initialize Redis connection and queue using the connection factory"""
        if self._init_attempted:
            return
        self._init_attempted = True

        try:
            from rq import Queue
            from .RedisConnection import RedisConnectionFactory, RedisMode

            # Use the connection factory for cluster-aware connections
            self._connection_factory = RedisConnectionFactory()
            self._redis = self._connection_factory.get_connection()

            # RQ Queue works with all Redis connection types
            self._queue = Queue(self.QUEUE_NAME, connection=self._redis)

            mode = self._connection_factory.config.mode
            logger.info(f"QueueManager initialized with Redis mode: {mode.value}")

        except ImportError as e:
            # Redis/RQ packages not installed
            logger.warning(f"Redis packages not installed: {e}")
            self._redis = None
            self._queue = None
            self._connection_factory = None
        except Exception as e:
            # Redis server not available
            logger.warning(f"Redis connection failed: {e}")
            self._redis = None
            self._queue = None
            self._connection_factory = None

    @property
    def is_available(self) -> bool:
        """Check if queue system is available"""
        return self._is_online and self._queue is not None

    @property
    def redis_mode(self) -> Optional[str]:
        """Get the current Redis deployment mode"""
        if self._connection_factory:
            return self._connection_factory.config.mode.value
        return None

    def get_redis_health(self) -> dict:
        """Get Redis health information including cluster/sentinel status"""
        if self._connection_factory:
            return self._connection_factory.get_health_info()
        return {"status": "unavailable", "error": "Not initialized"}

    def submit_job(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        job_id: Optional[str] = None,
        timeout: int = 7200,  # 2 hour default
        result_ttl: int = 86400,  # 24 hours
        description: str = ""
    ) -> Optional[str]:
        """
        Submit a job to the queue.

        Args:
            func: The function to execute
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            job_id: Optional custom job ID (defaults to UUID)
            timeout: Job timeout in seconds
            result_ttl: How long to keep results
            description: Human-readable job description

        Returns:
            Job ID if successful, None otherwise
        """
        if not self.is_available:
            return None

        kwargs = kwargs or {}

        try:
            job = self._queue.enqueue(
                func,
                args=args,
                kwargs=kwargs,
                job_id=job_id,
                job_timeout=timeout,
                result_ttl=result_ttl,
                description=description,
                meta={"description": description, "progress": 0.0, "current_step": ""}
            )
            return job.id
        except Exception:
            return None

    def get_job_info(self, job_id: str) -> Optional[JobInfo]:
        """
        Get information about a job.

        Args:
            job_id: The job ID to query

        Returns:
            JobInfo object or None if not found
        """
        if not self.is_available:
            return None

        try:
            from rq.job import Job

            job = Job.fetch(job_id, connection=self._redis)

            # Map RQ status to our enum
            status_map = {
                "queued": JobStatus.QUEUED,
                "started": JobStatus.STARTED,
                "finished": JobStatus.FINISHED,
                "failed": JobStatus.FAILED,
                "deferred": JobStatus.DEFERRED,
                "canceled": JobStatus.CANCELED,
            }

            status = status_map.get(job.get_status(), JobStatus.QUEUED)

            # Get progress from job meta
            meta = job.meta or {}
            progress = meta.get("progress", 0.0)
            current_step = meta.get("current_step", "")

            # Calculate queue position if queued
            queue_position = None
            queue_length = None
            if status == JobStatus.QUEUED:
                queue_position = self._get_job_position(job_id)
                queue_length = len(self._queue)

            return JobInfo(
                job_id=job.id,
                status=status,
                progress=progress,
                current_step=current_step,
                queue_position=queue_position,
                queue_length=queue_length,
                result=job.result if status == JobStatus.FINISHED else None,
                error=str(job.exc_info) if job.exc_info else None,
                enqueued_at=str(job.enqueued_at) if job.enqueued_at else None,
                started_at=str(job.started_at) if job.started_at else None,
                ended_at=str(job.ended_at) if job.ended_at else None,
            )
        except Exception:
            return None

    def _get_job_position(self, job_id: str) -> Optional[int]:
        """Get position of a job in the queue (1-indexed)"""
        try:
            job_ids = self._queue.job_ids
            if job_id in job_ids:
                return job_ids.index(job_id) + 1
            return None
        except Exception:
            return None

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a queued or running job.

        Args:
            job_id: The job ID to cancel

        Returns:
            True if successfully canceled
        """
        if not self.is_available:
            return False

        try:
            from rq.job import Job

            job = Job.fetch(job_id, connection=self._redis)
            job.cancel()
            return True
        except Exception:
            return False

    def get_queue_stats(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Dictionary with queue stats including Redis mode
        """
        if not self.is_available:
            return {}

        try:
            from rq import Worker

            workers = Worker.all(connection=self._redis)
            busy_workers = len([w for w in workers if w.get_state() == "busy"])

            stats = {
                "queued": len(self._queue),
                "started": len(self._queue.started_job_registry),
                "finished": len(self._queue.finished_job_registry),
                "failed": len(self._queue.failed_job_registry),
                "workers": len(workers),
                "busy_workers": busy_workers,
                "idle_workers": len(workers) - busy_workers,
                "redis_mode": self.redis_mode,
            }

            # Add cluster-specific info if in cluster mode
            if self._connection_factory:
                health = self._connection_factory.get_health_info()
                if health.get("cluster_state"):
                    stats["cluster_state"] = health["cluster_state"]
                    stats["cluster_nodes"] = health.get("cluster_known_nodes", 0)
                    stats["master_nodes"] = health.get("master_nodes", 0)
                    stats["replica_nodes"] = health.get("replica_nodes", 0)

            return stats
        except Exception:
            return {}

    def store_job_id(self, workflow_dir: Path, job_id: str) -> None:
        """Store job ID in workflow directory for recovery"""
        job_file = Path(workflow_dir) / ".job_id"
        job_file.write_text(job_id)

    def load_job_id(self, workflow_dir: Path) -> Optional[str]:
        """Load job ID from workflow directory"""
        job_file = Path(workflow_dir) / ".job_id"
        if job_file.exists():
            return job_file.read_text().strip()
        return None

    def clear_job_id(self, workflow_dir: Path) -> None:
        """Clear stored job ID"""
        job_file = Path(workflow_dir) / ".job_id"
        if job_file.exists():
            job_file.unlink()
