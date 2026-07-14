"""
Tests for the classify_log_outcome helper used by the run-page static display.

The UI must render three different messages depending on what's in the
workflow log:
    finished  -> "Workflow completed successfully" (success)
    cancelled -> "Workflow was cancelled"          (warning)
    error     -> "Errors occurred, check log file" (error)

This helper is split out so the dispatch is unit-testable without booting
Streamlit and without pulling in pyopenms.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow._log_status import classify_log_outcome


def test_finished_marker_returns_finished():
    assert classify_log_outcome(
        "STARTING WORKFLOW\n\nstep 1\n\nWORKFLOW FINISHED\n\n"
    ) == "finished"


def test_cancelled_marker_returns_cancelled():
    assert classify_log_outcome(
        "STARTING WORKFLOW\n\nstep 1\n\nWORKFLOW CANCELLED\n\n"
    ) == "cancelled"


def test_cancelled_takes_precedence_over_partial_error():
    """
    A TOPP subprocess often dies as the worker is being torn down, leaving
    an ERROR line followed by the cancellation marker. The user-meaningful
    state is 'cancelled', not 'error'.
    """
    assert classify_log_outcome(
        "STARTING WORKFLOW\n\nERROR: subprocess died\n\nWORKFLOW CANCELLED\n\n"
    ) == "cancelled"


def test_truncated_log_returns_error():
    assert classify_log_outcome("STARTING WORKFLOW\n\nstep 1\n\n") == "error"


def test_empty_log_returns_error():
    assert classify_log_outcome("") == "error"
