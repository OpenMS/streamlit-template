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
import math
from pathlib import Path

logger = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "settings.json"

CGROUP_V2_CPU_MAX = Path("/sys/fs/cgroup/cpu.max")
CGROUP_V1_CPU_QUOTA = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
CGROUP_V1_CPU_PERIOD = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")


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


def _read_int(path: Path) -> int | None:
    """Read a single integer out of a cgroup pseudo-file, or None."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def detect_cpu_quota() -> int | None:
    """
    Number of CPUs this container is actually allowed to use, from its cgroup.

    Returns None whenever no CPU ceiling can be established - not on Linux, not
    in a container, or in a container with no quota set - and the caller then
    falls back to its configured value. None is "do not know", never "one".

    Why this exists: the rq-worker runs at ``requests.cpu == limits.cpu``
    (Guaranteed QoS), so its pod spec IS its CPU allocation, and the two are
    sized per deployment by the memory-tier components. A single
    ``max_threads.online`` in settings.json cannot be right for both a 4 cpu
    worker and a 20 cpu one, and the one that was there described neither.

    Both cgroup generations are handled:

    * v2 (``/sys/fs/cgroup/cpu.max``) holds ``"<quota> <period>"``, or
      ``"max <period>"`` when unconstrained.
    * v1 (``cpu.cfs_quota_us`` / ``cpu.cfs_period_us``) uses a quota of ``-1``
      to mean unconstrained.

    Rounded UP: Kubernetes turns ``cpu: 1500m`` into a quota of 1.5 cores, and
    two runnable threads throttled to 1.5 cores finish sooner than one thread
    using 1.0 and leaving 0.5 idle.

    Returns:
        int | None: CPU count, at least 1, or None if no quota applies.
    """
    quota_us: float | None = None
    period_us: int | None = None

    try:
        raw = CGROUP_V2_CPU_MAX.read_text(encoding="utf-8").strip()
    except OSError:
        raw = ""
    if raw:
        parts = raw.split()
        # "max <period>" is the unconstrained case and must read as None, not
        # as a fallthrough to v1 - a host with both hierarchies mounted would
        # otherwise answer from the wrong one.
        if parts[0] == "max":
            return None
        try:
            quota_us = float(parts[0])
            period_us = int(parts[1]) if len(parts) > 1 else 100000
        except (IndexError, ValueError):
            logger.warning("Unparsable %s: %r", CGROUP_V2_CPU_MAX, raw)
            return None
    else:
        v1_quota = _read_int(CGROUP_V1_CPU_QUOTA)
        if v1_quota is None or v1_quota <= 0:
            # -1 is the documented "no limit"; 0 is not a legal quota and is
            # treated the same rather than propagated as a zero CPU budget.
            return None
        quota_us = float(v1_quota)
        period_us = _read_int(CGROUP_V1_CPU_PERIOD) or 100000

    if not quota_us or not period_us or period_us <= 0:
        return None
    return max(1, math.ceil(quota_us / period_us))
