# Redis Queue Implementation Plan for Online Mode

## Overview

This document outlines the implementation plan for introducing a Redis-based job queueing system to the OpenMS Streamlit Template's **online mode only**. This system will replace the current `multiprocessing.Process` approach with a more robust, scalable queue architecture suitable for production deployments.

**Important:** The existing multiprocessing system remains completely unchanged for offline/local deployments (including the Windows installer). Redis queue is purely additive and only activates in online Docker deployments.

---

## Design Principles

### Plug & Play Architecture

The Redis queue system is designed with minimal changes to existing code:

```
┌─────────────────────────────────────────────────────────────────┐
│                      WorkflowManager                             │
│                                                                   │
│   start_workflow()                                               │
│        │                                                         │
│        ▼                                                         │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  if online_mode AND redis_available:                     │   │
│   │      → Submit to Redis Queue (new code)                  │   │
│   │  else:                                                   │   │
│   │      → multiprocessing.Process (existing code, unchanged)│   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
1. **Zero changes to local mode**: Windows installer and local development work exactly as before
2. **Graceful fallback**: If Redis is unavailable, automatically uses multiprocessing
3. **Feature flag**: Can be disabled via `queue_settings.enabled = false`
4. **Same execution logic**: The `execution()` method code is identical - only the process spawning differs

### Offline Mode (Windows Installer) Compatibility

The Windows installer built from GitHub Actions uses local mode with no Redis:

| Mode | Queue System | Process Model | Use Case |
|------|--------------|---------------|----------|
| **Local** (`online_deployment: false`) | None | `multiprocessing.Process` | Windows installer, local dev |
| **Online** (`online_deployment: true`) | Redis + RQ | RQ Worker | Docker deployment |

**No code changes required for offline mode.** The detection happens automatically:

```python
# In WorkflowManager
def start_workflow(self):
    if self._is_online_mode() and self._queue_manager.is_available:
        self._start_workflow_queued()    # Redis queue
    else:
        self._start_workflow_local()      # Existing multiprocessing (unchanged)
```

---

## Current Architecture

### How Workflows Execute Today

```
┌─────────────────────┐      ┌──────────────────────────┐
│   Streamlit UI      │      │    Detached Process      │
│   (Browser)         │      │    (Same Container)      │
├─────────────────────┤      ├──────────────────────────┤
│ 1. User clicks      │─────→│ multiprocessing.Process  │
│    "Start Workflow" │      │                          │
│ 2. Monitor log file │      │ • Runs workflow_process()│
│ 3. Poll for PID     │      │ • Executes TOPP tools    │
│    removal          │      │ • Logs to files          │
└─────────────────────┘      │ • Deletes PID on done    │
                             └──────────────────────────┘
```

**Key Files:**
- `/src/workflow/WorkflowManager.py:25-38` - Process spawning
- `/src/workflow/StreamlitUI.py:989-1057` - Execution UI/monitoring
- `/src/workflow/CommandExecutor.py:28-61` - Command execution

**Limitations of Current Approach:**
1. No job persistence across container restarts
2. No visibility into queue depth or worker health
3. Limited scalability (single container)
4. No job retry mechanism on failure
5. No priority queuing
6. Difficult to add job timeouts

---

## Proposed Architecture

### Single-Container Redis Queue System

All components run within the same Docker container, ensuring identical environments for the web app and worker processes.

```
┌────────────────────────────────────────────────────────────┐
│                    Docker Container                         │
│                                                             │
│  ┌─────────────────┐    ┌─────────────┐    ┌────────────┐  │
│  │  Streamlit App  │───→│ Redis Server│←───│ RQ Worker  │  │
│  │  (Main Process) │    │ (localhost) │    │ (Background)│  │
│  └─────────────────┘    └─────────────┘    └────────────┘  │
│         │                      ↑                  │         │
│         │    Submit jobs       │    Poll jobs     │         │
│         └──────────────────────┴──────────────────┘         │
│                                                             │
│  All processes share: pyOpenMS, TOPP tools, Python env     │
└────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Message Broker | **Redis** (embedded) | Fast, simple, runs as background process |
| Task Queue | **RQ (Redis Queue)** | Lightweight, Python-native, simpler than Celery |
| Job Monitoring | **rq-dashboard** (optional) | Can run in same container if needed |

**Why Single Container?**
- **Environment consistency**: Worker has identical pyOpenMS/TOPP installation
- **Simpler deployment**: One image, one container, no orchestration complexity
- **No networking issues**: All communication via localhost
- **Easier debugging**: All logs in one place
- **Lower resource overhead**: No container-to-container communication

**Why RQ over Celery?**
- Simpler configuration (fewer moving parts)
- Lower memory footprint
- Native Python job serialization
- Perfect for single-container deployment
- Easier to debug and maintain

---

## Implementation Plan

### Phase 1: Infrastructure Setup (Single Container)

#### 1.1 Update Dockerfile

**File:** `/Dockerfile`

