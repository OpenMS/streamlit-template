import json
from pathlib import Path
from typing import Optional
from .Logger import Logger
from .ParameterManager import InvalidParameterFileError, ParameterManager
from .CommandExecutor import CommandExecutor
from .StreamlitUI import StreamlitUI
from .FileManager import FileManager
from .input_check import clash_message, selection_clashes
from ._log_status import classify_log_outcome
from .RunManager import RunManager, FINISHED, FAILED, CANCELLED, RUNNING, FOLLOW_UP_KEY, FOLLOW_UP_FILE, RUN_NAME_KEY, RUN_NAME_FILE, MAX_NAME_LENGTH, apply_settings, same_files_info
from .pid_files import reap
from .process_state import local_workflow_running, owned_workflow_running, pid_markers, prune_exited_marker, register_process_marker, signal_owned_process
from .file_lock import file_lock
import multiprocessing
import streamlit as st
import shutil
import subprocess
import sys
import uuid
import traceback

# The app folder, which holds src/. Put first on sys.path in the workflow
# process (see _start_workflow_local).
_APP_ROOT = str(Path(__file__).resolve().parents[2])

# Runs one workflow in its own interpreter: argv is the app folder, then the
# arguments of execute_workflow, the function the queue worker runs.
_RUN_WORKFLOW = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from src.workflow.tasks import execute_workflow\n"
    "execute_workflow(*sys.argv[2:])\n"
)

