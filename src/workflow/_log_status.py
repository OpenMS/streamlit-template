"""
Pure helper for classifying a workflow log file's terminal state.

Kept streamlit-free so the static-display dispatch in StreamlitUI can be
unit-tested without a Streamlit runtime.
"""

from typing import Literal

LogOutcome = Literal["finished", "cancelled", "error"]

CANCELLED_MARKER = "WORKFLOW CANCELLED"
FINISHED_MARKER = "WORKFLOW FINISHED"


def classify_log_outcome(content: str) -> LogOutcome:
    """
    Classify a workflow log's terminal state from its full text.

    Order matters: a TOPP subprocess often dies as the worker is being torn
    down, so a partial 'ERROR:' line followed by the cancellation marker is
    still a cancellation, not a crash. Cancellation therefore wins over
    finished (defensive — both shouldn't appear) and over the implicit error
    fallback.
    """
    if CANCELLED_MARKER in content:
        return "cancelled"
    if FINISHED_MARKER in content:
        return "finished"
    return "error"
