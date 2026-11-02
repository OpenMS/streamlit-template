"""
Keeps every run of a workflow as its own named result set.

A workflow that sets ``multi_run = True`` writes each run into
``<workflow_dir>/runs/<run_id>/`` instead of overwriting
``<workflow_dir>/results/``:

    runs/<run_id>/run.json      name, status and timestamps
    runs/<run_id>/params.json   the parameters the run was started with
    runs/<run_id>/results/      everything execution() wrote
    runs/<run_id>/logs/         the run's logs, copied when it ends

This module must stay importable without Streamlit: the RQ worker
(``tasks.py``) uses it to mark a queued run finished or failed.
"""

import json
import shutil
import stat
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

RUN_FILE = "run.json"
MAX_NAME_LENGTH = 100
# Largest unpacked size import_zip() accepts by default
MAX_IMPORT_BYTES = 20 * 1024**3


class RunImportError(ValueError):
    """A ZIP that can not be imported as a run; the message says why."""

# Run states written to run.json. A run whose process died without reaching
# finish() stays "running"; the UI shows it as interrupted once the workflow
# is no longer running.
RUNNING = "running"
FINISHED = "finished"
FAILED = "failed"
CANCELLED = "cancelled"


class RunManager:
    """Creates, lists, renames, deletes and archives the runs of one workflow."""

    def __init__(self, workflow_dir: Path) -> None:
        self.workflow_dir = Path(workflow_dir)
        self.runs_dir = Path(self.workflow_dir, "runs")

    # Paths

    def run_dir(self, run_id: str) -> Path:
        return Path(self.runs_dir, run_id)

    def results_dir(self, run_id: str) -> Path:
        return Path(self.runs_dir, run_id, "results")

    def params_file(self, run_id: str) -> Path:
        return Path(self.runs_dir, run_id, "params.json")

    # Reading

    def get(self, run_id: Optional[str]) -> Optional[dict]:
        """The run's metadata, or None if there is no such run."""
        if not run_id or not _is_safe_id(run_id):
            return None
        try:
            with open(Path(self.run_dir(run_id), RUN_FILE), "r", encoding="utf-8") as f:
                run = json.load(f)
        except (OSError, ValueError):
            return None
        run["id"] = run_id
        return run

    def list_runs(self, status: Optional[str] = None) -> list[dict]:
        """All runs, newest first. Pass ``status`` to keep only runs in that state."""
        if not self.runs_dir.is_dir():
            return []
        runs = [self.get(d.name) for d in self.runs_dir.iterdir() if d.is_dir()]
        runs = [r for r in runs if r is not None]
        if status is not None:
            runs = [r for r in runs if r.get("status") == status]
        return sorted(runs, key=lambda r: (r.get("created", ""), r["id"]), reverse=True)

    def latest(self, status: Optional[str] = FINISHED) -> Optional[str]:
        """Id of the newest run (in ``status``, if given), or None."""
        runs = self.list_runs(status)
        return runs[0]["id"] if runs else None

    def params(self, run_id: str) -> dict:
        """The parameters a run was started with (empty if not recorded)."""
        try:
            with open(self.params_file(run_id), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    # Writing

    def new_run(self, name: str = "", params_file: Optional[Path] = None) -> str:
        """
        Create the directory for a new run and return its id.

        Args:
            name: Display name. Defaults to "Run <n>".
            params_file: The workflow's params.json, copied into the run so the
                results can be read with the parameters that produced them.
        """
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_id, n = base, 1
        while self.run_dir(run_id).exists():
            n += 1
            run_id = f"{base}-{n}"
        self.results_dir(run_id).mkdir(parents=True)
        name = _clean_name(name) or self.default_name()
        self._write(run_id, {"name": name, "created": _now(), "status": RUNNING})
        if params_file is not None and Path(params_file).exists():
            shutil.copy2(params_file, self.params_file(run_id))
        return run_id

    def finish(self, run_id: Optional[str], status: str) -> None:
        """Record how a run ended and keep a copy of its logs."""
        run = self.get(run_id)
        # A cancelled run stays cancelled when its dying process reports failure.
        if run is None or run.get("status") == CANCELLED:
            return
        run.update(status=status, finished=_now())
        self._write(run_id, run)
        logs = Path(self.workflow_dir, "logs")
        if logs.is_dir():
            shutil.copytree(logs, Path(self.run_dir(run_id), "logs"), dirs_exist_ok=True)

    def rename(self, run_id: str, name: str) -> bool:
        """Set a run's display name. False if the name is empty or too long."""
        run = self.get(run_id)
        name = _clean_name(name)
        if run is None or not name or len(name) > MAX_NAME_LENGTH:
            return False
        run["name"] = name
        self._write(run_id, run)
        return True

    def delete(self, run_id: str) -> bool:
        """Delete a run and all its files."""
        if self.get(run_id) is None:
            return False
        shutil.rmtree(self.run_dir(run_id), ignore_errors=True)
        Path(self.workflow_dir, "downloads", f"{run_id}.zip").unlink(missing_ok=True)
        return True

    def zip(self, run_id: str, exclude: Optional[list[str]] = None) -> Path:
        """
        Pack a run's results, parameters and logs into
        ``<workflow_dir>/downloads/<run_id>.zip`` and return the path.

        Args:
            exclude: File or folder names to leave out (glob patterns allowed),
                e.g. caches such as ``["insight_cache"]``.
        """
        from fnmatch import fnmatch

        exclude = list(exclude or [])
        run_dir = self.run_dir(run_id)
        zip_path = Path(self.workflow_dir, "downloads", f"{run_id}.zip")
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(run_dir.rglob("*")):
                rel = path.relative_to(run_dir)
                if path.is_file() and not any(
                    fnmatch(part, p) for part in rel.parts for p in exclude
                ):
                    zf.write(path, rel)
        return zip_path

    def import_zip(
        self, source, name: str = "", max_bytes: int = MAX_IMPORT_BYTES
    ) -> str:
        """
        Add a run from a ZIP made by zip() and return its new id.

        The ZIP holds ``results/`` and, as zip() writes them, ``run.json``,
        ``params.json`` and ``logs/``; a ZIP of the run folder itself (all of
        that under one top folder) works too. The run keeps its name, status,
        times and parameters, and gets a new id, so importing the same ZIP
        twice gives two runs.

        Every member is checked before anything is written: absolute paths,
        ``..``, drive letters, backslashes and symbolic links are refused, as
        is a ZIP that unpacks to more than ``max_bytes``. Unpacking goes to a
        temporary folder that becomes the run only when it is complete.

        Args:
            source: Path or binary file object (e.g. a Streamlit upload).
            name: Display name; defaults to the name in run.json, then
                "Imported run".
            max_bytes: Largest unpacked size accepted.

        Raises:
            RunImportError: The file is not such a ZIP, or is unsafe.
        """
        try:
            archive = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, OSError) as e:
            raise RunImportError("This is not a ZIP file.") from e
        with archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            for m in archive.infolist():
                _check_member(m)
            total = sum(m.file_size for m in members)
            if total > max_bytes:
                raise RunImportError(
                    f"The ZIP unpacks to {total / 1024**3:.1f} GB, more than "
                    f"the {max_bytes / 1024**3:.1f} GB allowed."
                )
            prefix = _run_prefix([m.filename for m in members])
            if prefix is None:
                raise RunImportError(
                    "This ZIP holds no run: a run's ZIP has a results/ folder."
                )

            meta = {}
            if f"{prefix}{RUN_FILE}" in archive.namelist():
                try:
                    meta = json.loads(archive.read(f"{prefix}{RUN_FILE}"))
                except ValueError:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}

            tmp = Path(self.workflow_dir, f".run-import-{uuid.uuid4().hex[:8]}")
            tmp.mkdir(parents=True)
            try:
                for m in members:
                    rel = m.filename[len(prefix):]
                    if not rel or rel == RUN_FILE:
                        continue
                    target = Path(tmp, *rel.split("/"))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(m) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                params = Path(tmp, "params.json")
                if params.exists():
                    try:
                        if not isinstance(json.loads(params.read_text(encoding="utf-8")), dict):
                            raise ValueError
                    except ValueError:
                        params.unlink()
                Path(tmp, "results").mkdir(exist_ok=True)

                run = {
                    "name": _clean_name(name) or _clean_name(meta.get("name")) or "Imported run",
                    "created": meta.get("created") or _now(),
                    "status": meta.get("status") if meta.get("status") in (
                        FINISHED, FAILED, CANCELLED
                    ) else FINISHED,
                    "imported": _now(),
                }
                if meta.get("finished"):
                    run["finished"] = meta["finished"]
                run["name"] = self._unique_name(run["name"][:MAX_NAME_LENGTH])

                self.runs_dir.mkdir(parents=True, exist_ok=True)
                base = datetime.now().strftime("%Y%m%d-%H%M%S")
                run_id, n = base, 1
                while self.run_dir(run_id).exists():
                    n += 1
                    run_id = f"{base}-{n}"
                with open(Path(tmp, RUN_FILE), "w", encoding="utf-8") as f:
                    json.dump(run, f, indent=2)
                tmp.rename(self.run_dir(run_id))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        return run_id

    def _unique_name(self, name: str) -> str:
        taken = {r.get("name") for r in self.list_runs()}
        if name not in taken:
            return name
        n = 2
        while f"{name} ({n})" in taken:
            n += 1
        return f"{name} ({n})"

    def adopt_legacy_results(self) -> Optional[str]:
        """
        Turn a ``<workflow_dir>/results`` left by a single-run version of the
        workflow into a run named "Earlier run", so switching a workflow to
        multi-run keeps what users already computed. Returns the new run id,
        or None if there was nothing to adopt.
        """
        legacy = Path(self.workflow_dir, "results")
        if not legacy.is_dir() or not any(legacy.iterdir()) or self.list_runs():
            return None
        created = datetime.fromtimestamp(legacy.stat().st_mtime)
        run_id = created.strftime("%Y%m%d-%H%M%S")
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(legacy), str(self.results_dir(run_id)))
        except OSError:
            return None
        self._write(
            run_id,
            {
                "name": "Earlier run",
                "created": created.isoformat(timespec="seconds"),
                "finished": created.isoformat(timespec="seconds"),
                "status": FINISHED,
            },
        )
        params = Path(self.workflow_dir, "params.json")
        if params.exists():
            shutil.copy2(params, self.params_file(run_id))
        return run_id

    # Internals

    def default_name(self) -> str:
        return f"Run {len(self.list_runs()) + 1}"

    def _write(self, run_id: str, run: dict) -> None:
        run = {k: v for k, v in run.items() if k != "id"}
        path = Path(self.run_dir(run_id), RUN_FILE)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(run, f, indent=2)
        tmp.replace(path)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_name(name: Optional[str]) -> str:
    return " ".join(str(name or "").split())


