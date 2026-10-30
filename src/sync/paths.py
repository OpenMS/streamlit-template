"""Which workspace files take part in sync, and how they are hashed.

Both sides apply the same rules: the client to decide what to send, the
server to refuse anything else. Paths are workspace-relative POSIX strings.

Pushed (offline -> online), the files a user uploads and nothing else:
    mzML-files/<file or folder>
    <workflow>/input-files/<key>/<file or folder>

Parameters are not synced as files: a run started from the desktop app
carries them (see ``runs.py``).

Pulled (online -> offline):
    <workflow>/results/<anything>
    <workflow>/runs/<run id>/<anything>    runs of a multi-run workflow,
                                           once they are no longer running

``external_files.txt`` is never sent as such. Each absolute path it lists is
sent as a real file (or folder, for Bruker ``.d`` acquisitions) inside the
directory that lists it, because the offline machine's paths mean nothing
on the server.
"""

import hashlib
import json
import os
import threading
from pathlib import Path, PurePosixPath
from typing import Iterator

EXTERNAL_FILES = "external_files.txt"
HASH_BLOCK = 8 * 1024 * 1024


def safe_relpath(rel: str) -> PurePosixPath | None:
    """Return ``rel`` as a workspace-relative path, or None if it is unsafe.

    Rejects absolute paths, backslashes, ``..`` and hidden components, so a
    path can neither leave the workspace nor touch sync state such as
    ``.sync.json``.
    """
    if not rel or "\\" in rel or "\x00" in rel:
        return None
    p = PurePosixPath(rel)
    if p.is_absolute():
        return None
    for part in p.parts:
        if part in ("", ".", "..") or part.startswith("."):
            return None
    return p


def is_pushable(rel: str) -> bool:
    p = safe_relpath(rel)
    if p is None or p.name == EXTERNAL_FILES:
        return False
    parts = p.parts
    if parts[0] == "mzML-files" and len(parts) >= 2:
        return True
    return len(parts) >= 4 and parts[1] == "input-files"


def is_pullable(rel: str) -> bool:
    p = safe_relpath(rel)
    if p is None:
        return False
    if len(p.parts) >= 3 and p.parts[1] == "results":
        return True
    return len(p.parts) >= 4 and p.parts[1] == "runs"


def _run_ended(run_dir: Path) -> bool:
    """A run's files are final once its run.json no longer says running."""
    try:
        return json.loads(Path(run_dir, "run.json").read_text(encoding="utf-8"))["status"] != "running"
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _walk(base: Path, rel: PurePosixPath) -> Iterator[tuple[str, Path]]:
    """Yield (rel, path) for ``base`` and every regular file below it."""
    if base.is_file():
        yield str(rel), base
        return
    if not base.is_dir():
        return
    for root, dirs, files in os.walk(base, followlinks=True):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        root_rel = rel / Path(root).relative_to(base).as_posix()
        for name in sorted(files):
            if name.startswith("."):
                continue
            # PurePosixPath drops the "." of the top folder; os.path.normpath
            # would turn the separators into backslashes on Windows.
            yield str(root_rel / name), Path(root, name)


def _input_dir_entries(directory: Path, rel: PurePosixPath) -> Iterator[tuple[str, Path]]:
    if not directory.is_dir():
        return
    for child in sorted(directory.iterdir()):
        if child.name.startswith("."):
            continue
        if child.name == EXTERNAL_FILES:
            for line in child.read_text().splitlines():
                line = line.strip()
                if line and Path(line).exists():
                    target = Path(line)
                    yield from _walk(target, rel / target.name)
            continue
        yield from _walk(child, rel / child.name)


def push_entries(workspace: Path) -> dict[str, Path]:
    """Map every pushable path of a local workspace to the file to read."""
    entries: dict[str, Path] = {}

    def add(items):
        for rel, path in items:
            if is_pushable(rel):
                entries[rel] = path

    add(_input_dir_entries(Path(workspace, "mzML-files"), PurePosixPath("mzML-files")))
    for wf in sorted(p for p in Path(workspace).iterdir() if p.is_dir()):
        if wf.name.startswith(".") or wf.name == "mzML-files":
            continue
        inputs = Path(wf, "input-files")
        if inputs.is_dir():
            for key in sorted(k for k in inputs.iterdir() if k.is_dir()):
                add(_input_dir_entries(key, PurePosixPath(wf.name, "input-files", key.name)))
    return entries


def pull_entries(workspace: Path) -> dict[str, Path]:
    """Map every pullable path of a server workspace to its file."""
    entries: dict[str, Path] = {}
    if not Path(workspace).is_dir():
        return entries
    for wf in sorted(p for p in Path(workspace).iterdir() if p.is_dir()):
        if wf.name.startswith("."):
            continue
        found = list(_walk(Path(wf, "results"), PurePosixPath(wf.name, "results")))
        runs = Path(wf, "runs")
        for run in sorted(r for r in runs.iterdir() if r.is_dir()) if runs.is_dir() else ():
            if _run_ended(run):
                found += _walk(run, PurePosixPath(wf.name, "runs", run.name))
        for rel, path in found:
            if is_pullable(rel):
                entries[rel] = path
    return entries


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(HASH_BLOCK):
            h.update(block)
    return h.hexdigest()


class HashCache:
    """sha256 per file, recomputed only when size or mtime changed.

    Hashing a multi-GB raw file takes seconds to minutes, and a manifest is
    built on every sync, so the digests are kept in a JSON file next to the
    workspace data and keyed by (size, mtime_ns).
    """

    def __init__(self, cache_file: Path):
        self.cache_file = Path(cache_file)
        try:
            self._data = json.loads(self.cache_file.read_text())
        except (OSError, ValueError):
            self._data = {}
        self._dirty = False

    def digest(self, path: Path) -> tuple[int, str]:
        st = os.stat(path)
        key = str(Path(path).absolute())
        hit = self._data.get(key)
        if hit and hit["size"] == st.st_size and hit["mtime_ns"] == st.st_mtime_ns:
            return st.st_size, hit["sha256"]
        digest = sha256_file(path)
        self._data[key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": digest}
        self._dirty = True
        return st.st_size, digest

    def remember(self, path: Path, digest: str) -> None:
        """Record a digest already known, e.g. one verified during upload."""
        st = os.stat(path)
        self._data[str(Path(path).absolute())] = {
            "size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": digest,
        }
        self._dirty = True

    def manifest(self, entries: dict[str, Path]) -> dict[str, dict]:
        out = {}
        for rel, path in entries.items():
            size, digest = self.digest(path)
            out[rel] = {"size": size, "sha256": digest}
        return out

    def save(self) -> None:
        if not self._dirty:
            return
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        # One temp file per thread: the sidebar refreshes states while a
        # transfer may be running, and both save the cache.
        tmp = self.cache_file.with_name(
            f"{self.cache_file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(self._data))
        os.replace(tmp, self.cache_file)
        self._dirty = False
