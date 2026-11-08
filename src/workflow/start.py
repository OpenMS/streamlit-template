"""What every start of a workflow does, whoever starts it.

The Run button (``WorkflowManager.start_workflow``), a run the desktop app
starts online (``src/sync/runs.py``) and a run an AI assistant starts
(``src/agent_access/runner.py``) all go through here, so a run records the
same things (its run folder with its settings, which run it follows) and its
processing report reads the same however it was started.

Streamlit-free: the sync service and the assistant's server import it.
"""

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from .RunManager import (FOLLOW_UP_FILE, FOLLOW_UP_KEY, PURPOSE_FILE, PURPOSE_KEY,
                         RunManager, clean_purpose)

APP_ROOT = str(Path(__file__).resolve().parents[2])

# The workflow process: a fresh interpreter running what the queue worker runs.
RUN_WORKFLOW = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from src.workflow.tasks import execute_workflow\n"
    "execute_workflow(*sys.argv[2:])\n"
)


def _read(params_file: Path) -> dict:
    try:
        params = json.loads(params_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return params if isinstance(params, dict) else {}


def _write(params_file: Path, params: dict) -> None:
    tmp = params_file.with_name(f"{params_file.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(params, indent=4), encoding="utf-8")
        os.replace(tmp, params_file)
    finally:
        tmp.unlink(missing_ok=True)


def prepare(workflow_dir: Path, multi_run: bool, name: str = "") -> str | None:
    """Record the start in the workflow folder, before the run begins.

    With run folders: create the run (named ``name``, with the settings in
    params.json and the run it adds to) and return its id. Without: keep which
    result the start follows in ``FOLLOW_UP_FILE``. Either way the next
    settings start fresh, without the follow-up. Who started the run and why
    (``PURPOSE_KEY``) goes the same way: into the run, or ``PURPOSE_FILE``.
    """
    workflow_dir = Path(workflow_dir)
    params_file = Path(workflow_dir, "params.json")
    params = _read(params_file)
    info = params.get(FOLLOW_UP_KEY)
    run_id = None
    if multi_run:
        adds_to = info.get("adds_to") if isinstance(info, dict) else None
        run_id = RunManager(workflow_dir).new_run(name, params_file, adds_to=adds_to)
    else:
        sidecar = Path(workflow_dir, FOLLOW_UP_FILE)
        if isinstance(info, dict):
            sidecar.write_text(json.dumps(info), encoding="utf-8")
        else:
            sidecar.unlink(missing_ok=True)
        purpose = clean_purpose(params.get(PURPOSE_KEY))
        sidecar = Path(workflow_dir, PURPOSE_FILE)
        if purpose:
            sidecar.write_text(json.dumps(purpose), encoding="utf-8")
        else:
            sidecar.unlink(missing_ok=True)
    followed = params.pop(FOLLOW_UP_KEY, None) is not None
    if (params.pop(PURPOSE_KEY, None) is not None) or followed:
        _write(params_file, params)
    return run_id


def launch_local(workflow_dir: Path, workflow_class: str, workflow_module: str,
                 run_id: str | None = None, app_root: str = APP_ROOT,
                 detach: bool = False) -> subprocess.Popen | None:
    """Run the workflow in a fresh interpreter and list it in ``pids/``.

    Returns the process, or None when it ended before its pid was written.
    ``detach`` gives it a session of its own and no stdout, for a caller
    whose stdout is a protocol stream and whose life is shorter than the run's.
    A child forked from the server would inherit the thread pools of pyOpenMS
    and polars without their threads and hang, so this is never a fork.
    """
    workflow_dir = Path(workflow_dir)
    shutil.rmtree(Path(workflow_dir, "logs"), ignore_errors=True)
    args = [str(workflow_dir), workflow_class, workflow_module]
    if run_id:
        args.append(run_id)
    extra = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 start_new_session=True) if detach else {}
    proc = subprocess.Popen([sys.executable, "-c", RUN_WORKFLOW, str(app_root), *args],
                            cwd=app_root if detach else None, stdin=subprocess.DEVNULL, **extra)
    pid_dir = Path(workflow_dir, "pids")
    pid_dir.mkdir(exist_ok=True)
    try:
        Path(pid_dir, str(proc.pid)).touch()
    except FileNotFoundError:
        # The workflow already ended (e.g. no input files) and removed the pid dir.
        return None
    if proc.poll() is not None:
        # Ended before its pid was written: the pid dir would show it running forever.
        shutil.rmtree(pid_dir, ignore_errors=True)
        return None
    return proc
