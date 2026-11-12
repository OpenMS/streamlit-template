"""
Memory of the machine a run will use, and the check of a run's estimate against it.

Streamlit-free, so the worker (``tasks.execute_workflow``) can use it as well
as the Run page.

The limit is the smaller of the machine's memory and the cgroup memory limit
(``docker run --memory``, a Kubernetes ``limits.memory``). A Streamlit pod does
not run the workflows online: the rq-worker pods do, with a limit of their
own. ``WORKER_MEMORY_LIMIT`` (bytes, or a Kubernetes quantity such as
``16Gi``), set on the Streamlit container by the memory-tier components, tells
the page the worker's limit; without it the page checks against its own
process, which is right for the local app and for a single container that runs
its workers itself.
"""

import os
import re
from pathlib import Path

CGROUP_V2_MEMORY_MAX = Path("/sys/fs/cgroup/memory.max")
CGROUP_V2_MEMORY_CURRENT = Path("/sys/fs/cgroup/memory.current")
CGROUP_V1_MEMORY_LIMIT = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
CGROUP_V1_MEMORY_USAGE = Path("/sys/fs/cgroup/memory/memory.usage_in_bytes")
MEMINFO = Path("/proc/meminfo")

WORKER_MEMORY_ENV = "WORKER_MEMORY_LIMIT"

# A run is warned about when its estimate is above this share of the memory.
# The rest is the app itself, the page caches and an estimate's error.
HEADROOM = 0.9

# cgroup v1 writes a huge number (close to 2**63) for "no limit".
_NO_LIMIT = 1 << 60

_UNITS = {
    "": 1, "k": 1000, "m": 1000 ** 2, "g": 1000 ** 3, "t": 1000 ** 4,
    "ki": 1024, "mi": 1024 ** 2, "gi": 1024 ** 3, "ti": 1024 ** 4,
}


def parse_quantity(text) -> int | None:
    """Bytes of ``16Gi``, ``512Mi``, ``2G`` or a plain number; None if unreadable."""
    if text is None:
        return None
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmMgGtT]i?)?[bB]?\s*", str(text))
    if not match:
        return None
    value = float(match.group(1)) * _UNITS[(match.group(2) or "").lower()]
    return int(value) if value > 0 else None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _meminfo(field: str) -> int | None:
    text = _read(MEMINFO)
    if not text:
        return None
    match = re.search(rf"^{field}:\s+(\d+)\s*kB", text, re.MULTILINE)
    return int(match.group(1)) * 1024 if match else None


def cgroup_memory_limit() -> int | None:
    """Memory limit of this container's cgroup in bytes, or None without one."""
    raw = _read(CGROUP_V2_MEMORY_MAX)
    if raw is not None:
        return None if raw == "max" else parse_quantity(raw)
    raw = _read(CGROUP_V1_MEMORY_LIMIT)
    value = parse_quantity(raw)
    return value if value is not None and value < _NO_LIMIT else None


def memory_limit() -> int | None:
    """Memory a run here may use at most: the cgroup limit or the machine's memory."""
    limits = [v for v in (cgroup_memory_limit(), _meminfo("MemTotal")) if v]
    return min(limits) if limits else None


def available_memory() -> int | None:
    """Memory free for a run now, in bytes, or None where it cannot be read.

    The smaller of what the machine has available (``MemAvailable``) and what
    the cgroup limit leaves after the container's current use.
    """
    values = []
    available = _meminfo("MemAvailable")
    if available is not None:
        values.append(available)
    limit = cgroup_memory_limit()
    if limit:
        used = parse_quantity(_read(CGROUP_V2_MEMORY_CURRENT) or _read(CGROUP_V1_MEMORY_USAGE)) or 0
        values.append(max(0, limit - used))
    return min(values) if values else None


def run_memory(online: bool = False) -> tuple[int | None, str]:
    """Memory a run gets and where it runs: ``(bytes, place)``.

    Online with ``WORKER_MEMORY_LIMIT`` set, the worker's limit (a worker runs
    one job at a time, so all of it); otherwise this process's available
    memory.
    """
    if online:
        worker = parse_quantity(os.environ.get(WORKER_MEMORY_ENV))
        if worker:
            return worker, "the server that runs analyses"
    return available_memory(), "this computer" if not online else "the server"


def format_bytes(n: float) -> str:
    """``12.3 GB``, ``850 MB``."""
    if n >= 1000 ** 3:
        return f"{n / 1000 ** 3:.1f} GB"
    return f"{max(n, 0) / 1000 ** 2:.0f} MB"


def memory_warning(estimate: int | None, memory: int | None, place: str = "this computer",
                   advice: str = "") -> str | None:
    """The warning for a run estimated to need ``estimate`` bytes, or None.

    None while either number is unknown or the estimate fits in HEADROOM of
    the memory.
    """
    if not estimate or memory is None or estimate <= HEADROOM * memory:
        return None
    text = (
        f"This analysis may need about {format_bytes(estimate)} of memory, and "
        f"{place} has {format_bytes(memory)} for it. It may stop when the memory runs out."
    )
    return f"{text} {advice}".strip()