Add Redis server installation and modify the entrypoint to start all services.

```dockerfile
# === Add to the run-app stage (around line 130) ===

# Install Redis server
RUN apt-get update && apt-get install -y --no-install-recommends \
    redis-server \
    && rm -rf /var/lib/apt/lists/*

# Install Python Redis client and RQ
RUN pip install rq redis

# Create Redis data directory
RUN mkdir -p /var/lib/redis && chown redis:redis /var/lib/redis

# === Replace the entrypoint script section (around line 160-170) ===

# Create entrypoint script that starts all services
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Start cron for workspace cleanup\n\
service cron start\n\
\n\
# Start Redis server in background\n\
echo "Starting Redis server..."\n\
redis-server --daemonize yes --dir /var/lib/redis --appendonly yes\n\
\n\
# Wait for Redis to be ready\n\
until redis-cli ping > /dev/null 2>&1; do\n\
    echo "Waiting for Redis..."\n\
    sleep 1\n\
done\n\
echo "Redis is ready"\n\
\n\
# Start RQ worker(s) in background\n\
echo "Starting RQ worker..."\n\
cd /openms-streamlit-template\n\
rq worker openms-workflows --url redis://localhost:6379/0 &\n\
\n\
# Optionally start RQ dashboard (uncomment if needed)\n\
# rq-dashboard --redis-url redis://localhost:6379/0 --port 9181 &\n\
\n\
# Start Streamlit (foreground - main process)\n\
echo "Starting Streamlit app..."\n\
exec streamlit run app.py\n\
' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
```

#### 1.2 Update Requirements

**File:** `/requirements.txt` (additions)

```
rq>=1.16.0
redis>=5.0.0
rq-dashboard>=0.6.0  # Optional: for web-based queue monitoring
```

#### 1.3 Docker Compose (Minimal Changes)

**File:** `/docker-compose.yml`

The docker-compose.yml requires minimal changes - just add environment variable:

```yaml
services:
  openms-streamlit-template:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        GITHUB_TOKEN: $GITHUB_TOKEN
    image: openms_streamlit_template
    container_name: openms-streamlit-template
    restart: always
    ports:
      - 8501:8501
      # - 9181:9181  # Uncomment to expose RQ dashboard
    volumes:
      - workspaces-streamlit-template:/workspaces-streamlit-template
    environment:
      - REDIS_URL=redis://localhost:6379/0
    # command is handled by entrypoint.sh

volumes:
  workspaces-streamlit-template:
```

#### 1.4 Alternative: Supervisor for Process Management (Optional)

For more robust process management, use `supervisord`:

**File:** `/supervisord.conf`

```ini
[supervisord]
nodaemon=true
user=root

[program:redis]
command=redis-server --dir /var/lib/redis --appendonly yes
autostart=true
autorestart=true
priority=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:rq-worker]
command=rq worker openms-workflows --url redis://localhost:6379/0
directory=/openms-streamlit-template
autostart=true
autorestart=true
priority=20
startsecs=5
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:streamlit]
command=streamlit run app.py
directory=/openms-streamlit-template
autostart=true
autorestart=true
priority=30
startsecs=10
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

Then update Dockerfile:
```dockerfile
RUN apt-get update && apt-get install -y supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```

---

### Phase 2: Core Queue Implementation

#### 2.1 Create Queue Manager Module

**New File:** `/src/workflow/QueueManager.py`

```python
"""
Redis Queue Manager for Online Mode Workflow Execution

This module provides job queueing functionality for online deployments,
replacing the multiprocessing approach with Redis-backed job queues.
"""

import os
from typing import Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
from redis import Redis
from rq import Queue, Worker
from rq.job import Job
import json
from pathlib import Path
import streamlit as st


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
        self._redis: Optional[Redis] = None
        self._queue: Optional[Queue] = None
        self._is_online = self._check_online_mode()

        if self._is_online:
            self._init_redis()

    def _check_online_mode(self) -> bool:
        """Check if running in online mode"""
        if "settings" in st.session_state:
            return st.session_state.settings.get("online_deployment", False)

        # Fallback: check settings file
        try:
            with open("settings.json", "r") as f:
                settings = json.load(f)
                return settings.get("online_deployment", False)
        except Exception:
            return False

    def _init_redis(self) -> None:
        """Initialize Redis connection and queue"""
        try:
            self._redis = Redis.from_url(self.REDIS_URL)
            self._redis.ping()  # Test connection
            self._queue = Queue(self.QUEUE_NAME, connection=self._redis)
        except Exception as e:
            st.error(f"Failed to connect to Redis: {e}")
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
        timeout: int = 3600,  # 1 hour default
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
                meta={"description": description}
            )
            return job.id
        except Exception as e:
            st.error(f"Failed to submit job: {e}")
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

            return JobInfo(
                job_id=job.id,
                status=status,
                progress=progress,
                current_step=current_step,
                result=job.result if status == JobStatus.FINISHED else None,
                error=str(job.exc_info) if job.exc_info else None,
                enqueued_at=str(job.enqueued_at) if job.enqueued_at else None,
                started_at=str(job.started_at) if job.started_at else None,
                ended_at=str(job.ended_at) if job.ended_at else None,
            )
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
            return {
                "queued": len(self._queue),
                "started": len(self._queue.started_job_registry),
                "finished": len(self._queue.finished_job_registry),
                "failed": len(self._queue.failed_job_registry),
                "workers": Worker.count(queue=self._queue),
            }
        except Exception:
            return {}

    def update_job_progress(
        self,
        job: Job,
        progress: float,
        current_step: str = ""
    ) -> None:
        """
        Update job progress (call from within worker).

        Args:
            job: The current RQ job object
            progress: Progress value 0.0 to 1.0
            current_step: Description of current step
        """
        job.meta["progress"] = min(max(progress, 0.0), 1.0)
        job.meta["current_step"] = current_step
        job.save_meta()

    def store_job_id(self, workflow_dir: Path, job_id: str) -> None:
        """Store job ID in workflow directory for recovery"""
        job_file = workflow_dir / ".job_id"
        job_file.write_text(job_id)

    def load_job_id(self, workflow_dir: Path) -> Optional[str]:
        """Load job ID from workflow directory"""
        job_file = workflow_dir / ".job_id"
        if job_file.exists():
            return job_file.read_text().strip()
        return None

    def clear_job_id(self, workflow_dir: Path) -> None:
        """Clear stored job ID"""
        job_file = workflow_dir / ".job_id"
        if job_file.exists():
            job_file.unlink()
```

#### 2.2 Create Worker Tasks Module

**New File:** `/src/workflow/tasks.py`

```python
"""
Worker tasks for Redis Queue execution.

These functions are executed by RQ workers and should not import Streamlit.
"""

import sys
import json
from pathlib import Path
from typing import Any
from rq import get_current_job

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.workflow.CommandExecutor import CommandExecutor
from src.workflow.FileManager import FileManager
from src.workflow.ParameterManager import ParameterManager
from src.workflow.Logger import Logger


def execute_workflow(
    workflow_dir: str,
    workflow_class: str,
    workflow_module: str,
) -> dict:
    """
    Execute a workflow in the worker process.

    Args:
        workflow_dir: Path to the workflow directory
        workflow_class: Name of the Workflow class
        workflow_module: Module path containing the Workflow class

    Returns:
        Dictionary with execution results
    """
    job = get_current_job()
    workflow_path = Path(workflow_dir)

    try:
        # Update progress
        _update_progress(job, 0.0, "Initializing workflow...")

        # Load the workflow class dynamically
        import importlib
        module = importlib.import_module(workflow_module)
        WorkflowClass = getattr(module, workflow_class)

        # Initialize workflow components (non-Streamlit mode)
        workflow_path = Path(workflow_dir)

        # Create a minimal workflow instance for execution
        # The workflow will read params from the saved params.json
        params_file = workflow_path / "params.json"
        if params_file.exists():
            with open(params_file, "r") as f:
                params = json.load(f)
        else:
            params = {}

        # Initialize executor and logger
        logger = Logger(workflow_path)
        file_manager = FileManager(workflow_path, params)
        executor = CommandExecutor(workflow_path, logger)

        # Create workflow instance with components
        workflow = WorkflowClass.__new__(WorkflowClass)
        workflow.workflow_dir = workflow_path
        workflow.params = params
        workflow.logger = logger
        workflow.file_manager = file_manager
        workflow.executor = executor

        # Inject progress callback
        workflow._job = job
        workflow._update_progress = lambda p, s: _update_progress(job, p, s)

        _update_progress(job, 0.1, "Starting workflow execution...")

        # Execute the workflow
        workflow.execution()

        _update_progress(job, 1.0, "Workflow completed")

        return {
            "success": True,
            "workflow_dir": str(workflow_path),
            "message": "Workflow completed successfully"
        }

    except Exception as e:
        import traceback
        error_msg = f"Workflow failed: {str(e)}\n{traceback.format_exc()}"

        # Log error to workflow logs
        try:
            log_file = workflow_path / "logs" / "all.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a") as f:
                f.write(f"\n\nERROR: {error_msg}\n")
        except Exception:
            pass

        return {
            "success": False,
            "workflow_dir": str(workflow_path),
            "error": error_msg
        }


def _update_progress(job, progress: float, step: str) -> None:
    """Update job progress metadata"""
    if job:
        job.meta["progress"] = progress
        job.meta["current_step"] = step
        job.save_meta()
```

---

### Phase 3: Integration with Existing Code

#### 3.1 Modify WorkflowManager

**File:** `/src/workflow/WorkflowManager.py`

Add queue support while maintaining backward compatibility:

```python
"""
Modified WorkflowManager with Redis Queue support for online mode.
"""

import multiprocessing
from pathlib import Path
from typing import Optional
import json
import streamlit as st

