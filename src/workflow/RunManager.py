"""
Keeps every run of a workflow as its own named result set.

A workflow that sets ``multi_run = True`` writes each run into
``<workflow_dir>/runs/<run_id>/`` instead of overwriting
``<workflow_dir>/results/``:

    runs/<run_id>/run.json      name, status and timestamps
    runs/<run_id>/params.json   the parameters the run was started with
    runs/<run_id>/results/      everything execution() wrote
    runs/<run_id>/logs/         the run's logs, copied when it ends

A run started to process more files for an earlier run's experiment
(``restore_settings(..., add_files=...)``) records that run as ``adds_to`` in
its run.json: the experiment is the earlier run with every finished run that
adds to it (``experiment``), and the results pages show it as one, computing
over the files of all of them.

This module must stay importable without Streamlit: the RQ worker
(``tasks.py``) uses it to mark a queued run finished or failed.
"""

import json
import re
import shutil
import stat
import uuid
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import Optional

RUN_FILE = "run.json"
DESIGN_FILE = "experimental-design.tsv"
# params.json key naming the run whose settings the next run starts from
FOLLOW_UP_KEY = "_follow_up"
# Without run folders: what the last start followed (WorkflowManager.start_from)
FOLLOW_UP_FILE = "last-follow-up.json"
# run.json key: the run whose experiment this run adds files to
ADDS_TO = "adds_to"
MAX_NAME_LENGTH = 100
# Largest unpacked size import_zip() accepts by default
MAX_IMPORT_BYTES = 20 * 1024**3
# Most files a run ZIP may add, and the largest run.json / params.json read
MAX_IMPORT_MEMBERS = 100_000
MAX_RUN_FILE_BYTES = 1024**2
MAX_PARAMS_FILE_BYTES = 64 * 1024**2


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

    # Experiments: a run and the runs that add files to it

    def experiment_root(self, run_id: Optional[str]) -> Optional[str]:
        """The run whose experiment ``run_id`` belongs to (itself, unless it adds files)."""
        run = self.get(run_id)
        if run is None:
            return None
        seen = {run_id}
        # Follows a chain, which a delete leaves while it re-points the runs
        while run.get(ADDS_TO) and run[ADDS_TO] not in seen:
            parent = self.get(run[ADDS_TO])
            if parent is None:
                break
            seen.add(run[ADDS_TO])
            run_id, run = run[ADDS_TO], parent
        return run_id

    def added_runs(self, run_id: str, status: Optional[str] = FINISHED) -> list[dict]:
        """The runs that add files to ``run_id``'s experiment, oldest first."""
        root = self.experiment_root(run_id)
        if root is None:
            return []
        added = [r for r in self.list_runs(status)
                 if r.get(ADDS_TO) and r["id"] != root and self.experiment_root(r["id"]) == root]
        return sorted(added, key=lambda r: (r.get("created", ""), r["id"]))

    def experiment(self, run_id: Optional[str]) -> list[str]:
        """The runs of ``run_id``'s experiment, oldest first: the run that
        started it, then every finished run that added files to it. Empty if
        there is no such run."""
        root = self.experiment_root(run_id)
        if root is None:
            return []
        return [root] + [r["id"] for r in self.added_runs(root)]

    def experiments(self, status: Optional[str] = FINISHED) -> list[dict]:
        """The runs that start an experiment (in ``status``), newest first; a run
        that adds files is listed under its experiment's first run instead."""
        return [r for r in self.list_runs(status) if self.experiment_root(r["id"]) == r["id"]]

    def new_run(self, name: str = "", params_file: Optional[Path] = None,
                adds_to: Optional[str] = None) -> str:
        """
        Create the directory for a new run and return its id.

        Args:
            name: Display name. Defaults to "Run <n>".
            params_file: The workflow's params.json, copied into the run so the
                results can be read with the parameters that produced them.
            adds_to: A run whose experiment this run adds files to.
        """
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_id, n = base, 1
        while self.run_dir(run_id).exists():
            n += 1
            run_id = f"{base}-{n}"
        self.results_dir(run_id).mkdir(parents=True)
        name = _clean_name(name) or self.default_name()
        run = {"name": name, "created": _now(), "status": RUNNING}
        root = self.experiment_root(adds_to) if adds_to else None
        if root:
            run[ADDS_TO] = root
        self._write(run_id, run)
        if params_file is not None and Path(params_file).exists():
            shutil.copy2(params_file, self.params_file(run_id))
        # The experimental design is part of the run's settings too
        design = Path(self.workflow_dir, DESIGN_FILE)
        if design.exists():
            shutil.copy2(design, Path(self.run_dir(run_id), DESIGN_FILE))
        return run_id

    def restore_settings(self, run_id: str, changes: Optional[dict] = None,
                         note: str = "", add_files: Optional[str] = None,
                         same_files: Optional[str] = None, keep: Optional[list] = None) -> bool:
        """Make a run's parameters (and experimental design) the workflow's again.

        The next run then starts from exactly the settings ``run_id`` used,
        with ``changes`` on top (top-level keys of params.json; a dict value,
        such as one TOPP tool's parameters, is merged into the stored one).
        ``FOLLOW_UP_KEY`` records which run it follows, for the configure page
        and the processing report. False if the run recorded no parameters.

        ``add_files`` (the params.json key of the input files, e.g.
        ``"mzML-files"``) starts a run that adds files to ``run_id``'s
        experiment: that key starts empty, so only the files picked now are
        processed, and the next run is recorded as adding to the experiment.

        ``same_files`` (that key) is for an analysis added to ``run_id`` itself:
        the next run takes exactly its files, which the configure page shows
        locked, and ``keep`` names the tools (instance names) whose results it
        reuses, whose settings stay as they were (``follow_up_info()["reuses"]``
        names the run, for ``execution()``).
        """
        run = self.get(run_id)
        params = self.params(run_id)
        if run is None or not isinstance(params, dict) or not params:
            return False
        info = {"run": run_id, "name": run.get("name", run_id), "note": note}
        if add_files:
            root = self.experiment_root(run_id)
            root_run = self.get(root) or run
            info.update(run=root, name=root_run.get("name", root), adds_to=root,
                        files_key=add_files, files=self.experiment_files(root, add_files))
            changes = {**(changes or {}), add_files: []}
        elif same_files:
            value = params.get(same_files) or []
            files = [value] if isinstance(value, str) else list(value)
            info.update(same_files_info(same_files, files, keep, [run_id]))
            changes = {**(changes or {}), same_files: files}
        apply_settings(self.workflow_dir, params, changes, info)
        design = Path(self.run_dir(run_id), DESIGN_FILE)
        if design.exists():
            shutil.copy2(design, Path(self.workflow_dir, DESIGN_FILE))
        return True

    def experiment_files(self, run_id: str, key: str) -> list[str]:
        """The input files (params.json ``key``) of every run of ``run_id``'s experiment."""
        files = []
        for member in self.experiment(run_id):
            value = self.params(member).get(key) or []
            files += [value] if isinstance(value, str) else list(value)
        return list(dict.fromkeys(files))

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
        """Delete a run and all its files.

        The runs that added files to its experiment then form one of their own,
        started by the oldest finished one of them (else the oldest).
        """
        if self.get(run_id) is None:
            return False
        if self.experiment_root(run_id) == run_id:
            added = self.added_runs(run_id, status=None)
            if added:
                # The others point at the oldest finished one (else the oldest),
                # and it becomes the root last: a write that fails leaves one
                # experiment to delete again
                first = next((r for r in added if r.get("status") == FINISHED), added[0])
                for other in added:
                    if other is first:
                        continue
                    other[ADDS_TO] = first["id"]
                    self._write(other["id"], {k: v for k, v in other.items() if k != "id"})
                first.pop(ADDS_TO, None)
                self._write(first["id"], {k: v for k, v in first.items() if k != "id"})
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
            self._write_report(zf, run_id)
        return zip_path

    def _write_report(self, zf: zipfile.ZipFile, run_id: str) -> None:
        """Add the run's processing report (Markdown) to its ZIP, if it recorded tool calls."""
        from .processing_report import REPORT_NAME, report_for, to_markdown

        try:
            report = report_for(self.workflow_dir, run_id)
            text = to_markdown(report) if report["steps"] else ""
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return  # a damaged progress.json: the ZIP goes without the report
        if text:
            zf.writestr(f"{REPORT_NAME}.md", text)

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
        as are names Windows reserves (``NUL``, ``CON``, ...), a ZIP that
        unpacks to more than ``max_bytes`` or holds more than
        MAX_IMPORT_MEMBERS files, and an oversized run.json or params.json.
        A run that was still running when it was zipped is imported as failed. Unpacking goes to a
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
        try:
            with archive:
                return self._import_archive(archive, name, max_bytes)
        except (zipfile.BadZipFile, zlib.error, EOFError) as e:
            raise RunImportError(f"The ZIP is damaged ({e}).") from e
        except RuntimeError as e:
            # Encrypted members, an unsupported compression method, or JSON
            # nested too deeply to parse
            raise RunImportError(f"The ZIP can not be read ({e}).") from e
        except OSError as e:
            raise RunImportError(f"The ZIP could not be unpacked ({e}).") from e

    def _import_archive(self, archive: zipfile.ZipFile, name: str, max_bytes: int) -> str:
        members = [m for m in archive.infolist() if not m.is_dir()]
        for m in archive.infolist():
            _check_member(m)
        if len(members) > MAX_IMPORT_MEMBERS:
            raise RunImportError(
                f"The ZIP holds {len(members)} files, more than the "
                f"{MAX_IMPORT_MEMBERS} allowed."
            )
        total = sum(m.file_size for m in members)
        if total > max_bytes:
            raise RunImportError(
                f"The ZIP unpacks to {total / 1024**3:.1f} GB, more than "
                f"the {max_bytes / 1024**3:.1f} GB allowed."
            )
        prefix = _run_prefix([m.filename for m in members])
        if prefix is None:
            raise RunImportError(
                "This ZIP holds no run: a run's ZIP has a results/ "
                "folder or a run.json."
            )

        for m in members:
            limit = {
                f"{prefix}{RUN_FILE}": MAX_RUN_FILE_BYTES,
                f"{prefix}params.json": MAX_PARAMS_FILE_BYTES,
            }.get(m.filename)
            if limit is not None and m.file_size > limit:
                raise RunImportError(
                    f"Refused: {m.filename} is larger than "
                    f"{limit / 1024**2:.0f} MB."
                )

        meta = {}
        if f"{prefix}{RUN_FILE}" in archive.namelist():
            try:
                meta = json.loads(archive.read(f"{prefix}{RUN_FILE}"))
            except ValueError:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        status = meta.get("status")
        if status == RUNNING:
            # Zipped while it ran, or after its process died: its results
            # may be incomplete.
            status = FAILED
        elif status not in (FINISHED, FAILED, CANCELLED):
            status = FINISHED

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
                "created": _iso_time(meta.get("created")) or _now(),
                "status": status,
                "imported": _now(),
            }
            if _iso_time(meta.get("finished")):
                run["finished"] = _iso_time(meta["finished"])
            run["name"] = self._unique_name(run["name"])

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
        """``name``, or ``name (n)`` if a run has it, within MAX_NAME_LENGTH."""
        taken = {r.get("name") for r in self.list_runs()}
        name = name[:MAX_NAME_LENGTH]
        if name not in taken:
            return name
        n = 2
        while True:
            suffix = f" ({n})"
            candidate = name[: MAX_NAME_LENGTH - len(suffix)].rstrip() + suffix
            if candidate not in taken:
                return candidate
            n += 1

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


