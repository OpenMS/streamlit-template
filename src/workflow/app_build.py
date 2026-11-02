"""
Identify the build of the app a process runs, so the RQ worker can tell when it
runs different code than the page that queued a job.

In Kubernetes the Streamlit pods and the rq-worker pods are separate
Deployments of one image. With a moving tag such as ``latest`` a release only
reaches the pods that are restarted, and nothing restarts both together. A page
on the new release then writes parameters (and the TOPP ``.ini`` files) for the
new TOPP tools while an old worker runs them with the old tools and the old
``execution()``. The tool rejects the parameters ("Parameters passed to '<tool>'
are invalid", exit code 6) and the error says nothing about the cause.

The page stamps every job with its build (``QueueManager.submit_job``) and the
worker compares it with its own (``tasks.execute_workflow``) before running
anything.

Streamlit free: imported by the worker.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

from .settings_io import load_settings

# The code the worker runs: the app's src/ tree, relative to the working
# directory like settings.json.
CODE_ROOT = Path("src")


@lru_cache(maxsize=None)
def _code_digest(root: str) -> str:
    """Hash every .py file below ``root`` (path and content), sorted by path."""
    digest = hashlib.sha256()
    base = Path(root)
    try:
        files = sorted(p for p in base.rglob("*.py") if p.is_file())
    except OSError:
        return ""
    for path in files:
        try:
            content = path.read_bytes()
        except OSError:
            continue
        digest.update(path.relative_to(base).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()[:12] if files else ""


def app_build(settings_path: str = "settings.json", code_root: Path = CODE_ROOT) -> dict:
    """
    The build of the app in this process.

    Returns:
        dict: ``{"version": <settings.json version>, "code": <hash of src/**/*.py>}``.
            Either value is "" when it cannot be determined.
    """
    settings = load_settings(settings_path)
    return {
        "version": str(settings.get("version", "") or ""),
        # Resolved, so the cache is keyed by the directory, not the working
        # directory the relative default happened to point at.
        "code": _code_digest(str(Path(code_root).resolve())),
    }


def build_mismatch(expected: dict | None, actual: dict | None = None) -> str | None:
    """
    Explain why a job queued by build ``expected`` must not run on ``actual``.

    Only the code hash decides: two images of the same version can still differ.
    A job without a stamp (queued by an older page) or a side whose hash could
    not be computed is let through, so this never blocks a deployment it cannot
    judge.

    Returns:
        str | None: A message for the workflow log, or None when the job may run.
    """
    if not isinstance(expected, dict):
        return None
    if actual is None:
        actual = app_build()
    want, have = expected.get("code") or "", actual.get("code") or ""
    if not want or not have or want == have:
        return None

    def describe(build: dict) -> str:
        version = build.get("version") or "unknown version"
        return f"{version} (code {build.get('code')})"

    return (
        f"This workflow was started from a page running {describe(expected)},\n"
        f"but the worker that picked it up runs {describe(actual)}.\n"
        "The workers run a different image than the web pages, so the parameters\n"
        "would not match the tools. Nothing was run.\n"
        "Restart the workers so they run the same image as the pages\n"
        "(in Kubernetes: kubectl rollout restart on the rq-worker Deployment),\n"
        "then start the workflow again."
    )
