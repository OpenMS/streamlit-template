"""
Tests for the failure signal of a workflow run.

``src/workflow/tasks.py`` is the RQ worker entry point for online (queue) mode
and has no test coverage at all. Two defects there make a failed workflow
indistinguishable from a successful one:

  - ``tasks.py:105-108`` calls ``workflow.execution()``, discards its return
    value and logs the ``WORKFLOW FINISHED`` marker unconditionally. A workflow
    that reported failure by returning ``False`` still ends up with the success
    marker in its log, which is the only thing
    ``src/workflow/_log_status.classify_log_outcome`` looks at.
  - ``tasks.py:144-148`` catches every exception and *returns a dict* instead of
    re-raising. RQ only records a job as failed when the job function raises, so
    ``FailedJobRegistry`` is structurally always empty and ``health.py``'s
    ``failed_jobs`` metric can never be anything but zero.

The other half of the same signal lives in ``src/Workflow.py``: ``execution()``
is annotated ``-> None``, returns nothing, and throws away the ``bool`` that
every ``run_topp`` / ``run_python`` call returns. ``WorkflowManager.execution``
is declared ``-> bool`` and ``WorkflowManager.workflow_process`` already gates
the marker on it, so the shipped example workflow renders
"Errors occurred, check log file." for a *successful* local run and says nothing
at all when a tool failed.

The two halves have to be fixed together: honouring the bool in ``tasks.py``
while ``execution()`` still returns ``None`` would mark every workflow failed.
Each test below therefore pins both directions of the signal, so neither defect
can be "fixed" by inverting it.
"""

import os
import sys
import json
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

fakeredis = pytest.importorskip("fakeredis")
rq = pytest.importorskip("rq")
# src/Workflow.py pulls in the whole Streamlit UI stack (StreamlitUI ->
# src.common.common -> captcha / psutil / pandas), so the real packages are
# needed here rather than the sys.modules MagicMock used by the tests that only
# touch ParameterManager / CommandExecutor.
pytest.importorskip("streamlit")
pytest.importorskip("pyopenms")

from rq import Queue, SimpleWorker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow import tasks
from src.workflow.FileManager import FileManager
from src.workflow.Logger import Logger
from src.workflow.QueueManager import QueueManager

# Importing src.Workflow drags in src.workflow.{StreamlitUI, ParameterManager,
# CommandExecutor, ...} bound to the *real* streamlit. Later test modules
# (test_tool_instance_name.py, test_topp_flag_parameters.py) swap
# sys.modules['streamlit'] for a MagicMock before importing those same modules,
# and would silently get these real ones back from the module cache instead.
# Restore the pre-import view of sys.modules so they still import cleanly; the
# Workflow class keeps its own module globals either way.
_src_modules_before = {
    k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")
}

from src.Workflow import Workflow

for _key in [k for k in sys.modules if k == "src" or k.startswith("src.")]:
    sys.modules.pop(_key, None)
sys.modules.update(_src_modules_before)


QUEUE_NAME = "openms-workflows-test"


class _FakeRedisSimpleWorker(SimpleWorker):
    """
    SimpleWorker that skips RQ's start-up CLIENT LIST lookup.

    rq's Worker.__init__ reads client["addr"] out of CLIENT LIST to record the
    worker's ip address; fakeredis answers CLIENT LIST without that field, so
    constructing any worker against it raises KeyError before a single job
    runs. ip_address is telemetry only and nothing under test reads it - the
    job execution and success/failure bookkeeping below are untouched.
    """

    def _set_ip_address(self, connection) -> None:
        self.ip_address = "unknown"


# ---------------------------------------------------------------------------
# Stand-in workflows. They live at module scope because execute_workflow
# resolves the class with importlib.import_module(workflow_module), and this
# test module is itself importable under its own __name__.
# ---------------------------------------------------------------------------


class RaisingWorkflow:
    """A workflow that crashes, e.g. on a TOPP tool that is not installed."""

    def execution(self) -> bool:
        raise RuntimeError("deliberate workflow failure")


class FalseReturningWorkflow:
    """A workflow reporting failure the documented way: by returning False."""

    def execution(self) -> bool:
        return False


class TrueReturningWorkflow:
    """A workflow that succeeds."""

    def execution(self) -> bool:
        return True


class NoneReturningWorkflow:
    """
    A workflow written against the older example: annotated -> None, returns
    nothing.

    This is the shape src/Workflow.py shipped until Step 1, and the shape the
    downstream subclasses (quantms-web, umetaflow, FLASHApp) still carry - they
    live in their own repositories and cannot be fixed in the same commit as
    tasks.py.
    """

    def execution(self) -> None:
        return None


