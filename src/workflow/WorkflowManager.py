from pathlib import Path
from typing import Optional
from .Logger import Logger
from .ParameterManager import ParameterManager
from .CommandExecutor import CommandExecutor
from .StreamlitUI import StreamlitUI
from .FileManager import FileManager
import multiprocessing
import streamlit as st
import shutil
import time
import traceback

class WorkflowManager:
    # Core workflow logic using the above classes
    def __init__(self, name: str, workspace: str):
        self.name = name
        self.workflow_dir = Path(workspace, name.replace(" ", "-").lower())
        self.file_manager = FileManager(self.workflow_dir)
        self.logger = Logger(self.workflow_dir)
        self.parameter_manager = ParameterManager(self.workflow_dir, workflow_name=name)
        self.executor = CommandExecutor(self.workflow_dir, self.logger, self.parameter_manager)
        self.ui = StreamlitUI(self.workflow_dir, self.logger, self.executor, self.parameter_manager)
        self.params = self.parameter_manager.get_parameters_from_json()

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
            from .QueueManager import QueueManager
            self._queue_manager = QueueManager()
        except ImportError:
            pass  # Queue not available, will use fallback

    def start_workflow(self) -> None:
        """
        Starts the workflow process.

        Online mode: Submits to Redis queue
        Local mode: Spawns multiprocessing.Process (existing behavior)
        """
        if self._queue_manager and self._queue_manager.is_available:
            self._start_workflow_queued()
        else:
            self._start_workflow_local()

    def _start_workflow_queued(self) -> None:
        """Submit workflow to Redis queue (online mode)"""
        from .tasks import execute_workflow

        # Generate unique job ID based on workflow directory
        job_id = f"workflow-{self.workflow_dir.name}-{int(time.time())}"

        # Submit job to queue
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
        else:
            # Fallback to local execution if queue submission fails
            st.warning("Queue submission failed, running locally...")
            self._start_workflow_local()

    def _start_workflow_local(self) -> None:
        """Start workflow as local process (existing behavior for local mode)"""
        # Delete the log file if it already exists
        shutil.rmtree(Path(self.workflow_dir, "logs"), ignore_errors=True)
        # Start workflow process
        workflow_process = multiprocessing.Process(target=self.workflow_process)
        workflow_process.start()
        # Add workflow process id to pid dir
        self.executor.pid_dir.mkdir()
        Path(self.executor.pid_dir, str(workflow_process.pid)).touch()

    def workflow_process(self) -> None:
        """
        Workflow process. Logs start and end of the workflow and calls the execution method where all steps are defined.
        """
        try:
            self.logger.log("STARTING WORKFLOW")
            results_dir = Path(self.workflow_dir, "results")
            if results_dir.exists():
                shutil.rmtree(results_dir)
            results_dir.mkdir(parents=True)
            success = self.execution()
            if success:
                self.logger.log("WORKFLOW FINISHED")
        except Exception as e:
            self.logger.log(f"ERROR: {e}")
            self.logger.log("".join(traceback.format_exception(e)))
        # Delete pid dir path to indicate workflow is done
        shutil.rmtree(self.executor.pid_dir, ignore_errors=True)

    def get_workflow_status(self) -> dict:
        """
        Get current workflow execution status.

        Returns:
            Dictionary with status information including:
            - running: bool indicating if workflow is running
            - status: string status (queued, started, finished, failed, idle)
            - progress: float 0-1 for queue jobs, None for local
            - current_step: string description of current step
            - job_id: job ID for queue jobs, None for local
            - queue_position: position in queue (1-indexed), None if not queued
            - queue_length: total jobs in queue, None if not queued
        """
        # Check queue status first (online mode)
        if self._queue_manager and self._queue_manager.is_available:
            job_id = self._queue_manager.load_job_id(self.workflow_dir)
            if job_id:
                job_info = self._queue_manager.get_job_info(job_id)
                if job_info:
                    is_running = job_info.status.value in ["queued", "started"]
                    return {
                        "running": is_running,
                        "status": job_info.status.value,
                        "progress": job_info.progress,
                        "current_step": job_info.current_step,
                        "job_id": job_id,
                        "queue_position": job_info.queue_position,
                        "queue_length": job_info.queue_length,
                        "enqueued_at": job_info.enqueued_at,
                        "started_at": job_info.started_at,
                        "result": job_info.result,
                        "error": job_info.error,
                    }
                else:
                    # Job not found, clear the stored job ID
                    self._queue_manager.clear_job_id(self.workflow_dir)

        # Fallback: check PID files (local mode)
        pid_dir = self.executor.pid_dir
        if pid_dir.exists() and list(pid_dir.iterdir()):
            return {
                "running": True,
                "status": "running",
                "progress": None,
                "current_step": None,
                "job_id": None,
                "queue_position": None,
                "queue_length": None,
            }

        return {
            "running": False,
            "status": "idle",
            "progress": None,
            "current_step": None,
            "job_id": None,
            "queue_position": None,
            "queue_length": None,
        }

    def stop_workflow(self) -> bool:
        """
        Stop a running workflow.

        Returns:
            True if successfully stopped
        """
        # Try to cancel queue job first (online mode)
        if self._queue_manager and self._queue_manager.is_available:
            job_id = self._queue_manager.load_job_id(self.workflow_dir)
            if job_id:
                success = self._queue_manager.cancel_job(job_id)
                if success:
                    self._queue_manager.clear_job_id(self.workflow_dir)
                    return True

        # Fallback: stop local process
        return self._stop_local_workflow()

    def _stop_local_workflow(self) -> bool:
        """Stop locally running workflow process"""
        import os
        import signal

        pid_dir = self.executor.pid_dir
        if not pid_dir.exists():
            return False

        stopped = False
        for pid_file in pid_dir.iterdir():
            try:
                pid = int(pid_file.name)
                os.kill(pid, signal.SIGTERM)
                pid_file.unlink()
                stopped = True
            except (ValueError, ProcessLookupError, PermissionError):
                pid_file.unlink()  # Clean up stale PID file

        # Clean up the pid directory
        shutil.rmtree(pid_dir, ignore_errors=True)
        return stopped

    def show_file_upload_section(self) -> None:
        """
        Shows the file upload section of the UI with content defined in self.upload().
        """
        self.ui.file_upload_section(self.upload)
        
    def show_parameter_section(self) -> None:
        """
        Shows the parameter section of the UI with content defined in self.configure().
        """
        self.ui.parameter_section(self.configure)

    def show_execution_section(self) -> None:
        """
        Shows the execution section of the UI with content defined in self.execution().
        """
        self.ui.execution_section(
            start_workflow_function=self.start_workflow,
            get_status_function=self.get_workflow_status,
            stop_workflow_function=self.stop_workflow
        )
        
    def show_results_section(self) -> None:
        """
        Shows the results section of the UI with content defined in self.results().
        """
        self.ui.results_section(self.results)

    def upload(self) -> None:
        """
        Add your file upload widgets here
        """
        ###################################
        # Add your file upload widgets here
        ###################################
        pass

    def configure(self) -> None:
        """
        Add your input widgets here
        """
        ###################################
        # Add your input widgets here
        ###################################
        pass

    def execution(self) -> bool:
        """
        Add your workflow steps here.
        Returns True on success, False on error.
        """
        ###################################
        # Add your workflow steps here
        ###################################
        return True

    def results(self) -> None:
        """
        Display results here
        """
        ###################################
        # Display results here
        ###################################
        pass