from src.workflow.StreamlitUI import StreamlitUI
from src.workflow.CommandExecutor import CommandExecutor
from src.workflow.FileManager import FileManager
from src.workflow.ParameterManager import ParameterManager
from src.workflow.Logger import Logger


class WorkflowManager(StreamlitUI):
    """
    Base class for workflow management with dual execution modes:
    - Online mode: Uses Redis Queue for job execution
    - Local mode: Uses multiprocessing (existing behavior)
    """

    def __init__(
        self,
        name: str,
        st_session_state: dict
    ) -> None:
        self.name = name
        self.params = st_session_state

        # Initialize paths
        self.workflow_dir = Path(
            st.session_state.workspace,
            self.name.replace(" ", "-").lower()
        )
        self.workflow_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.logger = Logger(self.workflow_dir)
        self.file_manager = FileManager(self.workflow_dir, self.params)
        self.executor = CommandExecutor(self.workflow_dir, self.logger)
        self.parameter_manager = ParameterManager(self.workflow_dir, self.params)

        # Initialize StreamlitUI
        super().__init__(
            self.workflow_dir,
            self.logger,
            self.executor,
            self.parameter_manager,
            self.file_manager
        )

        # Initialize queue manager for online mode
        self._queue_manager: Optional['QueueManager'] = None
        if self._is_online_mode():
            self._init_queue_manager()

    def _is_online_mode(self) -> bool:
        """Check if running in online deployment mode"""
        return st.session_state.get("settings", {}).get("online_deployment", False)

    def _init_queue_manager(self) -> None:
        """Initialize queue manager for online mode"""
        try:
            from src.workflow.QueueManager import QueueManager
            self._queue_manager = QueueManager()
        except ImportError:
            pass  # Queue not available, will use fallback

    def start_workflow(self) -> None:
        """
        Starts workflow execution.

        Online mode: Submits to Redis queue
        Local mode: Spawns multiprocessing.Process (existing behavior)
        """
        # Save current parameters before execution
        self.parameter_manager.save_parameters()

        if self._queue_manager and self._queue_manager.is_available:
            self._start_workflow_queued()
        else:
            self._start_workflow_local()

    def _start_workflow_queued(self) -> None:
        """Submit workflow to Redis queue (online mode)"""
        from src.workflow.tasks import execute_workflow

        # Generate job ID based on workspace
        job_id = f"workflow-{self.workflow_dir.name}-{Path(st.session_state.workspace).name}"

        # Submit job
        submitted_id = self._queue_manager.submit_job(
            func=execute_workflow,
            kwargs={
                "workflow_dir": str(self.workflow_dir),
                "workflow_class": self.__class__.__name__,
                "workflow_module": self.__class__.__module__,
            },
            job_id=job_id,
            timeout=7200,  # 2 hour timeout
            description=f"Workflow: {self.name}"
        )

        if submitted_id:
            # Store job ID for status checking
            self._queue_manager.store_job_id(self.workflow_dir, submitted_id)
            st.success(f"Workflow submitted to queue (Job ID: {submitted_id})")
        else:
            st.error("Failed to submit workflow to queue")

    def _start_workflow_local(self) -> None:
        """Start workflow as local process (existing behavior)"""
        workflow_process = multiprocessing.Process(target=self.workflow_process)
        workflow_process.start()

        # Create PID directory and file
        self.executor.pid_dir.mkdir(parents=True, exist_ok=True)
        Path(self.executor.pid_dir, str(workflow_process.pid)).touch()

    def workflow_process(self) -> None:
        """
        Main workflow execution method.
        Override in subclass to define workflow logic.
        """
        self.logger.log("Starting workflow...")
        self.execution()
        self.logger.log("WORKFLOW FINISHED")

    def get_workflow_status(self) -> dict:
        """
        Get current workflow execution status.

        Returns:
            Dictionary with status information
        """
        if self._queue_manager and self._queue_manager.is_available:
            job_id = self._queue_manager.load_job_id(self.workflow_dir)
            if job_id:
                job_info = self._queue_manager.get_job_info(job_id)
                if job_info:
                    return {
                        "running": job_info.status.value in ["queued", "started"],
                        "status": job_info.status.value,
                        "progress": job_info.progress,
                        "current_step": job_info.current_step,
                        "job_id": job_id,
                    }

        # Fallback: check PID files (local mode)
        pid_dir = self.executor.pid_dir
        if pid_dir.exists() and list(pid_dir.iterdir()):
            return {
                "running": True,
                "status": "running",
                "progress": None,
                "current_step": None,
                "job_id": None,
            }

        return {
            "running": False,
            "status": "idle",
            "progress": None,
            "current_step": None,
            "job_id": None,
        }

    def stop_workflow(self) -> bool:
        """
        Stop a running workflow.

        Returns:
            True if successfully stopped
        """
        if self._queue_manager and self._queue_manager.is_available:
            job_id = self._queue_manager.load_job_id(self.workflow_dir)
            if job_id:
                success = self._queue_manager.cancel_job(job_id)
                if success:
                    self._queue_manager.clear_job_id(self.workflow_dir)
                return success

        # Fallback: kill local process
        return self._stop_local_workflow()

    def _stop_local_workflow(self) -> bool:
        """Stop locally running workflow process"""
        import os
        import signal

        pid_dir = self.executor.pid_dir
        if not pid_dir.exists():
            return False

        for pid_file in pid_dir.iterdir():
            try:
                pid = int(pid_file.name)
                os.kill(pid, signal.SIGTERM)
                pid_file.unlink()
            except (ValueError, ProcessLookupError, PermissionError):
                pid_file.unlink()  # Clean up stale PID file

        return True

    # Abstract methods to override
    def upload(self) -> None:
        """Override to define file upload UI"""
        pass

    def configure(self) -> None:
        """Override to define parameter configuration UI"""
        pass

    def execution(self) -> None:
        """Override to define workflow execution logic"""
        pass

    def results(self) -> None:
        """Override to define results display"""
        pass
