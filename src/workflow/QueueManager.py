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
        self._init_attempted = False

        settings = self._load_settings()
        self._is_online = self._check_online_mode(settings)

        queue_settings = settings.get("queue_settings", {})
        self._default_timeout = queue_settings.get("default_timeout", 7200)
        self._default_result_ttl = queue_settings.get("result_ttl", 86400)

        if self._is_online:
            self._init_redis()

    @staticmethod
    def _load_settings() -> dict:
        """Load settings.json once; return empty dict on failure."""
        try:
            with open("settings.json", "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _check_online_mode(self, settings: dict) -> bool:
        """Check if running in online mode"""
        # Check environment variable first (set in Docker)
        if os.environ.get("REDIS_URL"):
            return True

        return settings.get("online_deployment", False)

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
        timeout: Optional[int] = None,
        result_ttl: Optional[int] = None,
        description: str = ""
    ) -> Optional[str]:
        """
        Submit a job to the queue.

        Args:
            func: The function to execute
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            job_id: Optional custom job ID (defaults to UUID)
            timeout: Job timeout in seconds (defaults to settings.json queue_settings.default_timeout)
            result_ttl: How long to keep results (defaults to settings.json queue_settings.result_ttl)
            description: Human-readable job description

        Returns:
            Job ID if successful, None otherwise
        """
        if not self.is_available:
            return None

        kwargs = kwargs or {}
        if timeout is None:
            timeout = self._default_timeout
        if result_ttl is None:
            result_ttl = self._default_result_ttl

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

            # 'stopped' is what RQ records after send_stop_job_command runs;
            # surface it as CANCELED so the UI doesn't show stopped jobs as queued.
            status_map = {
                "queued": JobStatus.QUEUED,
                "started": JobStatus.STARTED,
                "finished": JobStatus.FINISHED,
                "failed": JobStatus.FAILED,
                "deferred": JobStatus.DEFERRED,
                "canceled": JobStatus.CANCELED,
                "stopped": JobStatus.CANCELED,
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

        For queued jobs, this removes them from the queue. For jobs that are
        already executing in a worker, Job.cancel() alone is not enough — it
        only updates Redis registries while the worker keeps running the
        workflow. We send a stop-job command to the worker so the work-horse
        is actually interrupted.

        Args:
            job_id: The job ID to cancel

        Returns:
            True if the job is canceled (or already was), False otherwise.
        """
        if not self.is_available:
            return False

        try:
            from rq.command import send_stop_job_command
            from rq.exceptions import InvalidJobOperation, NoSuchJobError
            from rq.job import Job
        except ImportError:
            return False

        try:
            job = Job.fetch(job_id, connection=self._redis)
        except NoSuchJobError:
            return False
        except Exception:
            return False

        # Idempotent: a second Stop click (or rerun) should not surface an error.
        if job.is_canceled or job.is_stopped:
            return True

        # Tell the worker to interrupt the work-horse before marking canceled.
        if job.is_started and job.worker_name:
            try:
                send_stop_job_command(self._redis, job_id)
            except InvalidJobOperation:
                # The worker just finished or the job moved out of 'started';
                # fall through to cancel() to settle registry state.
                pass
            except Exception:
                pass

        try:
            job.cancel()
        except InvalidJobOperation:
            # Worker already transitioned the job (e.g. to 'stopped'); that
            # satisfies the user's intent to stop.
            pass
        except Exception:
            return False

        return True

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