# ------------------------------- helpers -----------------------------------


def _prepare_workflow_dir(tmp_path: Path, name: str) -> Path:
    """Create a workflow directory with the params.json the worker expects."""
    workflow_dir = tmp_path / name
    workflow_dir.mkdir(parents=True, exist_ok=True)
    with open(Path(workflow_dir, "params.json"), "w", encoding="utf-8") as f:
        json.dump({"max_threads": 1}, f)
    return workflow_dir


def _run_in_worker(workflow_dir: Path, workflow_class: str) -> tuple:
    """
    Enqueue tasks.execute_workflow and drain the queue with an in-process RQ
    worker backed by fakeredis. Returns (queue, job_id).

    SimpleWorker performs the job in the current process (no fork), so the
    stand-in workflow classes above are importable from the worker while RQ's
    own success/failure bookkeeping - the thing under test - still runs for
    real.

    Queue name and job id are unique per call: older fakeredis releases share
    one server between bare FakeStrictRedis() instances, which would otherwise
    let one run's registries leak into the next one's assertions.
    """
    run_id = uuid.uuid4().hex[:8]
    job_id = f"job-{workflow_class}-{run_id}"
    connection = fakeredis.FakeStrictRedis()
    queue = Queue(f"{QUEUE_NAME}-{run_id}", connection=connection)
    queue.enqueue(
        tasks.execute_workflow,
        kwargs={
            "workflow_dir": str(workflow_dir),
            "workflow_class": workflow_class,
            "workflow_module": __name__,
        },
        job_id=job_id,
    )
    _FakeRedisSimpleWorker([queue], connection=connection).work(
        burst=True, logging_level="CRITICAL"
    )
    return queue, job_id


def _read_logs(workflow_dir: Path) -> dict:
    """Return {log file name: content} for the three log tiers Logger writes."""
    log_dir = Path(workflow_dir, "logs")
    logs = {}
    for name in ("minimal.log", "commands-and-run-times.log", "all.log"):
        log_file = Path(log_dir, name)
        logs[name] = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    return logs


def _make_workflow(workflow_dir: Path, params: dict, executor) -> Workflow:
    """
    Build a src.Workflow.Workflow the way the RQ worker does: bypass __init__
    (it dereferences st.session_state) and inject the members execution() uses.

    Mirrors tasks.execute_workflow:81-88, so anything breaking here breaks the
    worker too.
    """
    workflow = object.__new__(Workflow)
    workflow.name = workflow_dir.name
    workflow.workflow_dir = workflow_dir
    workflow.file_manager = FileManager(workflow_dir)
    workflow.logger = Logger(workflow_dir)
    workflow.parameter_manager = MagicMock()
    workflow.executor = executor
    workflow.params = params
    # workflow_process() and execute_workflow() both create results/ before
    # calling execution(); FileManager._create_results_sub_dir mkdirs without
    # parents=True and would fail otherwise.
    Path(workflow_dir, "results").mkdir(parents=True, exist_ok=True)
    return workflow


def _make_executor(topp_results=(True, True), python_result=True) -> MagicMock:
    """
    A stand-in CommandExecutor whose run_topp / run_python return bools.

    Both really do: run_python() used to be annotated -> None and discard
    run_command()'s result, which made every `if not run_python(...)` guard in
    execution() dead code and this mock's False a value production could never
    produce. tests/test_command_executor_run_python.py pins the real contract.
    """
    executor = MagicMock()
    executor.run_topp.side_effect = list(topp_results)
    executor.run_python.return_value = python_result
    return executor


# =========================== tasks.execute_workflow ==========================


def test_failed_workflow_reaches_failed_registry(tmp_path):
    """
    A workflow whose execution() raises must be recorded as failed by RQ.

    execute_workflow swallows the exception and returns
    {"success": False, ...}, so from RQ's point of view the job returned
    normally: it lands in the finished registry and FailedJobRegistry stays
    empty. That makes health.py's failed_jobs metric structurally zero and
    leaves Retry inert for application failures.

    The second half is the control for the fix: re-raising must stay confined
    to actual failures, or "every job failed" would satisfy the first half.
    """
    failing_dir = _prepare_workflow_dir(tmp_path, "failing-workflow")
    queue, job_id = _run_in_worker(failing_dir, "RaisingWorkflow")

    failed_ids = queue.failed_job_registry.get_job_ids()
    finished_ids = queue.finished_job_registry.get_job_ids()

    assert failed_ids == [job_id], (
        "A crashed workflow must reach RQ's FailedJobRegistry "
        f"(failed={failed_ids}, finished={finished_ids}). execute_workflow has "
        "to re-raise instead of returning a result dict."
    )
    assert finished_ids == [], (
        "A crashed workflow must not be recorded as finished successfully."
    )

    ok_dir = _prepare_workflow_dir(tmp_path, "succeeding-workflow")
    ok_queue, ok_job_id = _run_in_worker(ok_dir, "TrueReturningWorkflow")

    assert ok_queue.failed_job_registry.get_job_ids() == [], (
        "A successful workflow must not be reported as failed."
    )
    assert ok_queue.finished_job_registry.get_job_ids() == [ok_job_id]


