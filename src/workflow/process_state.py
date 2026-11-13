"""Track process identity without mistaking stale PIDs for owned workers."""

import json
import math
import os
import socket
import tempfile
from functools import lru_cache
from pathlib import Path

import psutil

_FOREIGN_PROCESS = object()
# Seconds between a legacy (empty) marker's mtime and its process's start.
_LEGACY_PID_REUSE_SLACK = 5.0


@lru_cache(maxsize=1)
def process_namespace() -> str:
    """Identify this host/boot/PID namespace for shared-workspace markers."""
    host = socket.gethostname()
    try:
        namespace = os.readlink("/proc/self/ns/pid")
        boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError:
        namespace, boot = "host", str(psutil.boot_time())
    return f"{host}|{boot}|{namespace}"


def _same_namespace(recorded, current: str) -> bool:
    """Compare exact Linux identities and stable host boot estimates elsewhere."""
    if recorded == current:
        return True
    if not isinstance(recorded, str):
        return False
    try:
        old_host, old_boot, old_namespace = recorded.rsplit("|", 2)
        host, boot, namespace = current.rsplit("|", 2)
        if old_host != host or old_namespace != "host" or namespace != "host":
            return False
        previous, present = float(old_boot), float(boot)
        # psutil's Windows boot estimate can vary by a second between Python
        # processes. Process creation time below is still checked exactly.
        return math.isfinite(previous) and math.isfinite(present) and abs(previous - present) <= 2
    except ValueError:
        return False


def pid_markers(pid_dir: Path) -> list[Path]:
    """Snapshot positive numeric regular markers; a removed directory is idle."""
    try:
        markers = list(Path(pid_dir).iterdir())
    except FileNotFoundError:
        return []
    return [
        marker for marker in markers
        if marker.name.isascii() and marker.name.isdecimal()
        and int(marker.name) > 0
        and not marker.is_symlink() and marker.is_file()
    ]


def register_process_marker(marker: Path, pid: int) -> None:
    """Publish PID and process birth time together, without partial records.

    Creation time distinguishes an original worker from another process that
    later receives the same PID, including after a container restart.
    """
    marker = Path(marker)
    try:
        process = psutil.Process(pid)
        created = process.create_time()
    except psutil.NoSuchProcess:
        return  # A worker that already exited no longer needs tracking.
    except psutil.AccessDenied as error:
        raise PermissionError(f"Cannot record process {pid} creation time") from error
    record = {"schema": 1, "pid": pid, "create_time": created, "namespace": process_namespace()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=f".{pid}-", suffix=".tmp",
            dir=marker.parent, delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(record, handle, allow_nan=False)
        os.replace(temporary, marker)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _remove_marker(marker: Path) -> None:
    try:
        marker.unlink(missing_ok=True)
    except OSError:
        pass  # An unremovable marker does not make a proven-dead process live.


def _live_marker_process(marker: Path, *, prune_stale=True):
    """Return the live process and whether its stored birth time proves ownership."""
    try:
        text = marker.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, False
    except UnicodeError:
        text = ""
    try:
        record = json.loads(text)
    except (ValueError, UnicodeError):
        record = None
    if (
        isinstance(record, dict) and isinstance(record.get("namespace"), str)
        and record["namespace"] and not _same_namespace(record["namespace"], process_namespace())
    ):
        # Offline markers from a previous container instance are stale. Queue
        # readers instead retain possible remote-worker records until RQ ACKs.
        if prune_stale:
            _remove_marker(marker)
            return None, False
        return _FOREIGN_PROCESS, False
    try:
        process = psutil.Process(int(marker.name))
        alive = process.is_running() and process.status() not in {
            psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD
        }
    except (psutil.NoSuchProcess, ValueError, OverflowError):
        alive = False
    if not alive:
        if prune_stale:
            _remove_marker(marker)
        return None, False
    if (
        not isinstance(record, dict)
        or type(record.get("schema")) is not int
        or record["schema"] != 1
        or type(record.get("pid")) is not int
        or record["pid"] != int(marker.name)
        or type(record.get("create_time")) not in (int, float)
        or not math.isfinite(record["create_time"])
        or record["create_time"] <= 0
        or not _same_namespace(record.get("namespace"), process_namespace())
    ):
        # Empty legacy markers and damaged records cannot establish ownership.
        # They still keep a live process busy, but are never used to signal it.
        # A legacy marker is touched right after its process started, so a
        # process created well after the marker got a reused PID.
        try:
            reused = process.create_time() > marker.stat().st_mtime + _LEGACY_PID_REUSE_SLACK
        except FileNotFoundError:
            return None, False
        if reused:
            if prune_stale:
                _remove_marker(marker)
            return None, False
        return process, False
    if process.create_time() != record["create_time"]:
        if prune_stale:
            _remove_marker(marker)
        return None, False
    return process, True


def local_workflow_running(pid_dir: Path) -> bool:
    """Inspect every marker, retaining live or unknown processes conservatively."""
    try:
        markers = pid_markers(pid_dir)
    except OSError:
        return True
    running = False
    for marker in markers:
        running = prune_exited_marker(marker) or running
    return running


def prune_exited_marker(marker: Path) -> bool:
    """Prune dead/reused PIDs; return True for a live or unknown process."""
    try:
        process, _owned = _live_marker_process(marker)
        return process is not None
    except (OSError, psutil.AccessDenied):
        return True


def owned_workflow_running(pid_dir: Path) -> bool:
    """Probe proven local ownership without pruning possible remote markers.

    Online readers can share files with workers in another PID namespace.
    Their queue acknowledgement is authoritative; a local PID mismatch must
    not remove the remote worker's tracking record.
    """
    try:
        for marker in pid_markers(pid_dir):
            process, owned = _live_marker_process(marker, prune_stale=False)
            if process is not None and owned:
                return True
    except (OSError, psutil.AccessDenied):
        return False  # The acknowledged queue state remains authoritative.
    return False


def signal_owned_process(marker: Path, sig: int, *, prune_stale=True) -> bool:
    """Signal only the exact recorded process, never a reused or legacy PID.

    psutil rechecks the Process object's identity when sending the signal, so
    reuse between our comparison and signal delivery is rejected as well.
    """
    try:
        process, owned = _live_marker_process(marker, prune_stale=prune_stale)
        if process is None:
            return False
        if not owned:
            raise PermissionError(
                f"Cannot verify ownership of process {marker.name}; its legacy or invalid tracking marker was retained."
            )
        if sig == 9:
            process.kill()  # Windows supports kill(), but not send_signal(9).
        else:
            process.send_signal(sig)
        return True
    except (psutil.NoSuchProcess, ProcessLookupError):
        if prune_stale:
            _remove_marker(marker)
        return False
    except psutil.AccessDenied as error:
        raise PermissionError(f"Cannot signal process {marker.name}: access denied") from error
    except OSError as error:
        raise PermissionError(f"Cannot verify or signal process {marker.name}: {error}") from error