def same_files_info(key: str, files: list, keep: Optional[list] = None,
                    reuses: Optional[list] = None) -> dict:
    """What ``FOLLOW_UP_KEY`` records for an analysis added to earlier results:
    the input files (params.json ``key``) stay ``files``, and the tools ``keep``
    are not run again, their results taken from ``reuses`` (run or result ids)."""
    return {"same_files": key, "files": [str(f) for f in files],
            "kept": list(keep or []), "reuses": list(reuses or [])}


def apply_settings(workflow_dir: Path, params: dict, changes: Optional[dict] = None,
                   follow_up: Optional[dict] = None) -> dict:
    """Write ``params`` with ``changes`` on top as the workflow's params.json.

    A dict value of ``changes`` (one TOPP tool's parameters) is merged into the
    stored one. ``follow_up`` (``{"run"?, "name", "note"}``) is kept under
    ``FOLLOW_UP_KEY`` for the configure page and the processing report.
    Returns what was written.
    """
    params = dict(params)
    params.pop(FOLLOW_UP_KEY, None)
    for key, value in (changes or {}).items():
        if isinstance(value, dict) and isinstance(params.get(key), dict):
            params[key] = {**params[key], **value}
        else:
            params[key] = value
    if follow_up:
        params[FOLLOW_UP_KEY] = dict(follow_up)
    target = Path(workflow_dir, "params.json")
    tmp = target.with_name(f".params-{uuid.uuid4().hex}.json")
    tmp.write_text(json.dumps(params, indent=4), encoding="utf-8")
    tmp.replace(target)
    return params


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_name(name: Optional[str]) -> str:
    return " ".join(str(name or "").split())


