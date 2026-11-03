"""
A local workflow run must not inherit the server's thread pools.

Local mode used to start the workflow with multiprocessing.Process, which forks
the Streamlit server on Linux. The forked child got the thread pools the server
had used without their threads, and blocked forever the first time it needed
one: the run stayed "running" and never finished. polars' pool (OpenMS-Insight)
is process-wide, so any page that had run a polars query was enough. pyOpenMS'
OpenMP pool belongs to the thread that used it, so it hung the run when the
page that started it had loaded an mzML file earlier in the same script run.

The first test loads an mzML file in the test process, then starts a workflow
from the same thread whose execution() loads one too, and checks that the run
finishes. With the forked start it times out.

The second test checks that the run status and the stop button still work with
the workflow running in its own process.
"""

import json
import os
import signal
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
oms = pytest.importorskip("pyopenms")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workflow.Logger import Logger  # noqa: E402

MZML = ROOT / "example-data" / "mzML" / "Control.mzML"

# The workflow classes live in a module of their own, written to a temporary
# folder, so the workflow process can import them by name.
WORKFLOW_MODULE = textwrap.dedent(
    """
    import time
    import pyopenms as oms
    from src.workflow.WorkflowManager import WorkflowManager


    class MzMLWorkflow(WorkflowManager):
        def execution(self) -> bool:
            exp = oms.MSExperiment()
            oms.MzMLFile().load(self.params["mzML"], exp)
            self.logger.log(f"spectra: {exp.size()}")
            return True


    class SleepWorkflow(WorkflowManager):
        def execution(self) -> bool:
            self.logger.log("sleeping")
            time.sleep(120)
            return True
    """
)


def _load_mzml() -> int:
    exp = oms.MSExperiment()
    oms.MzMLFile().load(str(MZML), exp)
    return exp.size()


@pytest.fixture
def workflow_module(tmp_path, monkeypatch):
    mod_dir = tmp_path / "mods"
    mod_dir.mkdir()
    (mod_dir / "local_process_workflows.py").write_text(WORKFLOW_MODULE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(mod_dir))
    # The workflow process finds the module through PYTHONPATH
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join(filter(None, [str(mod_dir), os.environ.get("PYTHONPATH")]))
    )
    monkeypatch.chdir(ROOT)
    import local_process_workflows

    yield local_process_workflows
    sys.modules.pop("local_process_workflows", None)


def _make(cls, workflow_dir: Path):
    """A workflow object for _start_workflow_local, without a Streamlit session."""
    from types import SimpleNamespace

    workflow_dir.mkdir(parents=True, exist_ok=True)
    wf = object.__new__(cls)  # skips __init__, which needs a Streamlit session
    wf.workflow_dir = workflow_dir
    wf.run_id = None
    wf.runs = None
    wf.results_dir = workflow_dir / "results"
    wf.logger = Logger(workflow_dir)
    wf.executor = SimpleNamespace(pid_dir=workflow_dir / "pids")
    wf._queue_manager = None
    wf.params = {"mzML": str(MZML)}
    return wf


def _kill_leftovers(pid_dir: Path) -> None:
    if pid_dir.exists():
        for f in pid_dir.iterdir():
            try:
                os.kill(int(f.name), signal.SIGTERM)
            except (ValueError, OSError):
                pass


def _wait_for(predicate, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.25)
    return False


@pytest.mark.skipif(not MZML.exists(), reason="example mzML missing")
def test_run_finishes_after_the_server_loaded_an_mzml(tmp_path, workflow_module):
    assert _load_mzml() > 0  # the server has used pyOpenMS' OpenMP pool

    workflow_dir = tmp_path / "mzml-workflow"
    workflow_dir.mkdir()
    # execute_workflow reads the parameters from params.json
    (workflow_dir / "params.json").write_text(json.dumps({"mzML": str(MZML)}), encoding="utf-8")
    wf = _make(workflow_module.MzMLWorkflow, workflow_dir)
    log = workflow_dir / "logs" / "minimal.log"
    try:
        wf._start_workflow_local()
        finished = _wait_for(
            lambda: log.exists() and "WORKFLOW FINISHED" in log.read_text(encoding="utf-8"),
            90,
        )
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        assert finished and "spectra: " in text, f"run did not finish:\n{text}"
        # The pid dir goes once the workflow process has cleaned up
        assert _wait_for(lambda: not wf.executor.pid_dir.exists(), 10)
        assert wf.get_workflow_status()["running"] is False
    finally:
        _kill_leftovers(wf.executor.pid_dir)


@pytest.mark.skipif(sys.platform == "win32", reason="checks the process with POSIX signals")
def test_stop_ends_the_workflow_process(tmp_path, workflow_module):
    wf = _make(workflow_module.SleepWorkflow, tmp_path / "sleep-workflow")
    log = wf.workflow_dir / "logs" / "minimal.log"
    try:
        wf._start_workflow_local()
        assert wf.get_workflow_status()["running"] is True
        pids = [int(f.name) for f in wf.executor.pid_dir.iterdir()]
        assert len(pids) == 1
        assert _wait_for(lambda: log.exists() and "sleeping" in log.read_text(encoding="utf-8"), 60)

        assert wf.stop_workflow() is True

        def gone() -> bool:
            try:
                # Reap it if it is our child (it is unless the test forks)
                os.waitpid(pids[0], os.WNOHANG)
                os.kill(pids[0], 0)
                return False
            except (ChildProcessError, ProcessLookupError):
                return True

        assert _wait_for(gone, 10), "workflow process still running after stop"
        assert wf.get_workflow_status()["running"] is False
        assert "WORKFLOW CANCELLED" in log.read_text(encoding="utf-8")
    finally:
        _kill_leftovers(wf.executor.pid_dir)