class WorkflowManager:
    # Keep every run as its own named result set in <workflow_dir>/runs/<id>/
    # instead of overwriting <workflow_dir>/results/. Set to True in a subclass
    # to opt in, and read and write results through self.results_dir.
    multi_run = False
    # The page that shows a running start (its execution section), opened by
    # the Start button that settings adding files to an experiment draw on the
    # configure page. None: that button stays on the configure page.
    run_page = None
    # Draw a name field beside the Run button of the configure page
    # (show_run_button). Run folders always offer it; a workflow without them
    # sets this to True and reads the name in execution() with run_name().
    name_runs = False
    # How the notification at the end of a run names it ("<label> finished.");
    # None: the workflow's name.
    run_label = None
    # The configure page. A multi-run workflow that names it offers **Start
    # again with these settings** in the History of each run (start_again).
    configure_page = None

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
        Local mode: Runs the workflow in a separate Python process
        """
        # Two browser sessions can both render Start before either launches.
        # Serialize the check through PID/job registration, then release it;
        # the worker itself does not hold this short UI-operation lock.
        acquired = False
        try:
            with file_lock(self.workflow_dir / ".locks" / "execution.lock", blocking=False):
                acquired = True
                if self.get_workflow_status().get("running", False):
                    raise ValueError("This workflow is already running. Wait for it to finish or stop it before starting another analysis.")
                # Flush the latest session state to params.json so the worker
                # (queued) or the workflow process (local) sees the values the
                # user just selected, not stale disk state.
                if self.parameter_manager.save_parameters() is False:
                    raise ValueError("The current settings could not be saved. Correct the parameter error before starting.")
                problems = self.input_problems()
                if problems:
                    st.error(problems, icon=":material/block:")
                    return
                if self.multi_run:
                    self._new_run()
                else:
                    self._settle_follow_up()
                try:
                    if self._queue_manager and self._queue_manager.is_available:
                        self._start_workflow_queued()
                    else:
                        self._start_workflow_local()
                except OSError:
                    if self.multi_run:
                        self.runs.finish(self.run_id, FAILED)
                    raise
        except BlockingIOError as error:
            if acquired:
                raise  # A real launch/I/O failure is not lock contention.
            raise ValueError("Another session is starting or stopping this workflow. Wait a moment, then try again.") from error

    def input_problems(self) -> str:
        """Why the selected input files cannot be run as they are ("" when they can).

        Two selected files whose names differ only in folder, extension or
        case would write to the same result files (outputs are named after
        the inputs), so one would replace the other's results. A subclass may
        add checks of its own.
        """
        params = self.parameter_manager.get_parameters_from_json()
        found = selection_clashes(self.workflow_dir, params)
        return " ".join(clash_message(groups) for groups in found.values())

    def _settle_follow_up(self) -> None:
        """Without run folders: the start keeps which result it follows (for the
        processing report) and the name it was given, and the next settings
        start fresh."""
        params = self._stored_params()
        if params is None:
            return
        info = params.pop(FOLLOW_UP_KEY, None)
        name = params.pop(RUN_NAME_KEY, None)
        sidecar = Path(self.workflow_dir, FOLLOW_UP_FILE)
        if isinstance(info, dict):
            sidecar.write_text(json.dumps(info), encoding="utf-8")
        else:
            sidecar.unlink(missing_ok=True)
        name_file = Path(self.workflow_dir, RUN_NAME_FILE)
        if isinstance(name, str) and name.strip():
            name_file.write_text(name.strip(), encoding="utf-8")
        else:
            name_file.unlink(missing_ok=True)
        if info is not None or name is not None:
            self.parameter_manager.write_parameters(params)

    def _stored_params(self) -> Optional[dict]:
        """params.json for a read-modify-write, None (and logged) when it
        cannot be read: writing back a tolerant empty read would erase it."""
        try:
            return self.parameter_manager.read_parameters_strict()
        except InvalidParameterFileError as e:
            print(f"params.json not updated: {e}", file=sys.stderr)
            return None

    def run_name(self) -> str:
        """The name the running start was given, for ``execution()``; empty
        when none was given. A run keeps it as its name (its default name when
        none was given)."""
        if self.multi_run and getattr(self, "run_id", None):
            return (self.runs.get(self.run_id) or {}).get("name", "")
        try:
            return Path(self.workflow_dir, RUN_NAME_FILE).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def run_name_placeholder(self) -> str:
        """Shown in the empty name field beside the Run button."""
        if self.multi_run:
            return self.runs.default_name()
        return "Name (optional)"

    def _new_run(self) -> None:
        """Create the run this start writes into, and show it on the results pages."""
        from .run_widgets import clear_run_name, pending_run_name, set_selected_run

        # A failed read leaves params.json as it is (nothing written back)
        stored = self._stored_params()
        params = stored if stored is not None else {}
        # The name typed on the Run page, else the one given beside the Run
        # button of the configure page
        given = params.pop(RUN_NAME_KEY, None)
        name = pending_run_name(self.runs) or (given if isinstance(given, str) else "")
        if given is not None and stored is not None:
            self.parameter_manager.write_parameters(params)
        info = params.get(FOLLOW_UP_KEY)
        adds_to = info.get("adds_to") if isinstance(info, dict) else None
        self.run_id = self.runs.new_run(name, Path(self.workflow_dir, "params.json"), adds_to=adds_to)
        # The name is cleared only once the run exists, so a failed start keeps it
        clear_run_name(self.runs)
        # The run keeps which run it follows; the next settings start fresh
        if params.pop(FOLLOW_UP_KEY, None) is not None and stored is not None:
            self.parameter_manager.write_parameters(params)
        self._use_run(self.run_id)
        set_selected_run(self.runs, self.run_id)

    def follow_up(
        self,
        run_id: str,
        changes: Optional[dict] = None,
        page=None,
        note: str = "",
        add_files: Optional[str] = None,
        same_files: Optional[str] = None,
        keep: Optional[list] = None,
    ) -> bool:
        """Set up the next run from the settings ``run_id`` was started with.

        For an analysis a run is missing (identification after deconvolution
        only), more files, or a comparison with other runs: the parameters the
        user set for that run, and its experimental design, become the
        workflow's again, with ``changes`` on top (params.json keys, e.g.
        ``{"identify": True}`` or ``{"mzML-files": [...]}``; a TOPP tool's dict is
        merged). The configure page then says which run it starts from and
        ``note`` (what changed). ``page`` switches there (``st.switch_page``).
        Returns False if the run recorded no parameters.

        ``add_files`` (the params.json key of the input files) is for more
        files: that key starts empty, and the next run adds the files picked
        then to ``run_id``'s experiment, which the results pages show as one
        (``RunManager.experiment``), so the earlier files are not processed again.

        ``same_files`` (that key) is for an analysis added to ``run_id`` itself
        (identification of a run deconvolved only): the next run takes exactly
        its files, shown locked on the configure page, and ``keep`` names the
        tools whose results it reuses, shown as kept there in place of their
        settings. ``execution()`` finds the run in ``follow_up_info()["reuses"]``
        and takes those tools' results from it instead of running them.
        """
        if not self.multi_run or not self.runs.restore_settings(
                run_id, changes, note, add_files, same_files=same_files, keep=keep):
            return False
        self._reload_settings(page)
        return True

    def start_from(
        self,
        params: dict,
        changes: Optional[dict] = None,
        name: str = "",
        page=None,
        note: str = "",
        adds_to: Optional[list] = None,
        files: Optional[list] = None,
        files_key: Optional[str] = None,
        same_files: Optional[str] = None,
        keep: Optional[list] = None,
        reuses: Optional[list] = None,
    ) -> None:
        """``follow_up`` for an app without run folders: start from ``params``.

        ``params`` are the settings the earlier result was made with (as the
        app stored them), ``name`` names that result on the configure page.
        ``adds_to`` (the app's ids of earlier results, with their input
        ``files``) is for more files: the next run then adds to them, and
        ``execution()`` reads them with ``self.follow_up_info()``. ``files_key``
        (the params.json key of the input files) shows those files apart on the
        configure page, so only the files to add can be picked there.

        ``same_files`` (that key) instead keeps the input ``files`` of the
        results ``reuses`` (the app's ids), shown locked on the configure page,
        and ``keep`` names the tools whose results are reused (see ``follow_up``).
        """
        info = {"name": name, "note": note}
        if same_files:
            info.update(same_files_info(same_files, files or [], keep, reuses))
            changes = {**(changes or {}), same_files: list(files or [])}
        elif adds_to:
            info.update(adds_to=list(adds_to), files=list(files or []))
            if files_key:
                info["files_key"] = files_key
        apply_settings(self.workflow_dir, params, changes, info)
        self._reload_settings(page)

    def follow_up_info(self) -> dict:
        """What the running start follows (``start_from``), for ``execution()``.

        Without run folders the start keeps it apart from params.json (so the
        next settings start fresh), a run keeps it in its own parameters;
        empty when the start followed nothing.
        """
        if self.multi_run and getattr(self, "run_id", None):
            info = (self.runs.params(self.run_id) or {}).get(FOLLOW_UP_KEY)
            return info if isinstance(info, dict) else {}
        try:
            info = json.loads(Path(self.workflow_dir, FOLLOW_UP_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return info if isinstance(info, dict) else {}

    def _reload_settings(self, page=None) -> None:
        self.params = self.parameter_manager.get_parameters_from_json()
        self.parameter_manager.clear_parameter_session_state()
        if page is not None:
            st.switch_page(page)

    def _use_run(self, run_id: str) -> None:
        """Point results_dir (and the FileManager) at a run."""
        self.run_id = run_id
        self.results_dir = self.runs.results_dir(run_id)
        self.file_manager.results_dir = self.results_dir

    def _start_workflow_queued(self) -> None:
        """Submit workflow to Redis queue (online mode)"""
        from .QueueManager import QueueStateUnavailableError
        from .tasks import execute_workflow

        # Same-named workflows in different workspaces can start together.
        job_id = f"workflow-{self.workflow_dir.name}-{uuid.uuid4().hex}"

        # Submit job to queue
        try:
            submitted_id = self._queue_manager.submit_job(
                func=execute_workflow,
                kwargs={
                    "workflow_dir": str(self.workflow_dir),
                    "workflow_class": self.__class__.__name__,
                    "workflow_module": self.__class__.__module__,
                    "run_id": self.run_id if self.multi_run else None,
                },
                job_id=job_id,
                timeout=self.job_timeout(),
                description=f"Workflow: {self.name}"
            )
        except QueueStateUnavailableError:
            # The queue may have accepted the job before its acknowledgement
            # was lost. Retain its ID and never start a duplicate locally.
            self._queue_manager.store_job_id(self.workflow_dir, job_id)
            raise

        if submitted_id:
            # Store job ID for status checking
            self._queue_manager.store_job_id(self.workflow_dir, submitted_id)
        else:
            # Fallback to local execution if queue submission fails
            st.warning("Queue submission failed, running locally...")
            self._start_workflow_local()

    def job_timeout(self) -> int:
        """Time limit (s) of a queued run: grows with the run's input files.

        settings.json queue_settings: default_timeout + timeout_per_input per
        selected input file, at most max_timeout (src/workflow/job_timeout.py).
        Override for a workflow whose run time follows something else.
        """
        from .job_timeout import count_input_files, job_timeout
        from .settings_io import load_settings

        params = self.parameter_manager.get_parameters_from_json()
        return job_timeout(count_input_files(params), load_settings().get("queue_settings", {}))

    def _start_workflow_local(self) -> None:
        """Start the workflow in a separate Python process (local mode)."""
        self.executor.pid_dir.mkdir(parents=True, exist_ok=True)
        # Delete the log file if it already exists
        shutil.rmtree(Path(self.workflow_dir, "logs"), ignore_errors=True)
        # Run the workflow in a fresh interpreter, with the same function the
        # queue worker runs. A child forked from the server (multiprocessing's
        # default on Linux) inherits the thread pools the server has already
        # used, such as the OpenMP pool of pyOpenMS or polars' pool, without
        # their threads, and blocks forever the first time it needs one (an
        # mzML load, a polars query), so the run never finished.
        # multiprocessing's "spawn" does not help, it re-runs the page script
        # (Streamlit's __main__) in the child.
        if getattr(sys, "frozen", False):
            # A PyInstaller executable cannot run "-c". It is built for
            # Windows only, where multiprocessing starts a fresh interpreter.
            workflow_process = multiprocessing.Process(target=self.workflow_process)
            workflow_process.start()
        else:
            args = [str(self.workflow_dir), self.__class__.__name__, self.__class__.__module__]
            if self.multi_run:
                args.append(self.run_id)
            workflow_process = subprocess.Popen(
                [sys.executable, "-c", _RUN_WORKFLOW, _APP_ROOT, *args],
                stdin=subprocess.DEVNULL,
            )
        # Add workflow process id to pid dir
        def ended():
            return (
                workflow_process.poll() is not None
                if hasattr(workflow_process, "poll")
                else not workflow_process.is_alive()
            )

        try:
            register_process_marker(Path(self.executor.pid_dir, str(workflow_process.pid)), workflow_process.pid)
        except OSError:
            if ended():
                # A very fast worker can remove its tracking directory first.
                return
            # Registration failed while the worker is still alive. Do not
            # leave an untracked analysis running after reporting a failure.
            try:
                workflow_process.terminate()
                if hasattr(workflow_process, "wait"):
                    workflow_process.wait(timeout=5)
                else:
                    workflow_process.join(timeout=5)
                    if workflow_process.is_alive():
                        workflow_process.kill()
                        workflow_process.join(timeout=5)
            except subprocess.TimeoutExpired:
                workflow_process.kill()
                workflow_process.wait(timeout=5)
            except ProcessLookupError:
                if hasattr(workflow_process, "wait"):
                    workflow_process.wait(timeout=5)
                else:
                    workflow_process.join(timeout=5)
            raise
        if ended():
            Path(self.executor.pid_dir, str(workflow_process.pid)).unlink(missing_ok=True)
            try:
                self.executor.pid_dir.rmdir()
            except OSError:
                pass  # Other tracked children or unrelated files remain.

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
        if self._queue_manager:
            from .QueueManager import QueueStateUnavailableError

            job_id = self._queue_manager.load_job_id(self.workflow_dir)
            if job_id:
                try:
                    if not self._queue_manager.is_available:
                        raise QueueStateUnavailableError("The queue is unavailable; the existing job cannot be confirmed stopped.")
                    job_info = self._queue_manager.get_job_info(job_id)
                except QueueStateUnavailableError as error:
                    return {
                        "running": True, "status": "unknown", "progress": None,
                        "current_step": "Waiting for the queue to confirm the existing job status.",
                        "job_id": job_id, "queue_position": None, "queue_length": None,
                        "error": str(error),
                    }
                if job_info:
                    is_running = job_info.status.value in ["queued", "started"]
                    state = job_info.status.value
                    if not is_running and owned_workflow_running(self.executor.pid_dir):
                        is_running, state = True, "stopping"
                    return {
                        "running": is_running,
                        "status": state,
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
                    self._queue_manager.clear_job_id(self.workflow_dir, expected_job_id=job_id)

        # Fallback: check PID files (local mode)
        pid_dir = self.executor.pid_dir
        # A run whose process was killed (the app force-closed) left its pid
        # files behind and showed as running forever. Checking the markers
        # removes those of ended processes; online they may belong to a
        # worker in another container, so only proven ones count there.
        if self._is_online_mode():
            running = local_workflow_running(pid_dir)
        else:
            # reap() also removes the folder once no marker is left.
            running, removed = reap(pid_dir)
            if removed and not running:
                self._record_interrupted_run()
        if running:
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

    def _record_interrupted_run(self) -> None:
        """Say in the log why a run whose processes are gone ended."""
        log = Path(self.workflow_dir, "logs", "minimal.log")
        try:
            content = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        if classify_log_outcome(content) == "error":
            self.logger.log(
                "ERROR: The workflow was interrupted: its process ended without "
                "finishing (the app was closed or the process was killed)."
            )

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
        acquired = False
        try:
            with file_lock(self.workflow_dir / ".locks" / "execution.lock", blocking=False):
                acquired = True
                # Try to cancel queue job first (online mode).
                if self._queue_manager:
                    from .QueueManager import QueueStateUnavailableError

                    job_id = self._queue_manager.load_job_id(self.workflow_dir)
                    if job_id:
                        if not self._queue_manager.is_available or not self._queue_manager.cancel_job(job_id):
                            self.logger.log("The queued job could not be confirmed cancelled. Its tracking was retained; retry when the queue is available.")
                            return False
                        self.logger.log("WORKFLOW CANCELLED")
                        self._mark_running_runs_cancelled()
                        try:
                            job_info = self._queue_manager.get_job_info(job_id)
                        except QueueStateUnavailableError:
                            job_info = None
                        if job_info and job_info.status.value not in {"queued", "started"}:
                            # RQ has acknowledged the stop. Any locally owned
                            # leftovers can now be signalled without racing its
                            # controller's work-horse termination/classification.
                            self._stop_local_workflow(queued=True)
                        return True
                stopped = self._stop_local_workflow()
                if stopped:
                    self._mark_running_runs_cancelled()
                return stopped
        except BlockingIOError:
            if acquired:
                raise
            self.logger.log("Another session is starting or stopping this workflow; retry Stop when it finishes.")
            return False

    def _mark_running_runs_cancelled(self) -> None:
        # The stopped process can not record how its run ended, so do it here.
        if self.multi_run:
            for run in self.runs.list_runs(RUNNING):
                self.runs.finish(run["id"], CANCELLED)

    def _stop_local_workflow(self, *, queued=False) -> bool:
        """Stop locally running workflow process"""
        import signal

        pid_dir = self.executor.pid_dir
        try:
            markers = pid_markers(pid_dir)
        except OSError as error:
            self.logger.log(f"Cannot inspect running processes to stop this workflow: {error}")
            return False

        stopped = False
        for pid_file in markers:
            pid = int(pid_file.name)
            try:
                if not signal_owned_process(pid_file, signal.SIGTERM, prune_stale=not queued):
                    continue
                stopped = True
                # Sending a signal does not mean the process has exited. Keep
                # live tracking so another start cannot overlap its shutdown.
                prune_exited_marker(pid_file)
            except (ProcessLookupError, OverflowError):
                pid_file.unlink(missing_ok=True)  # Polling may already have cleaned it up.
            except PermissionError as error:
                self.logger.log(f"Cannot stop process {pid}; its tracking marker was retained: {error}")

        # Another child or a denied process can still own a marker. Only
        # remove an empty directory, rather than erasing its tracking state.
        try:
            pid_dir.rmdir()
        except OSError:
            pass
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

    def _follow_up(self) -> Optional[dict]:
        """What the settings follow (``follow_up``, ``start_from``), else None."""
        info = self.parameter_manager.get_parameters_from_json().get(FOLLOW_UP_KEY)
        return info if isinstance(info, dict) else None

    @staticmethod
    def _follow_up_summary(info: dict) -> str:
        """One line on what a start with the settings of an earlier run does."""
        name = info.get("name") or info.get("run") or "the earlier run"
        if info.get("same_files"):
            return f"Adds to {name}: its files with these settings, the new run kept next to it."
        if info.get("adds_to"):
            return f"Adds the files picked above to {name}."
        return f"Starts from the settings of {name}."

    def _follow_up_files_missing(self, info: Optional[dict]) -> bool:
        """True while settings that add files to an experiment have none picked."""
        key = (info or {}).get("files_key")
        if not key or not (info or {}).get("adds_to"):
            return False
        picked = st.session_state.get(f"{self.parameter_manager.param_prefix}{key}",
                                      self.params.get(key))
        return not picked

    def _autostart_key(self) -> str:
        """Session-state flag set by ``show_run_button``: start on the Run page."""
        return f"{self.workflow_dir.name}-autostart"

    def show_run_button(
        self,
        run_page,
        label: str = "Run analysis",
        help: Optional[str] = None,
        key: str = "",
        sticky: bool = True,
        summary: Optional[str] = None,
        name_label: str = "Run name",
    ) -> None:
        """A primary button that opens the Run page and starts the workflow there.

        For the end of the configure page, so a user who has described the
        experiment goes straight on: the settings are saved, ``run_page`` (a
        page path or ``st.Page``) opens and the run starts at once. While a run
        is going, the button opens the Run page to follow it instead.

        ``sticky`` (default) draws it in a bar that stays at the bottom of the
        window while the page scrolls, with ``summary`` (a short line on what
        will run) beside it; call it last on the page. ``sticky=False`` draws
        the button alone where it is called.

        A workflow with run folders (or ``name_runs``) gets a name field
        beside the button, labelled ``name_label``: the start is given that
        name (``run_name()`` in ``execution()``).
        """
        running = self.get_workflow_status().get("running", False)
        if running:
            label, icon = "Follow the running analysis", ":material/hourglass_top:"
            help = help or "An analysis is running. Open the Run page to follow it."
            summary = "An analysis is running."
        else:
            icon = ":material/play_arrow:"
            help = help or "Save these settings, open the Run page and start the analysis."
        info = None if running else self._follow_up()
        if info:
            # Settings of an earlier run (adding files, an analysis, a re-run):
            # this button starts with them; say so beside it.
            line = self._follow_up_summary(info)
            summary = f"{line} {summary}" if summary else line
        key = key or f"{self.workflow_dir.name}-run-button"
        if sticky:
            bar = st.container(key=f"{key}-bar", horizontal=True,
                               vertical_alignment="center", horizontal_alignment="right")
            st.html(_run_bar_css(f"{key}-bar"))
        else:
            bar = st.container()
        named = (self.multi_run or self.name_runs) and not running
        with bar:
            if sticky and summary:
                st.caption(summary, width="stretch")
            if named:
                st.text_input(
                    name_label, key=f"{key}-name", max_chars=MAX_NAME_LENGTH,
                    placeholder=self.run_name_placeholder(), width=320,
                    label_visibility="collapsed" if sticky else "visible",
                    help=f"{name_label}: how the results of this analysis are listed. "
                    "Leave it empty for the default name.",
                )
            clicked = st.button(label, type="primary", icon=icon, help=help, key=key)
        if clicked:
            if not running and self._follow_up_files_missing(info):
                st.toast("Pick the files to add first.", icon=":material/warning:")
                return
            if not running:
                if not self.parameter_manager.save_parameters():
                    return
                if named and not self._give_next_run_name(st.session_state.get(f"{key}-name", "")):
                    return
                st.session_state[self._autostart_key()] = True
            st.switch_page(run_page)

    def _give_next_run_name(self, name: str) -> bool:
        """Keep the name typed beside the Run button for the start it opens.
        False (with an error shown) when params.json cannot be read."""
        name = (name or "").strip()[:MAX_NAME_LENGTH]
        try:
            params = self.parameter_manager.read_parameters_strict()
        except InvalidParameterFileError as e:
            st.error(f"**ERROR**: {e} The analysis was not started.")
            return False
        if name:
            params[RUN_NAME_KEY] = name
        elif params.pop(RUN_NAME_KEY, None) is None:
            return True
        self.parameter_manager.write_parameters(params)
        if self.multi_run:
            from .run_widgets import run_name_key

            # The Run page shows it in its own name field
            st.session_state[run_name_key(self.runs)] = name
        return True

    def show_execution_section(
        self,
        results_page=None,
        results_label: str = "Open results",
    ) -> None:
        """
        Shows the execution section of the UI with content defined in self.execution().

        A start requested by ``show_run_button`` on the configure page begins
        here at once. ``results_page`` (a page path or ``st.Page``) is linked
        when the run has finished, labelled ``results_label``.
        """
        autostart = bool(st.session_state.pop(self._autostart_key(), False))
        name_key = ""
        if self.multi_run:
            from .run_widgets import run_name_input, run_name_key

            run_name_input(self.runs, disabled=self.get_workflow_status()["running"] or autostart)
            name_key = run_name_key(self.runs)
        if self._run_online(name_key):
            return
        blocked = "" if self.get_workflow_status().get("running") else self.input_problems()
        self.ui.execution_section(
            blocked=blocked,
            start_workflow_function=self.start_workflow,
            get_status_function=self.get_workflow_status,
            stop_workflow_function=self.stop_workflow,
            autostart=autostart,
            results_page=results_page,
            results_label=results_label,
            on_open_results=self._select_newest_run if self.multi_run else None,
            name=self.run_label or getattr(self, "name", "The workflow"),
        )

    def _select_newest_run(self) -> None:
        """Show the newest finished run on the results page, not an older pick."""
        from .run_widgets import set_selected_run

        set_selected_run(self.runs, self.runs.latest())

    def _run_online(self, name_key: str) -> bool:
        """Offer the linked online workspace (offline app, workspace sync on).

        True when the user chose it and its controls were drawn instead.
        """
        if not st.session_state.get("settings", {}).get("workspace_sync", {}).get("enabled"):
            return False
        from src.common.workspace_sync import render_run_choice

        # Saved when the online run starts: it takes them from params.json.
        return render_run_choice(self.workflow_dir, name_key,
                                 save_parameters=self.parameter_manager.save_parameters)

    def show_results_section(self) -> None:
        """
        Shows the results section of the UI with content defined in self.results().

        A multi-run workflow first shows a run picker and points
        self.results_dir at the chosen run.
        """
        if self.multi_run:
            from .run_widgets import show_import_notice

            show_import_notice(self.runs)
        if self.multi_run and not self.select_run():
            from .run_widgets import run_import

            st.info(
                "No finished runs yet. Start the workflow on the **Run** page, "
                "or open a run someone shared as a ZIP."
            )
            run_import(self.runs)
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
            on_start_again=self.start_again if self.configure_page else None,
        )

    def start_again(self, run_id: str) -> bool:
        """Open ``configure_page`` with the files and settings ``run_id`` was
        started with (``follow_up``); the next start makes a new run next to it.
        False if the run recorded no settings."""
        if self.follow_up(run_id, page=self.configure_page, note="to start again"):
            return True
        st.toast("This run recorded no settings to start from.", icon=":material/error:")
        return False

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

def _run_bar_css(container_key: str) -> str:
    """Style of the Run bar: it sticks to the bottom of the window, in the
    background colour of the active theme so the page scrolls under it."""
    try:
        theme = st.context.theme.type or "light"
    except Exception:  # pragma: no cover - older Streamlit
        theme = "light"
    try:
        background = st.get_option(f"theme.{theme}.backgroundColor")
    except Exception:
        background = None
    background = background or ("#0e1117" if theme == "dark" else "#ffffff")
    # The bar's own element wrapper is what sticks: the bar alone would only
    # stick within that wrapper.
    return f"""<style>
div:has(> .st-key-{container_key}) {{
  position: sticky; bottom: 0; z-index: 99;
  background: {background};
  padding: 0.75rem 0 1rem 0; margin-top: 1rem;
  border-top: 1px solid rgba(128, 128, 128, 0.3);
}}
</style>"""
