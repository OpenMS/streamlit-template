"""The example workflow imports plotly express only for the intensity chart.

Every page of the workflow (configure, run, results, download) imports
src.Workflow. Importing plotly.express at its top cost 0.3 to 0.7 s of the first
of those pages after a restart, although only the results page draws a plotly
express chart, and only once rows of the feature table are selected.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_module_does_not_import_plotly_express():
    code = "import sys\nimport src.Workflow\nprint('plotly.express' in sys.modules)\n"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "False"