def test_execution_returning_false_is_a_failure(tmp_path):
    """
    Returning False from execution() is the documented failure signal
    (WorkflowManager.execution is declared -> bool and workflow_process gates
    the marker on it). The worker must honour it and *not* write the
    WORKFLOW FINISHED marker, which is what classify_log_outcome reads when it
    decides a run succeeded.

    The second half pins the marker string and the log tiers that receive it
    (as tests/test_workflow_manager_stop.py does for WORKFLOW CANCELLED), so
    the first half cannot be satisfied by never writing the marker at all.
    """
    failing_dir = _prepare_workflow_dir(tmp_path, "failing-workflow")
    queue, job_id = _run_in_worker(failing_dir, "FalseReturningWorkflow")

    # Returning False is the *documented* failure signal and by far the most
    # common one - "No mzML files selected" reaches it. Asserting only on the
    # log markers would let execute_workflow swallow it back into a
    # {"success": False} return, leaving the FailedJobRegistry empty and
    # health.py's failed_jobs metric structurally zero all over again.
    assert queue.failed_job_registry.get_job_ids() == [job_id], (
        "a workflow reporting failure by returning False must reach RQ's "
        "FailedJobRegistry, not just be missing a log marker"
    )
    assert queue.finished_job_registry.get_job_ids() == []

    for name, content in _read_logs(failing_dir).items():
        assert "STARTING WORKFLOW" in content, (
            f"{name} should carry the start marker - the run did happen."
        )
        assert "WORKFLOW FINISHED" not in content, (
            f"{name} must not claim the workflow finished: execution() returned "
            "False. execute_workflow logs the marker unconditionally, so a "
            "failed queued run is reported to the user as a success."
        )

    ok_dir = _prepare_workflow_dir(tmp_path, "succeeding-workflow")
    _run_in_worker(ok_dir, "TrueReturningWorkflow")

    for name, content in _read_logs(ok_dir).items():
        assert "WORKFLOW FINISHED" in content, (
            f"{name} must still carry the finished marker when execution() "
            "returned True."
        )


def test_legacy_execution_returning_none_is_accepted_as_success(tmp_path):
    """
    A subclass still annotated -> None must not have every run reported failed.

    Queue mode used to log WORKFLOW FINISHED unconditionally, so for the forks
    carrying the old example's signature every queued run was recorded
    successful. Honouring the bool strictly would flip all of them to failed on
    the first rebase, for runs in which every step succeeded - and the plan's
    "ship it in the same commit as Workflow.py" rule cannot reach a subclass
    that lives in another repository. None is therefore accepted as success,
    loudly; an explicit False stays a failure, which is what
    test_execution_returning_false_is_a_failure pins.
    """
    legacy_dir = _prepare_workflow_dir(tmp_path, "legacy-workflow")
    queue, job_id = _run_in_worker(legacy_dir, "NoneReturningWorkflow")

    assert queue.failed_job_registry.get_job_ids() == [], (
        "a legacy execution() returning None must not be reported as a failure"
    )
    assert queue.finished_job_registry.get_job_ids() == [job_id]

    logs = _read_logs(legacy_dir)
    assert "WORKFLOW FINISHED" in logs["minimal.log"]
    assert "execution() returned None" in logs["minimal.log"], (
        "accepting None silently would leave the fork with no signal to "
        "migrate on; the deprecation has to reach the log the user reads"
    )


