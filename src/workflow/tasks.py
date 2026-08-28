"""
Worker tasks for Redis Queue execution.

These functions are executed by RQ workers and should not import Streamlit.
This module must be importable without Streamlit being available.
"""

import sys
import json
import shutil
import traceback
from pathlib import Path


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
) -> dict:
    """
    Execute a workflow in the worker process.

    This function is called by the RQ worker to execute a workflow.
    It reconstructs the workflow object and calls its execution() method.

    Args:
        workflow_dir: Path to the workflow directory
        workflow_class: Name of the Workflow class
        workflow_module: Module path containing the Workflow class

    Returns:
        Dictionary with execution results

    Raises:
        Exception: Anything raised while setting up or running the workflow is
            re-raised after the failure has been written to the workflow logs,
            and a WorkflowExecutionError if execution() returned False. RQ
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

    try:
        # Update progress
        _update_progress(job, 0.0, "Initializing workflow...")

        # Import required modules
        from src.workflow.CommandExecutor import CommandExecutor
        from src.workflow.FileManager import FileManager
        from src.workflow.ParameterManager import ParameterManager
        from src.workflow.Logger import Logger

        # Load the workflow class dynamically
        import importlib
        module = importlib.import_module(workflow_module)
        WorkflowClass = getattr(module, workflow_class)

        _update_progress(job, 0.05, "Loading parameters...")

        # Delete the log file if it already exists
        shutil.rmtree(Path(workflow_path, "logs"), ignore_errors=True)

        # Load parameters from saved params.json
        params_file = workflow_path / "params.json"
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
        file_manager = FileManager(workflow_path)
        parameter_manager = ParameterManager(workflow_path)
        executor = CommandExecutor(workflow_path, logger, parameter_manager)
        executor.pid_dir.mkdir(parents=True, exist_ok=True)

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

        # Store job reference for progress updates
        workflow._rq_job = job

        # Clear results directory
        results_dir = workflow_path / "results"
        if results_dir.exists():
            shutil.rmtree(results_dir)
        results_dir.mkdir(parents=True)

        # Log workflow start
        logger.log("STARTING WORKFLOW")

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

            for log_name in ["minimal.log", "commands-and-run-times.log", "all.log"]:
                log_file = log_dir / log_name
                with open(log_file, "a") as f:
                    f.write(f"\n\nERROR: {str(e)}\n")
                    # A workflow reporting failure by returning False is not a
                    # crash, the reason is in the tool output above.
                    if not isinstance(e, WorkflowExecutionError):
                        f.write(traceback.format_exc())
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


def _update_progress(job, progress: float, step: str) -> None:
    """Update job progress metadata"""
    if job is not None:
        try:
            job.meta["progress"] = progress
            job.meta["current_step"] = step
            job.save_meta()
        except Exception:
            pass  # Ignore errors updating progress
