from pathlib import Path
from typing import Optional
from .Logger import Logger
from .ParameterManager import ParameterManager
from .CommandExecutor import CommandExecutor
from .StreamlitUI import StreamlitUI
from .FileManager import FileManager
from .RunManager import RunManager, FINISHED, FAILED, CANCELLED, RUNNING
import multiprocessing
import streamlit as st
import shutil
import time
import traceback

class WorkflowManager:
    # Keep every run as its own named result set in <workflow_dir>/runs/<id>/
    # instead of overwriting <workflow_dir>/results/. Set to True in a subclass
    # to opt in, and read and write results through self.results_dir.
    multi_run = False

    # Core workflow logic using the above classes
    def __init__(self, name: str, workspace: str):
        self.name = name
        self.workflow_dir = Path(workspace, name.replace(" ", "-").lower())
        # Where execution() writes and results() reads. For a multi-run
        # workflow this is the results folder of the run the pages show.
        self.results_dir = Path(self.workflow_dir, "results")
        self.run_id = None
        self.runs = None
        if self.multi_run:
            from .run_widgets import get_selected_run

            self.runs = RunManager(self.workflow_dir)
            self.runs.adopt_legacy_results()
            self.run_id = get_selected_run(self.runs)
            if self.run_id:
                self.results_dir = self.runs.results_dir(self.run_id)
        self.file_manager = FileManager(self.workflow_dir, self.results_dir)
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
        # Flush the latest session state to params.json so the worker
        # (queued) or the forked child (local) sees the values the user
        # just selected, not stale disk state from a previous fragment run.
        self.parameter_manager.save_parameters()
        if self.multi_run:
            self._new_run()
        if self._queue_manager and self._queue_manager.is_available:
            self._start_workflow_queued()
        else:
            self._start_workflow_local()

    def _new_run(self) -> None:
        """Create the run this start writes into, and show it on the results pages."""
        from .run_widgets import run_name_key, set_selected_run

        name = st.session_state.pop(run_name_key(self.runs), "")
        self.run_id = self.runs.new_run(name, Path(self.workflow_dir, "params.json"))
        self._use_run(self.run_id)
        set_selected_run(self.runs, self.run_id)

    def _use_run(self, run_id: str) -> None:
        """Point results_dir (and the FileManager) at a run."""
        self.run_id = run_id
        self.results_dir = self.runs.results_dir(run_id)
        self.file_manager.results_dir = self.results_dir

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
                "run_id": self.run_id if self.multi_run else None,
            },
            job_id=job_id,
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
        self.executor.pid_dir.mkdir(exist_ok=True)
        try:
            Path(self.executor.pid_dir, str(workflow_process.pid)).touch()
        except FileNotFoundError:
            # The workflow already ended (e.g. no input files) and removed the
            # pid dir; there is nothing left to track.
            pass

    def workflow_process(self) -> None:
        """
        Workflow process. Logs start and end of the workflow and calls the execution method where all steps are defined.
        """
        success = False
        try:
            self.logger.log("STARTING WORKFLOW")
            if self.multi_run:
                # A fresh folder made by _new_run(); earlier runs stay untouched.
                self.results_dir.mkdir(parents=True, exist_ok=True)
            else:
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
        if self.multi_run:
            self.runs.finish(self.run_id, FINISHED if success else FAILED)
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

        Writes a "WORKFLOW CANCELLED" marker to the log so the static
        run-page display can render a "Workflow was cancelled" message
        instead of "Errors occurred". Cleans up the worker-side pid_dir
        left behind when the RQ worker is force-stopped, so a subsequent
        get_workflow_status does not flip running back to True via the
        local-mode fallback.

        .job_id is intentionally left in place: get_job_info will report
        the canceled status to the UI so _show_queue_status can render the
        Cancelled pill. Resubmission overwrites it; RQ's result_ttl
        eventually evicts the job and get_workflow_status self-heals.

        Returns:
            True if a stop action was taken (queue cancel or local kill).
        """
        # Try to cancel queue job first (online mode)
        if self._queue_manager and self._queue_manager.is_available:
            job_id = self._queue_manager.load_job_id(self.workflow_dir)
            if job_id:
                if self._queue_manager.cancel_job(job_id):
                    self.logger.log("WORKFLOW CANCELLED")
                    shutil.rmtree(self.executor.pid_dir, ignore_errors=True)
                    self._mark_running_runs_cancelled()
                    return True

        # Fallback: stop local process
        stopped = self._stop_local_workflow()
        if stopped:
            self._mark_running_runs_cancelled()
        return stopped

    def _mark_running_runs_cancelled(self) -> None:
        # The stopped process can not record how its run ended, so do it here.
        if self.multi_run:
            for run in self.runs.list_runs(RUNNING):
                self.runs.finish(run["id"], CANCELLED)

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
        if stopped:
            self.logger.log("WORKFLOW CANCELLED")
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
        if self.multi_run:
            from .run_widgets import run_name_input

            run_name_input(self.runs, disabled=self.get_workflow_status()["running"])
        self.ui.execution_section(
            start_workflow_function=self.start_workflow,
            get_status_function=self.get_workflow_status,
            stop_workflow_function=self.stop_workflow
        )
        
    def show_results_section(self) -> None:
        """
        Shows the results section of the UI with content defined in self.results().

        A multi-run workflow first shows a run picker and points
        self.results_dir at the chosen run.
        """
        if self.multi_run and not self.select_run():
            st.info("No finished runs yet. Start the workflow on the **Run** page.")
            return
        self.ui.results_section(self.results)

    def select_run(self, label: str = "Run", key: str = "") -> str | None:
        """
        Multi-run workflows: show a picker for the run to display, point
        self.results_dir at it and return its id (None if no run finished yet).
        The choice is shared by all pages of the workflow.
        """
        from .run_widgets import select_run

        run_id = select_run(self.runs, label=label, key=key)
        if run_id:
            self._use_run(run_id)
        return run_id

    def select_runs(self, label: str = "Runs", key: str = "") -> list[str]:
        """
        Multi-run workflows: let the user pick several finished runs, e.g. to
        compare them side by side. Returns their ids; read each one's files
        from self.runs.results_dir(run_id).
        """
        from .run_widgets import select_run

        return select_run(self.runs, label=label, multiple=True, key=key)

    def show_run_manager_section(self, exclude: list[str] | None = None) -> None:
        """
        Multi-run workflows: list every run with buttons to show, rename,
        download (ZIP of results, parameters and logs) and delete it.
        """
        from .run_widgets import run_manager_section

        run_manager_section(
            self.runs,
            workflow_running=self.get_workflow_status()["running"],
            exclude=exclude,
        )

    def show_results_download_section(self, exclude: list[str] | None = None) -> None:
        """
        Shows a page offering every file in the workflow's results directory for
        download, singly or as a ZIP. Pass ``exclude`` to hide folders or files
        that are not results, such as visualization caches.

        A multi-run workflow lists its runs first (show, rename, download,
        delete), then offers the files of the run picked below.
        """
        if self.multi_run:
            st.markdown("#### Runs")
            self.show_run_manager_section(exclude=exclude)
            st.markdown("#### Files of one run")
            if not self.select_run():
                return
        self.ui.results_download_section(
            exclude=exclude, results_dir=self.results_dir
        )

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