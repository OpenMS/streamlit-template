"""
The workflows this app offers. A derived app edits this file: one
WorkflowSpec per WorkflowManager subclass.

The spec below is the Svelte counterpart of ``src/Workflow.py``'s
``upload()``, ``configure()`` and ``results()``; its ``execution()`` is reused
as is.
"""

from pathlib import Path

from .workflow_spec import (
    TOPP,
    Python,
    ResultView,
    SelectFiles,
    Tab,
    Upload,
    Widget,
    WorkflowSpec,
)

TOPP_WORKFLOW = WorkflowSpec(
    name="TOPP Workflow",
    module="src.Workflow",
    cls="Workflow",
    description="Detect metabolite features in each mzML file and link them across files.",
    upload=[
        Upload(
            key="mzML-files",
            name="MS data",
            file_types=["mzML"],
            fallback=[str(f) for f in sorted(Path("example-data", "mzML").glob("*.mzML"))],
        ),
    ],
    configure=[
        SelectFiles("mzML-files", name="mzML files", multiple=True),
        Tab(
            "Feature Detection",
            [TOPP("FeatureFinderMetabo", custom_defaults={"algorithm:common:noise_threshold_int": 1000.0})],
        ),
        Tab("Feature Linking", [TOPP("FeatureLinkerUnlabeledKD")]),
        Tab(
            "Python Custom Tool",
            [
                Widget("run-python-script", False, "Run custom Python script", widget_type="checkbox"),
                Python("example", visible_if={"key": "run-python-script", "equals": True}),
            ],
        ),
    ],
    results=[
        ResultView(
            component="consensus-features",
            title="Consensus features",
            props={"file": "results/feature-linking/feature_matrix.tsv"},
        ),
    ],
)

WORKFLOWS = [TOPP_WORKFLOW]


def get_workflow(slug: str) -> WorkflowSpec:
    from fastapi import HTTPException

    for wf in WORKFLOWS:
        if wf.slug == slug:
            return wf
    raise HTTPException(404, f"Unknown workflow {slug!r}")