def test_failed_jobs_are_evicted_rather_than_kept_for_a_year(tmp_path, monkeypatch):
    """
    Failed jobs are brand-new state, and they must expire.

    Before execute_workflow started re-raising, the FailedJobRegistry was
    structurally always empty - that was the defect. Now every failure keeps a
    job hash with its full traceback in Redis, and RQ's default failure_ttl is
    one year. That Redis has memory request == limit == 256Mi, no persistence
    and no maxmemory-policy, so it is OOMKilled rather than evicting; "No mzML
    files selected" is a routine user error and must not leave a year-lived key
    behind.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("REDIS_URL", raising=False)
    Path(tmp_path, "settings.json").write_text(
        json.dumps({"online_deployment": False}), encoding="utf-8"
    )

    connection = fakeredis.FakeStrictRedis()
    queue = Queue(f"{QUEUE_NAME}-{uuid.uuid4().hex[:8]}", connection=connection)

    # Built through __init__ so the retention actually comes from the
    # configured defaults, then pointed at the fake queue - local mode means no
    # Redis connection was attempted during construction.
    manager = QueueManager()
    manager._is_online = True
    manager._queue = queue

    failing_dir = _prepare_workflow_dir(tmp_path, "failing-workflow")
    job_id = manager.submit_job(
        tasks.execute_workflow,
        kwargs={
            "workflow_dir": str(failing_dir),
            "workflow_class": "RaisingWorkflow",
            "workflow_module": __name__,
        },
        job_id=f"ttl-job-{uuid.uuid4().hex[:8]}",
    )
    assert job_id is not None, "the job was not enqueued at all"

    _FakeRedisSimpleWorker([queue], connection=connection).work(
        burst=True, logging_level="CRITICAL"
    )

    registry = queue.failed_job_registry
    assert registry.get_job_ids() == [job_id]

    expires_in = connection.zscore(registry.key, job_id) - time.time()
    assert 0 < expires_in <= 7 * 24 * 3600, (
        "the failed job is retained for "
        f"{expires_in / 86400:.1f} days; enqueue has to pass failure_ttl "
        "alongside result_ttl, or RQ keeps it for a year"
    )


# ============================ src.Workflow.Workflow ==========================


def test_execution_returns_true_on_success(tmp_path):
    """
    The shipped example workflow must report success by returning True.

    It is annotated -> None and returns nothing, so workflow_process() never
    logs WORKFLOW FINISHED and a successful local run renders
    "Errors occurred, check log file."
    """
    workflow_dir = _prepare_workflow_dir(tmp_path, "topp-workflow")
    executor = _make_executor()
    workflow = _make_workflow(
        workflow_dir,
        {"mzML-files": ["a.mzML", "b.mzML"], "run-python-script": False},
        executor,
    )

    result = workflow.execution()

    assert result is True, (
        f"execution() must return True when every step succeeded; got {result!r}."
    )
    # Proves the True did not come from an early exit: both TOPP steps and the
    # consensus export actually ran.
    assert [c.args[0] for c in executor.run_topp.call_args_list] == [
        "FeatureFinderMetabo",
        "FeatureLinkerUnlabeledKD",
    ]
    assert executor.run_python.call_count == 1


def test_execution_returns_false_on_missing_input(tmp_path):
    """
    "No mzML files selected" is the workflow's own parameter check. It logs an
    ERROR and bails, but returns None, so the caller cannot tell it apart from
    a completed run.
    """
    workflow_dir = _prepare_workflow_dir(tmp_path, "topp-workflow")
    executor = _make_executor()
    workflow = _make_workflow(
        workflow_dir, {"mzML-files": [], "run-python-script": False}, executor
    )

    result = workflow.execution()

    assert result is False, (
        f"execution() must return False when the input check fails; got {result!r}."
    )
    executor.run_topp.assert_not_called()
    assert "ERROR: No mzML files selected." in _read_logs(workflow_dir)["minimal.log"]


@pytest.mark.parametrize(
    "topp_results, python_result",
    [
        ((False, True), True),
        ((True, False), True),
        ((True, True), False),
    ],
    ids=["feature-detection-fails", "feature-linking-fails", "python-export-fails"],
)
def test_tool_failure_propagates(tmp_path, topp_results, python_result):
    """
    run_topp / run_python already return a bool. execution() discards every one
    of them, so a tool that failed - a missing binary, a bad parameter, a
    SIGKILLed process - is reported to the user as a completed workflow.
    """
    workflow_dir = _prepare_workflow_dir(tmp_path, "topp-workflow")
    executor = _make_executor(topp_results=topp_results, python_result=python_result)
    workflow = _make_workflow(
        workflow_dir,
        {"mzML-files": ["a.mzML", "b.mzML"], "run-python-script": False},
        executor,
    )

    result = workflow.execution()

    assert result is False, (
        "execution() must return False as soon as an executor call fails; "
        f"got {result!r}."
    )
