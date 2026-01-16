"""
Redis Queue Manager for Online Mode Workflow Execution

This module provides job queueing functionality for online deployments,
replacing the multiprocessing approach with Redis-backed job queues.
Only activates when running in online mode with Redis available.
"""

import os
import json
from typing import Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


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
    Redis runs on localhost within the same container.
    """

    QUEUE_NAME = "openms-workflows"
    # Redis runs locally in the same container
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    def __init__(self):
        self._redis = None
        self._queue = None
        self._is_online = self._check_online_mode()
        self._init_attempted = False

        if self._is_online:
            self._init_redis()

    def _check_online_mode(self) -> bool:
        """Check if running in online mode"""
        # Check environment variable first (set in Docker)
        if os.environ.get("REDIS_URL"):
            return True

        # Fallback: check settings file
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
                return settings.get("online_deployment", False)
        except Exception:
            return False

    def _init_redis(self) -> None:
        """Initialize Redis connection and queue"""
        if self._init_attempted:
            return
        self._init_attempted = True

        try:
            from redis import Redis
            from rq import Queue

            self._redis = Redis.from_url(self.REDIS_URL)
            self._redis.ping()  # Test connection
            self._queue = Queue(self.QUEUE_NAME, connection=self._redis)
        except ImportError:
            # Redis/RQ packages not installed
            self._redis = None
            self._queue = None
        except Exception:
            # Redis server not available
            self._redis = None
            self._queue = None

    @property
    def is_available(self) -> bool:
        """Check if queue system is available"""
        return self._is_online and self._queue is not None

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
            Dictionary with queue stats
        """
        if not self.is_available:
            return {}

        try:
            from rq import Worker

            workers = Worker.all(connection=self._redis)
            busy_workers = len([w for w in workers if w.get_state() == "busy"])

            return {
                "queued": len(self._queue),
                "started": len(self._queue.started_job_registry),
                "finished": len(self._queue.finished_job_registry),
                "failed": len(self._queue.failed_job_registry),
                "workers": len(workers),
                "busy_workers": busy_workers,
                "idle_workers": len(workers) - busy_workers,
            }
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
