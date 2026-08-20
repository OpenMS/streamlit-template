"""
Streamlit free access to settings.json.

Inside the RQ work horse there is no ScriptRunContext, so `st.session_state` is
an empty global mock and every setting read through session state silently
falls back to its hardcoded default there (DEFECTS.md G1). Code which has to
behave the same in the worker and in a Streamlit session reads the settings
from disk through this module instead.

Kept dependency free on purpose: `src/workflow/tasks.py` runs inside the worker
and must stay importable without Streamlit.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "settings.json"


def load_settings(path: Path | str = SETTINGS_FILE_NAME) -> dict:
    """
    Read the app settings from disk.

    The path is resolved against the process working directory by default,
    which is how every other reader in this repository resolves it (app.py:8,
    src/common/common.py:362, test_gui.py:14). Deliberately not memoised: the
    caller decides how long a value stays valid.

    Settings are only ever read here, never written back, so tolerating an
    unreadable file cannot destroy it - unlike a workflow's params.json, see
    ParameterManager.read_parameters_strict().

    Total by construction: it never raises, whatever is on disk. The two other
    readers in this repository (app.py, src/common/common.py) open settings.json
    with the platform default encoding, so a file hand-edited on a cp1252 box
    loads there; decoding with errors="replace" here keeps this loader from
    being the one place that hard-fails on it - inside the RQ work horse, where
    nothing catches it and the job dies.

    Args:
        path: Location of the settings file.

    Returns:
        dict: The parsed settings, or an empty dict if the file is absent,
            unreadable or does not hold a JSON object. Callers are expected to
            supply their own defaults per key.
    """
    settings_file = Path(path)
    try:
        with open(settings_file, "r", encoding="utf-8", errors="replace") as f:
            settings = json.load(f)
    except FileNotFoundError:
        logger.warning(
            "No %s in %s, falling back to default settings.", settings_file, Path.cwd()
        )
        return {}
    except (ValueError, OSError) as e:
        # ValueError covers json.JSONDecodeError and UnicodeDecodeError, which
        # is a ValueError rather than an OSError - the gap that let an
        # undecodable settings.json escape a handler documented as total.
        logger.warning(
            "Could not read %s (%s), falling back to default settings.", settings_file, e
        )
        return {}

    if not isinstance(settings, dict):
        logger.warning(
            "%s does not hold a JSON object (found %s), falling back to default settings.",
            settings_file,
            type(settings).__name__,
        )
        return {}
    return settings
