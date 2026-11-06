"""Content-addressable cache for individual TOPP tool invocations.

A step's cache key ("condition hash") is derived from:
  - the basenames of its input files (never their contents)
  - the condition hash(es) of the immediately preceding step(s) it depends on
  - the effective parameters passed to the tool (merged defaults + user
    overrides + custom params)
  - the tool's reported version and executable identity (SHA-256 of the
    resolved binary)
  - the output file paths and the effective tool parameters

Keys are computed without ever reading input file contents, so large mzML
files never need to be hashed or copied just to decide whether a step can be
skipped. This is a deliberate trade-off: two input files with the same
basename in different folders are treated as identical inputs. See
docs/step-cache.md for the full set of guarantees and limitations.
"""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

PathLike = Union[str, Path]


class StepCache:
    """Per-workflow cache of TOPP tool step results, keyed by condition hash."""

    # Thread allocation is deliberately excluded. The same per-file step can
    # be reused when a batch grows or shrinks and the executor assigns a
    # different number of threads to each command.
    SCHEMA = 4
    INPUT_IDENTITY = "filename"

    def __init__(self, workflow_dir: PathLike):
        self.workflow_dir = Path(workflow_dir)
        self.cache_root = self.workflow_dir / "cache" / "steps"
        self._producers_path = self.workflow_dir / "cache" / "producers.json"
        self.producers: Dict[str, str] = self._load_producers()

    # ------------------------------------------------------------------
    # Dependency chaining: which step produced a given file, by basename.
    # ------------------------------------------------------------------

    def _load_producers(self) -> Dict[str, str]:
        if self._producers_path.exists():
            try:
                producers = json.loads(self._producers_path.read_text(encoding="utf-8"))
                return producers if isinstance(producers, dict) else {}
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_producers(self) -> None:
        self._producers_path.parent.mkdir(parents=True, exist_ok=True)
        self._producers_path.write_text(
            json.dumps(self.producers, indent=2), encoding="utf-8"
        )

    def register_producer(self, output_path: PathLike, condition_hash: str) -> None:
        """Record that the step with this condition hash produced ``output_path``.

        Looked up later (by basename) when a downstream step wants to chain
        its key to the step that produced one of its inputs.
        """
        self.producers[Path(output_path).name] = condition_hash
        self._save_producers()

    def upstream_key_for(self, input_path: PathLike) -> Optional[str]:
        """Return the condition hash of the step that produced this input file,
        loaded from disk or registered in this process, else None."""
        return self.producers.get(Path(input_path).name)

    # ------------------------------------------------------------------
    # Executable identity
    # ------------------------------------------------------------------

    @staticmethod
    def _executable_identity(tool: str) -> Dict[str, str]:
        """Resolve a tool/executable's version string and content hash.

        Works uniformly for OpenMS TOPP tools and external binaries invoked
        through adapters (Comet, Percolator, ...): both are just an
        executable on PATH whose version output and binary content we can
        hash, so a rebuilt or replaced binary invalidates any cached step
        that used it, even if the reported version string didn't change.
        """
        resolved = shutil.which(tool) or tool
        version = ""
        try:
            result = subprocess.run(
                [tool, "--help"], capture_output=True, text=True, timeout=30
            )
            output = (result.stdout or "") + (result.stderr or "")
            for line in output.splitlines():
                if "Version" in line:
                    version = line.split("Version:")[-1].strip().split("-")[0].strip()
                    break
        except (OSError, subprocess.SubprocessError):
            pass

        digest = ""
        try:
            with open(resolved, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            pass

        return {
            "tool": tool,
            "resolved_path": str(resolved),
            "version": version,
            "sha256": digest,
        }

    # ------------------------------------------------------------------
    # Condition hash construction
    # ------------------------------------------------------------------

    def condition_hash(
        self,
        tool: str,
        input_paths: Iterable[PathLike],
        output_paths: Iterable[PathLike],
        effective_params: Dict[str, Any],
        threads: int,
        upstream_keys: Optional[Iterable[str]] = None,
        executable: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Compute a step's condition hash.

        Returns (digest, condition) where ``condition`` is the exact dict
        that was hashed, stored verbatim in the manifest for inspection and
        debugging. ``threads`` remains in the API for compatibility, but is
        intentionally not part of the condition because it only controls
        scheduling.
        """
        input_names = [Path(p).name for p in input_paths]
        output_names = [str(p) for p in output_paths]
        # An instance name is a parameter/cache namespace, not an executable.
        exe_identity = self._executable_identity(executable or tool)

        condition = {
            "schema": self.SCHEMA,
            "input_identity": self.INPUT_IDENTITY,
            "tool": tool,
            "executable": exe_identity,
            "inputs": input_names,
            "outputs": output_names,
            "upstream_keys": sorted(set(upstream_keys or [])),
            "params": effective_params,
        }
        payload = json.dumps(condition, sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return digest, condition

    # ------------------------------------------------------------------
    # Cache directory / manifest helpers
    # ------------------------------------------------------------------

    def _step_dir(self, tool: str, digest: str) -> Path:
        # Tool may be an absolute executable path or an arbitrary instance
        # name. Never let it escape the workflow cache root.
        namespace = hashlib.sha256(tool.encode("utf-8")).hexdigest()
        return self.cache_root / namespace / digest

    def _manifest_path(self, tool: str, digest: str) -> Path:
        return self._step_dir(tool, digest) / "manifest.json"

    @staticmethod
    def _file_checksum(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Hit check / restore
    # ------------------------------------------------------------------

    def try_restore(
        self, tool: str, digest: str, output_paths: List[PathLike]
    ) -> bool:
        """Attempt to restore a cached step's outputs into ``output_paths``.

        Returns True (with outputs copied into place) only if a manifest
        exists for this condition hash AND every declared output is present
        in the cache with a matching checksum. Returns False, with no side
        effects, on any miss, corruption, or missing/mismatched output.
        """
        manifest_path = self._manifest_path(tool, digest)
        if not manifest_path.exists():
            return False
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False

        if not isinstance(manifest, dict) or manifest.get("condition_hash") != digest:
            return False

        entries = manifest.get("outputs", [])
        if not isinstance(entries, list) or len(entries) != len(output_paths):
            return False

        step_dir = self._step_dir(tool, digest)
        for index, entry in enumerate(entries):
            if (not isinstance(entry, dict)
                    or entry.get("cache_name") != str(index)
                    or not isinstance(entry.get("checksum"), str)):
                return False
            cached_file = step_dir / entry["cache_name"]
            if not cached_file.is_file():
                return False
            if self._file_checksum(cached_file) != entry["checksum"]:
                return False

        for entry, dest in zip(entries, output_paths):
            dest_path = Path(dest)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(step_dir / entry["cache_name"], dest_path)

        return True

    # ------------------------------------------------------------------
    # Publish a freshly computed step
    # ------------------------------------------------------------------

    def publish(
        self,
        tool: str,
        digest: str,
        condition: Dict[str, Any],
        output_paths: List[PathLike],
    ) -> bool:
        """Store copies of a successful step's outputs plus a manifest.

        Returns False without writing anything if any declared output is
        missing (the tool claimed success but didn't produce everything it
        was supposed to), so a corrupt/incomplete run is never cached.
        """
        for p in output_paths:
            if not Path(p).is_file():
                return False

        step_dir = self._step_dir(tool, digest)
        step_dir.mkdir(parents=True, exist_ok=True)

        entries = []
        for i, p in enumerate(output_paths):
            cache_name = str(i)
            checksum = self._file_checksum(Path(p))
            shutil.copy2(p, step_dir / cache_name)
            entries.append(
                {
                    "output_path": str(p),
                    "cache_name": cache_name,
                    "checksum": checksum,
                }
            )

        manifest = {
            "condition_hash": digest,
            "condition": condition,
            "outputs": entries,
        }
        self._manifest_path(tool, digest).write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )
        return True
