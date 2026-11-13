"""
Worker tasks for Redis Queue execution.

These functions are executed by RQ workers and should not import Streamlit.
This module must be importable without Streamlit being available.
"""

import os
import sys
import json
import shutil
import traceback
from pathlib import Path


class WorkerBuildMismatchError(RuntimeError):
    """
    Raised when the worker runs other code than the page that queued the job.

    The page's parameters (and the TOPP .ini files it wrote) belong to its own
    TOPP tools; running them with the worker's tools fails with an error that
    does not name the cause. See src/workflow/app_build.py.
    """


class WorkflowExecutionError(RuntimeError):
    """
    Raised when a workflow's execution() reports failure by returning False.

    RQ records a job as failed only if the job function raises, so an
    application level failure has to be turned into an exception here.
    Returning a result dict instead leaves the FailedJobRegistry empty and
    health.py's failed_jobs metric structurally zero.
    """


def execute_workflow(
    workflow_dir: str,
    workflow_class: str,
    workflow_module: str,
    run_id: str | None = None,
) -> dict:
    """
    Execute a workflow in the worker process.

    This function is called by the RQ worker to execute a workflow.
    It reconstructs the workflow object and calls its execution() method.

    Args:
        workflow_dir: Path to the workflow directory
        workflow_class: Name of the Workflow class
        workflow_module: Module path containing the Workflow class
        run_id: For a multi-run workflow, the run (created by the UI in
            <workflow_dir>/runs/) this job writes into. None writes into
            <workflow_dir>/results, which is cleared first.

    Returns:
        Dictionary with execution results

    Raises:
        Exception: Anything raised while setting up or running the workflow is
            re-raised after the failure has been written to the workflow logs,
            a WorkerBuildMismatchError (before anything runs) if the page that
            queued the job runs other code than this worker, and a
            WorkflowExecutionError if execution() returned False. RQ
            needs the job function to raise to record the job as failed. A
            legacy execution() returning None is accepted as success with a
            deprecation warning in the workflow log.
    """
    try:
        from rq import get_current_job
        job = get_current_job()
    except Exception:
        job = None

    workflow_path = Path(workflow_dir)
    runs = None

    try:
        # Update progress
        _update_progress(job, 0.0, "Initializing workflow...")

        # Import required modules
        # Load the workflow class dynamically
        import importlib

        from src.workflow.CommandExecutor import CommandExecutor
        from src.workflow.FileManager import FileManager
        from src.workflow.Logger import Logger
        from src.workflow.ParameterManager import ParameterManager
        from src.workflow.RunManager import RunManager
        module = importlib.import_module(workflow_module)
        WorkflowClass = getattr(module, workflow_class)

        _update_progress(job, 0.05, "Loading parameters...")

        # Delete the log file if it already exists
        shutil.rmtree(Path(workflow_path, "logs"), ignore_errors=True)

        # Refuse a job queued by a page that runs other code than this worker
        # (a release that reached the web pods but not the worker pods).
        from src.workflow.app_build import build_mismatch
        mismatch = build_mismatch((job.meta or {}).get("app_build") if job else None)
        if mismatch:
            raise WorkerBuildMismatchError(mismatch)

        # Load parameters from saved params.json. A run of a multi-run
        # workflow reads the copy taken when it was started (RunManager.new_run)
        # instead, so a change saved on the configure page while the run is
        # going does not leak into it and the run's params.json stays the
        # record of what produced its results.
        params_file = workflow_path / "params.json"
        if run_id:
            runs = RunManager(workflow_path)
            if runs.params_file(run_id).exists():
                params_file = runs.params_file(run_id)
        if params_file.exists():
            # encoding="utf-8" explicitly, matching every other reader and
            # writer of params.json: the platform codepage here would decode a
            # file written elsewhere differently, or fail outright.
            with open(params_file, "r", encoding="utf-8") as f:
                params = json.load(f)
        else:
            params = {}

        # Initialize workflow components
        logger = Logger(workflow_path)
        if run_id:
            results_dir = runs.results_dir(run_id)
        else:
            results_dir = workflow_path / "results"
        file_manager = FileManager(workflow_path, results_dir)
        parameter_manager = ParameterManager(workflow_path)
        # run_topp / run_python read the parameters through the
        # ParameterManager while the run goes on: the same file as above.
        parameter_manager.params_file = params_file
        executor = CommandExecutor(workflow_path, logger, parameter_manager)
        executor.pid_dir.mkdir(parents=True, exist_ok=True)
        if job is not None:
            # Record the work-horse too, not only its native tool children.
            # Local queue recovery must not admit another analysis in the
            # gaps between commands while this worker is still active.
            from src.workflow.process_state import register_process_marker

            register_process_marker(executor.pid_dir / str(os.getpid()), os.getpid())

        _update_progress(job, 0.1, "Starting workflow execution...")

        # Create workflow instance
        # We need to bypass the normal __init__ which requires Streamlit
        workflow = object.__new__(WorkflowClass)
        workflow.name = workflow_path.name
        workflow.workflow_dir = workflow_path
        workflow.file_manager = file_manager
        workflow.logger = logger
        workflow.parameter_manager = parameter_manager
        workflow.executor = executor
        workflow.params = params
        workflow.results_dir = results_dir
        workflow.run_id = run_id
        workflow.runs = runs

        # Store job reference for progress updates
        workflow._rq_job = job

        # Clear results directory. A run's folder is new and stays as it is.
        if run_id is None and results_dir.exists():
            shutil.rmtree(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)

        # Log workflow start
        logger.log("STARTING WORKFLOW")
        if job is not None and getattr(job, "timeout", None):
            from src.workflow.job_timeout import format_duration
            logger.log(f"Time limit of this run: {format_duration(job.timeout)}")

        _update_progress(job, 0.15, "Executing workflow steps...")

        # Execute the workflow. It reports success with a bool
        # (WorkflowManager.execution is declared -> bool), same as the local
        # mode in WorkflowManager.workflow_process.
        success = workflow.execution()

        if success is None:
            # Migration shim for workflows written against the older example,
            # which was annotated -> None and returned nothing. Those
            # subclasses live in downstream repositories (quantms-web,
            # umetaflow, FLASHApp) and cannot be fixed in the same commit as
            # this file, so treating their None as a failure would report every
            # successful queued run as failed the moment they rebase. Accepted
            # as success, loudly, so they have a runway; explicit False is
            # still a failure.
            logger.log(
                "WARNING: execution() returned None and was treated as success. "
                "Annotate it '-> bool' and return True on success / False on "
                "failure - see .claude/skills/create-workflow.md. A future "
                "release will treat None as a failure.",
                0,
            )
        elif not success:
            raise WorkflowExecutionError(
                f"Workflow execution reported failure (returned {success!r})"
            )

        # Log workflow completion. Only write the marker for a run which
        # actually succeeded, it is what classify_log_outcome reads to tell a
        # finished run from a failed one.
        logger.log("WORKFLOW FINISHED")
        if runs is not None:
            runs.finish(run_id, "finished")

        _update_progress(job, 1.0, "Workflow completed")

        # Clean up pid directory (in case it was created by accident)
        shutil.rmtree(executor.pid_dir, ignore_errors=True)

        return {
            "success": True,
            "workflow_dir": str(workflow_path),
            "message": "Workflow completed successfully"
        }

    except Exception as e:
        # Log error to workflow logs
        try:
            log_dir = workflow_path / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            message = str(e)
            if _is_timeout(e):
                # The queue's time limit (job_timeout.py), not a crash: say
                # so, and end the tools it leaves running.
                from src.workflow.job_timeout import format_duration
                limit = getattr(job, "timeout", None) if job is not None else None
                message = (
                    "The run took longer than its time limit"
                    + (f" of {format_duration(limit)}" if limit else "")
                    + " and was stopped.\nA longer limit: "
                    "queue_settings.timeout_per_input and max_timeout in settings.json."
                )
                _end_tools(workflow_path / "pids")
            for log_name in ["minimal.log", "commands-and-run-times.log", "all.log"]:
                log_file = log_dir / log_name
                with open(log_file, "a") as f:
                    f.write(f"\n\nERROR: {message}\n")
                    # A workflow reporting failure by returning False is not a
                    # crash, the reason is in the tool output above.
                    if not isinstance(e, (WorkflowExecutionError, WorkerBuildMismatchError)) and not _is_timeout(e):
                        f.write(traceback.format_exc())
        except Exception:
            pass

        try:
            if runs is not None:
                runs.finish(run_id, "failed")
        except Exception:
            pass

        # Clean up pid directory
        try:
            pid_dir = workflow_path / "pids"
            shutil.rmtree(pid_dir, ignore_errors=True)
        except Exception:
            pass

        # Re-raise so RQ moves the job into the FailedJobRegistry. Returning a
        # {"success": False} dict here looked like a normal return to RQ, which
        # recorded every crashed workflow as finished successfully.
        raise


def _is_timeout(e: BaseException) -> bool:
    """RQ's JobTimeoutException (by name: rq is not importable everywhere)."""
    return type(e).__name__ == "JobTimeoutException"


def _end_tools(pid_dir: Path) -> None:
    """SIGTERM the tools a run started (pids/<pid>), which outlive a timed-out job.

    Only processes whose marker proves they are the ones this run started are
    signalled (a reused PID is left alone), and never this work-horse itself,
    whose own marker sits in the same folder.
    """
    import signal
    from src.workflow.process_state import pid_markers, signal_owned_process
    try:
        markers = pid_markers(pid_dir)
    except OSError:
        return
    for marker in markers:
        if marker.name == str(os.getpid()):
            continue
        try:
            signal_owned_process(marker, signal.SIGTERM)
        except PermissionError:
            pass


def _update_progress(job, progress: float, step: str) -> None:
    """Update job progress metadata"""
    if job is not None:
        try:
            job.meta["progress"] = progress
            job.meta["current_step"] = step
            job.save_meta()
        except Exception:
            pass  # Ignore errors updating progress
