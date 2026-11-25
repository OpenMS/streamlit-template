"""Skip a test of the template's example app in an app that replaced it.

Every app gets the template's tests through the template sync. Most of them
test the framework, but a few test the example app (`src/Workflow.py`'s
`Workflow`, the example's pages), which an app replaces with its own workflow
and pages. Those tests call `skip_without_example(...)` at module level, or
use `needs_example(...)` on a single test, so they run in the template and
are skipped in an app instead of failing there.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "src" / "Workflow.py"


def has_example(*pages: str) -> bool:
    """True when the example workflow and each named page are there."""
    try:
        source = WORKFLOW.read_text(encoding="utf-8")
    except OSError:
        return False
    if "class Workflow(WorkflowManager)" not in source:
        return False
    return all((ROOT / page).exists() for page in pages)


def _reason(pages) -> str:
    named = ", ".join(("src/Workflow.py",) + tuple(pages))
    return f"tests the template's example app ({named}), which this app replaced"


def skip_without_example(*pages: str) -> None:
    """Skip the whole module unless the example app is there."""
    if not has_example(*pages):
        pytest.skip(_reason(pages), allow_module_level=True)


def needs_example(*pages: str):
    """Mark one test to run only where the example app is there."""
    return pytest.mark.skipif(not has_example(*pages), reason=_reason(pages))


def needs_pages(*pages: str):
    """Mark one test to run only where each named template page is there."""
    missing = [p for p in pages if not (ROOT / p).exists()]
    return pytest.mark.skipif(
        bool(missing), reason=f"this app replaced {', '.join(missing)}")