```

#### 3.2 Update StreamlitUI Execution Section

**File:** `/src/workflow/StreamlitUI.py`

Modify the `show_execution_section()` method to show queue status:

```python
def show_execution_section(self) -> None:
    """
    Display workflow execution section with queue status for online mode.
    """
    st.header("Workflow Execution")

    # Get workflow status
    status = self.get_workflow_status() if hasattr(self, 'get_workflow_status') else {}
    is_running = status.get("running", False)

    # Show queue status for online mode
    if status.get("job_id"):
        self._show_queue_status(status)

    # Execution controls
    col1, col2 = st.columns(2)

    with col1:
        if is_running:
            if st.button("Stop Workflow", type="secondary", use_container_width=True):
                if hasattr(self, 'stop_workflow'):
                    self.stop_workflow()
                    st.rerun()
        else:
            if st.button("Start Workflow", type="primary", use_container_width=True):
                if hasattr(self, 'start_workflow'):
                    self.start_workflow()
                    st.rerun()

    with col2:
        log_level = st.selectbox(
            "Log Level",
            ["minimal", "commands and run times", "all"],
            key="log-level-select"
        )

    # Show logs
    self._show_logs(log_level, is_running)


def _show_queue_status(self, status: dict) -> None:
    """Display queue job status"""
    job_status = status.get("status", "unknown")
    progress = status.get("progress")
    current_step = status.get("current_step", "")

    # Status indicator
    status_colors = {
        "queued": "🟡",
        "started": "🔵",
        "finished": "🟢",
        "failed": "🔴",
    }

    status_icon = status_colors.get(job_status, "⚪")
    st.markdown(f"**Job Status:** {status_icon} {job_status.capitalize()}")

    # Progress bar
    if progress is not None and job_status == "started":
        st.progress(progress, text=current_step or "Processing...")

    # Job ID
    with st.expander("Job Details"):
        st.code(f"Job ID: {status.get('job_id', 'N/A')}")
```

---

### Phase 4: Configuration & Environment

#### 4.1 Update Settings Schema

**File:** `/settings.json` (additions)

```json
{
    "online_deployment": false,
    "queue_settings": {
        "enabled": true,
        "redis_url": "redis://localhost:6379/0",
        "default_timeout": 7200,
        "max_retries": 3,
        "result_ttl": 86400
    }
}
```

#### 4.2 Environment Variables

These are set automatically in the container (localhost since same container):

```
REDIS_URL=redis://localhost:6379/0
RQ_QUEUE_NAME=openms-workflows
RQ_WORKER_TIMEOUT=7200
```

---

### Phase 5: Monitoring & Operations

#### 5.1 Queue Health Check Endpoint

**New File:** `/src/workflow/health.py`

```python
"""Health check utilities for queue monitoring"""

import os
from redis import Redis


def check_redis_health() -> dict:
    """Check Redis connection health"""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    try:
        redis = Redis.from_url(redis_url)
        redis.ping()
        info = redis.info()

        return {
            "status": "healthy",
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "unknown"),
            "uptime_days": info.get("uptime_in_days", 0),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


def check_worker_health() -> dict:
    """Check RQ worker health"""
    from rq import Worker, Queue

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    try:
        redis = Redis.from_url(redis_url)
        queue = Queue("openms-workflows", connection=redis)
        workers = Worker.all(connection=redis)

        return {
            "status": "healthy",
            "worker_count": len(workers),
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
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }
```

#### 5.2 Admin Dashboard Page (Optional)

**New File:** `/content/admin_queue.py`

```python
"""Queue administration page for online deployments"""

import streamlit as st
from src.common.common import page_setup

page_setup()

# Only show in online mode
if not st.session_state.settings.get("online_deployment", False):
    st.warning("Queue administration is only available in online mode.")
    st.stop()

st.title("Queue Administration")