def _is_safe_id(run_id: str) -> bool:
    # Run ids come from session state and query parameters; never let one
    # leave the runs directory.
    return bool(run_id) and "/" not in run_id and "\\" not in run_id and run_id not in (".", "..")


def _check_member(member: zipfile.ZipInfo) -> None:
    """Refuse a ZIP member that could land outside the folder it is unpacked to."""
    name = member.filename
    parts = name.replace("\\", "/").split("/")
    if (
        "\\" in name
        or name.startswith("/")
        or ".." in parts
        or (len(name) > 1 and name[1] == ":")
        or "\x00" in name
    ):
        raise RunImportError(f"Refused: the ZIP has an unsafe path ({name!r}).")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise RunImportError(f"Refused: the ZIP holds a symbolic link ({name!r}).")


def _run_prefix(names: list[str]) -> Optional[str]:
    """
    Where the run sits in the ZIP: "" when results/ is at the top, "<dir>/"
    when everything is in one folder, None when there is no results/ folder.
    """
    if any(n.startswith("results/") for n in names):
        return ""
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1:
        top = tops.pop() + "/"
        if any(n.startswith(f"{top}results/") for n in names):
            return top
    return None


def format_time(iso: Optional[str]) -> str:
    """'2026-10-30T09:12:05' -> '2026-10-30 09:12' (empty for None)."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso
