"""
Entry point of a workflow run: ``python -m server.run_workflow <workflow_dir> <class> <module>``.

Runs the workflow's unchanged ``execution()`` through the Streamlit-free
``src.workflow.tasks.execute_workflow``, which writes the logs and markers.
"""

import sys

from server.core import ensure_cwd


def main(argv: list[str]) -> int:
    ensure_cwd()
    from src.workflow.tasks import execute_workflow

    workflow_dir, cls, module = argv
    try:
        execute_workflow(workflow_dir, cls, module)
    except Exception:
        # execute_workflow already wrote the error to the workflow logs
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
