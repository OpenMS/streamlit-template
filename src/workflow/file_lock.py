"""Short cross-process locks for shared workflow state on desktop platforms."""

import errno
import os
import time
from contextlib import contextmanager
from pathlib import Path

_WINDOWS = os.name == "nt"


@contextmanager
def file_lock(path, *, blocking=True):
    """Hold an advisory lock, released on exit or process termination.

    Keep the lock file at a stable path outside folders that an operation can
    remove. Unlinking it would let another caller lock a different file at the
    same name while the first caller still holds its original open handle.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if _WINDOWS:
            # This standard-library module is available only on Windows.
            import msvcrt  # pylint: disable=import-error

            # Windows byte-range locks need one stable byte to lock. Repeated
            # initializers can write the same byte without changing its role.
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    if not blocking:
                        raise BlockingIOError(error.errno, "Workflow state is locked", str(path)) from error
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            fcntl.flock(handle.fileno(), flags)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