def _is_safe_id(run_id: str) -> bool:
    # Run ids come from session state and query parameters; never let one
    # leave the runs directory.
    return bool(run_id) and "/" not in run_id and "\\" not in run_id and run_id not in (".", "..")


def _iso_time(value) -> Optional[str]:
    """``value`` if it is an ISO timestamp string, else None."""
    if not isinstance(value, str):
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


# Names Windows maps to devices, with or without an extension (NUL, nul.txt)
_WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)


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
        or any(_WINDOWS_RESERVED.match(p.rstrip(" .")) for p in parts if p)
    ):
        raise RunImportError(f"Refused: the ZIP has an unsafe path ({name!r}).")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise RunImportError(f"Refused: the ZIP holds a symbolic link ({name!r}).")


def _run_prefix(names: list[str]) -> Optional[str]:
    """
    Where the run sits in the ZIP: "" when results/ is at the top, "<dir>/"
    when everything is in one folder, None when it holds no run. A run is
    a results/ folder or a run.json: zip() leaves out an empty results/.
    """
    def is_run(prefix: str) -> bool:
        return any(
            n.startswith(f"{prefix}results/") or n == f"{prefix}{RUN_FILE}"
            for n in names
        )

    if is_run(""):
        return ""
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1:
        top = tops.pop() + "/"
        if is_run(top):
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