from src.workflow.health import check_redis_health, check_worker_health

# Redis Health
st.subheader("Redis Status")
redis_health = check_redis_health()
if redis_health["status"] == "healthy":
    st.success("Redis: Connected")
    col1, col2, col3 = st.columns(3)
    col1.metric("Clients", redis_health.get("connected_clients", 0))
    col2.metric("Memory", redis_health.get("used_memory", "N/A"))
    col3.metric("Uptime (days)", redis_health.get("uptime_days", 0))
else:
    st.error(f"Redis: {redis_health.get('error', 'Disconnected')}")

# Worker Health
st.subheader("Worker Status")
worker_health = check_worker_health()
if worker_health["status"] == "healthy":
    st.success(f"Workers: {worker_health.get('worker_count', 0)} active")
    st.metric("Queue Length", worker_health.get("queue_length", 0))

    if worker_health.get("workers"):
        st.write("**Active Workers:**")
        for worker in worker_health["workers"]:
            state_emoji = "🟢" if worker["state"] == "busy" else "🟡"
            st.write(f"{state_emoji} {worker['name']} - {worker['state']}")
else:
    st.error(f"Workers: {worker_health.get('error', 'No workers')}")

# Link to RQ Dashboard
st.subheader("Detailed Monitoring")
st.markdown("[Open RQ Dashboard](http://localhost:9181)")
```

---

## File Summary

### New Files to Create

| File | Purpose |
|------|---------|
| `/src/workflow/QueueManager.py` | Redis queue interaction layer |
| `/src/workflow/tasks.py` | Worker task definitions |
| `/src/workflow/health.py` | Health check utilities |
| `/content/admin_queue.py` | Admin dashboard page (optional) |
| `/supervisord.conf` | Process manager config (optional) |

### Files to Modify

| File | Changes |
|------|---------|
| `/Dockerfile` | Install Redis server, RQ, update entrypoint |
| `/docker-compose.yml` | Minor: add REDIS_URL env var |
| `/requirements.txt` | Add `rq`, `redis` packages |
| `/src/workflow/WorkflowManager.py` | Add queue submission logic |
| `/src/workflow/StreamlitUI.py` | Add queue status display |
| `/settings.json` | Add queue configuration section |

---

## Configuring Worker Count

### Why Multiple Workers?

Each RQ worker can process **one job at a time**. With a single worker, users must wait for the previous workflow to complete before theirs can start. Multiple workers allow parallel execution.

| Workers | Concurrent Jobs | Use Case |
|---------|-----------------|----------|
| 1 | 1 | Development, low-traffic deployments |
| 2-3 | 2-3 | Small team, moderate usage |
| 4-8 | 4-8 | Production, high traffic |

### Configuration Methods

#### Method 1: Environment Variable (Recommended)

Set `RQ_WORKER_COUNT` in docker-compose.yml or the entrypoint:

```yaml
# docker-compose.yml
environment:
  - REDIS_URL=redis://localhost:6379/0
  - RQ_WORKER_COUNT=3  # Number of workers to start
```

Update entrypoint.sh to read this variable:

```bash
#!/bin/bash
# ... Redis startup ...

# Start RQ workers based on environment variable
WORKER_COUNT=${RQ_WORKER_COUNT:-1}
echo "Starting $WORKER_COUNT RQ worker(s)..."

for i in $(seq 1 $WORKER_COUNT); do
    rq worker openms-workflows --url redis://localhost:6379/0 --name worker-$i &
done

# Start Streamlit
exec streamlit run app.py
```

#### Method 2: Supervisord Configuration

For more robust process management with automatic restart:

```ini
# supervisord.conf
[program:rq-worker]
command=rq worker openms-workflows --url redis://localhost:6379/0
directory=/openms-streamlit-template
numprocs=%(ENV_RQ_WORKER_COUNT)s  # Read from environment
process_name=worker-%(process_num)02d
autostart=true
autorestart=true
startsecs=5
```

#### Method 3: Settings File

Add to settings.json for runtime configuration:

```json
{
    "queue_settings": {
        "worker_count": 2
    }
}
```

### Resource Considerations

Each worker consumes memory for:
- Python interpreter (~100-200MB base)
- pyOpenMS/TOPP tools during execution (~500MB-2GB depending on workflow)
- Input/output file processing

**Recommended formula:**
```
max_workers = (available_memory - 2GB) / 1.5GB
```

Example: 8GB container → max 4 workers

---

## User Experience: Queue Status Display

### What Users See When Queued

When a user starts a workflow and it enters the queue, they need clear feedback:

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow Execution                                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  🟡 Status: Queued                                          │
│                                                              │
│  Your workflow is #3 in the queue                           │
│  Estimated wait: ~5-10 minutes                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Queue Position    ███░░░░░░░░░░░░░░░░░  3 of 5     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  [Cancel Workflow]                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Status States and UI Feedback

| Status | Icon | Message | UI Elements |
|--------|------|---------|-------------|
| **Queued** | 🟡 | "Your workflow is #N in queue" | Position indicator, cancel button |
| **Starting** | 🔵 | "Workflow is starting..." | Spinner |
| **Running** | 🔵 | "Workflow in progress" | Progress bar, log viewer, stop button |
| **Completed** | 🟢 | "Workflow completed successfully" | View results button |
| **Failed** | 🔴 | "Workflow failed" | Error details, retry button |
| **Cancelled** | ⚪ | "Workflow was cancelled" | Restart button |

### Implementation: Queue Status UI

**File:** `/src/workflow/StreamlitUI.py` (additions)

```python
def _show_queue_status(self, status: dict) -> None:
    """Display detailed queue status to user"""
    job_status = status.get("status", "unknown")

    # Status icons and colors
    status_display = {
        "queued": ("🟡", "Queued", "warning"),
        "started": ("🔵", "Running", "info"),
        "finished": ("🟢", "Completed", "success"),
        "failed": ("🔴", "Failed", "error"),
        "canceled": ("⚪", "Cancelled", "secondary"),
    }

    icon, label, color = status_display.get(job_status, ("⚪", "Unknown", "secondary"))

    # Main status display
    st.markdown(f"### {icon} Status: {label}")

    # Queue-specific information
    if job_status == "queued":
        queue_position = status.get("queue_position", "?")
        queue_length = status.get("queue_length", "?")

        st.info(f"Your workflow is **#{queue_position}** in the queue ({queue_length} total)")

        # Visual queue indicator
        if isinstance(queue_position, int) and isinstance(queue_length, int):
            progress = 1 - (queue_position / max(queue_length, 1))
            st.progress(progress, text=f"Position {queue_position} of {queue_length}")

        # Estimate wait time (rough: 5 min per job ahead)
        if isinstance(queue_position, int):
            wait_min = (queue_position - 1) * 5
            if wait_min > 0:
                st.caption(f"Estimated wait: ~{wait_min}-{wait_min + 10} minutes")

    # Running status with progress
    elif job_status == "started":
        progress = status.get("progress", 0)
        current_step = status.get("current_step", "Processing...")

        st.progress(progress, text=current_step)

    # Expandable job details
    with st.expander("Job Details", expanded=False):
        st.code(f"""Job ID: {status.get('job_id', 'N/A')}
Submitted: {status.get('enqueued_at', 'N/A')}
Started: {status.get('started_at', 'N/A')}
Workers Active: {status.get('active_workers', 'N/A')}""")
```

---

## Sidebar Metrics (Online Mode)

### Metrics to Display

In online mode, enhance the existing CPU/RAM sidebar with queue metrics:

```
┌─────────────────────────┐
│  System Status          │
├─────────────────────────┤
│  CPU    ████░░░░  45%   │
│  RAM    ██████░░  72%   │
├─────────────────────────┤
│  Queue Status           │
├─────────────────────────┤
│  Workers   2/3 busy     │
│  Queued    5 jobs       │
│  Running   2 jobs       │
└─────────────────────────┘
```

### Implementation: Sidebar Queue Metrics

**File:** `/src/common/common.py` (additions to `render_sidebar()`)

```python
def render_queue_metrics() -> None:
    """Display queue metrics in sidebar (online mode only)"""
    if not st.session_state.settings.get("online_deployment", False):
        return

    try:
        from src.workflow.QueueManager import QueueManager
        qm = QueueManager()

        if not qm.is_available:
            return

        stats = qm.get_queue_stats()
        if not stats:
            return

        st.sidebar.markdown("---")
        st.sidebar.markdown("**Queue Status**")

        # Worker status
        total_workers = stats.get("workers", 0)
        busy_workers = stats.get("started", 0)

        col1, col2 = st.sidebar.columns(2)
        col1.metric("Workers", f"{busy_workers}/{total_workers}",
                    delta=None,
                    help="Active workers / Total workers")

        # Queue depth
        queued = stats.get("queued", 0)
        col2.metric("Queued", queued,
                    delta=None,
                    help="Jobs waiting in queue")

        # Visual indicator
        if total_workers > 0:
            utilization = busy_workers / total_workers
            st.sidebar.progress(utilization, text=f"{int(utilization*100)}% utilized")

        # Warning if queue is backing up
        if queued > total_workers * 2:
            st.sidebar.warning(f"High queue depth: {queued} jobs waiting")

    except Exception:
        pass  # Silently fail if queue not available


def render_sidebar() -> None:
    """Existing sidebar render function - add queue metrics"""
    # ... existing sidebar code ...

    # Add queue metrics for online mode
    render_queue_metrics()
```

### Available Metrics

| Metric | Description | Source |
|--------|-------------|--------|
| **Workers Total** | Number of RQ workers running | `Worker.count()` |
| **Workers Busy** | Workers currently processing | `started_job_registry` |
| **Queue Depth** | Jobs waiting to be processed | `len(queue)` |
| **Jobs Running** | Jobs currently being processed | `started_job_registry` |
| **Jobs Completed** | Recent completed jobs | `finished_job_registry` |
| **Jobs Failed** | Recent failed jobs | `failed_job_registry` |
| **Avg Wait Time** | Average time in queue | Calculated from job metadata |
| **Avg Run Time** | Average execution time | Calculated from job metadata |

### Extended Metrics (Optional)

For more detailed monitoring, add a dedicated metrics endpoint:

```python
def get_detailed_queue_metrics() -> dict:
    """Get comprehensive queue metrics"""
    from rq import Queue, Worker
    from redis import Redis

    redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    queue = Queue("openms-workflows", connection=redis)
    workers = Worker.all(connection=redis)

    return {
        # Capacity
        "total_workers": len(workers),
        "idle_workers": len([w for w in workers if w.get_state() == "idle"]),
        "busy_workers": len([w for w in workers if w.get_state() == "busy"]),

        # Queue state
        "queued_jobs": len(queue),
        "started_jobs": len(queue.started_job_registry),
        "finished_jobs_24h": len(queue.finished_job_registry),
        "failed_jobs_24h": len(queue.failed_job_registry),

        # Performance (if tracking)
        "avg_wait_time_sec": _calculate_avg_wait_time(queue),
        "avg_run_time_sec": _calculate_avg_run_time(queue),

        # Health
        "redis_connected": redis.ping(),
        "redis_memory_mb": redis.info().get("used_memory_human", "N/A"),
    }
```

---

## Deployment Considerations

### Scaling Workers (Within Container)

You can run multiple RQ workers within the same container by modifying the entrypoint:

```bash
# Start multiple workers (in entrypoint.sh)
WORKER_COUNT=${RQ_WORKER_COUNT:-1}
for i in $(seq 1 $WORKER_COUNT); do
    rq worker openms-workflows --url redis://localhost:6379/0 --name worker-$i &
done
```

Or with supervisord, add multiple worker programs:

```ini
[program:rq-worker]
command=rq worker openms-workflows --url redis://localhost:6379/0
numprocs=%(ENV_RQ_WORKER_COUNT)s
process_name=%(program_name)s-%(process_num)02d
```

### Redis Persistence

Redis data is persisted using AOF (Append Only File):
```bash
redis-server --appendonly yes --dir /var/lib/redis
```

For container restarts, mount the Redis data directory:
```yaml
volumes:
  - redis-data:/var/lib/redis
```

### Resource Limits

```yaml
# In docker-compose.yml
openms-streamlit-template:
  deploy:
    resources:
      limits:
        cpus: '4'
        memory: 8G
```

### Monitoring

- **RQ Dashboard**: Enable in entrypoint, access at port 9181
- **Redis CLI**: `docker exec -it openms-streamlit-template redis-cli`
- **Worker Status**: `docker exec -it openms-streamlit-template rq info`
- **All Logs**: `docker logs openms-streamlit-template`

---

## Migration Path

### Phase 1: Infrastructure
- Update Dockerfile to install Redis server and RQ
- Create entrypoint script to start all services
- Update requirements.txt
- Build and verify container starts correctly with all services

### Phase 2: Core Implementation
- Implement QueueManager class
- Implement worker tasks module
- Add health check utilities

### Phase 3: Integration
- Modify WorkflowManager to use queue in online mode
- Update StreamlitUI for queue status display
- Test execution flow end-to-end

### Phase 4: Testing & Polish
- Comprehensive testing across all scenarios
- Verify local mode still works unchanged
- Documentation updates

---

## Rollback Plan

If issues arise, the system can fall back to local execution:

1. Set `queue_settings.enabled = false` in settings.json
2. Or remove REDIS_URL environment variable
3. The WorkflowManager will automatically use multiprocessing fallback

The entrypoint can also be modified to skip Redis/RQ startup entirely if needed.

---

## Future Enhancements

1. **Priority Queues**: Separate queues for different workflow types
2. **Job Scheduling**: Delayed job execution
3. **Email Notifications**: Notify users when long jobs complete
4. **Job Dependencies**: Chain workflows together
5. **Resource Quotas**: Limit jobs per user/workspace
6. **Multi-Container Scaling**: If needed later, extract workers to separate containers

---

## Appendix: Testing Checklist

- [ ] Container starts with Redis, RQ worker, and Streamlit all running
- [ ] `redis-cli ping` returns PONG inside container
- [ ] `rq info` shows worker registered
- [ ] Job submission from Streamlit succeeds
- [ ] Job status updates in real-time
- [ ] Job completion triggers correct callbacks
- [ ] Job cancellation works
- [ ] Failed jobs are handled gracefully
- [ ] Local mode (non-Docker) still works with multiprocessing fallback
- [ ] Workspace cleanup cron still functions correctly
- [ ] Logs are written correctly from worker
- [ ] Multiple concurrent jobs execute properly
- [ ] Container restart recovers Redis state (if persistence enabled)
