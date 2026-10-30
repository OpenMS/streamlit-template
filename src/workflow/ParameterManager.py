import pyopenms as poms
import errno
import json
import logging
import os
import shutil
import subprocess
import streamlit as st
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)


def bool_param_paths_from_param_xml_ini(ini_path: Path, tool_stem: str) -> set[str]:
    """
    Return short parameter paths for every ``<ITEM type="bool">`` in a ParamXML .ini file.

    Paths match the suffix after ``Tool:1:`` in pyOpenMS (e.g. ``algorithm:epd:masstrace_snr_filtering``).
    """
    try:
        root = ET.parse(ini_path).getroot()
    except (ET.ParseError, OSError):
        return set()

    def local_tag(el: ET.Element) -> str:
        t = el.tag
        return t.rsplit("}", 1)[-1] if isinstance(t, str) and "}" in t else str(t)

    out: set[str] = set()

    def walk(el: ET.Element, parts: tuple[str, ...]) -> None:
        for ch in el:
            lt = local_tag(ch)
            if lt == "NODE":
                nm = ch.get("name") or ""
                walk(ch, parts + (nm,))
            elif lt == "ITEM" and (ch.get("type") or "").lower() == "bool":
                nm = ch.get("name") or ""
                segs = [p for p in parts if p]
                if nm:
                    segs.append(nm)
                if not segs:
                    continue
                # Strip tool root NODE name and instance NODE "1" (not part of pyOpenMS short keys)
                while segs and segs[0] in (tool_stem, "1"):
                    segs.pop(0)
                if segs:
                    out.add(":".join(segs))

    for ch in root:
        if local_tag(ch) == "NODE":
            walk(ch, ())
    return out


class InvalidParameterFileError(ValueError):
    """
    Raised when a params.json exists but cannot be read as a parameter dict.

    Deliberately distinct from an absent file, which simply means a first run
    with no stored parameters. Conflating the two is the erasure bug: a failed
    read reported as an empty dict gets merged into a read-modify-write and
    written back as the current session's subset, permanently deleting
    ``_defaults``, ``_flag_params`` and every other tool's values.
    """


class TransientParameterFileError(InvalidParameterFileError):
    """
    Raised when the read failed for a reason expected to clear by itself.

    A shared NFS export is restarted by upgrades, evictions and node drains,
    and clients see ESTALE/EIO until it is back. The stored bytes are almost
    certainly intact, so callers must still refuse to write - the current
    content is unknown - but must not offer to delete the file. Resetting
    during a self-healing blip is what would turn a momentary outage into the
    permanent data loss this split exists to prevent.

    A subclass, so every ``except InvalidParameterFileError`` guard keeps
    catching it; only code that treats the two differently has to know.
    """


# errno values meaning "the storage is not answering right now", as opposed to
# "this file is broken". Looked up defensively: not all exist on every platform.
_TRANSIENT_READ_ERRNOS = frozenset(
    value
    for value in (
        getattr(errno, name, None)
        for name in (
            "ESTALE",
            "EIO",
            "ENOTCONN",
            "ETIMEDOUT",
            "EAGAIN",
            "EINTR",
            "ENOLINK",
            "EREMOTEIO",
        )
    )
    if value is not None
)

# Two retries, at 0.2s and 0.4s. Long enough to ride out a re-established NFS
# connection, short enough that a Streamlit rerun does not visibly stall. Only
# transient errnos retry, so a corrupt file still fails on the first attempt.
_READ_ATTEMPTS = 3
_READ_RETRY_DELAY_SECONDS = 0.2


def _read_parameter_file(params_file: Path) -> dict:
    """
    Read a parameter JSON file. Pure I/O, no Streamlit and no session state.

    Args:
        params_file: Path of the JSON file to read.

    Returns:
        dict: The stored parameters, or an empty dict if the file does not
            exist at all - a first run has no parameters and that is not a
            failure.

    Raises:
        TransientParameterFileError: The storage did not answer (ESTALE, EIO,
            ...), and still did not after retrying. The file is probably fine.
        InvalidParameterFileError: The file exists but could not be read as a
            JSON object: malformed or torn content, a bad encoding, a directory
            in its place, permissions. Callers which merge the result and write
            it back must abort on this rather than treat it as "no parameters".
    """
    last_error = None
    for attempt in range(_READ_ATTEMPTS):
        try:
            with open(params_file, "r", encoding="utf-8") as f:
                params = json.load(f)
            break
        except FileNotFoundError:
            # Ordered before OSError on purpose: an absent file is a first run,
            # not a failure, and conflating the two is the erasure bug.
            return {}
        except OSError as e:
            if e.errno not in _TRANSIENT_READ_ERRNOS:
                raise InvalidParameterFileError(
                    f"Could not read parameter file {params_file}: {e}"
                ) from e
            last_error = e
            if attempt + 1 < _READ_ATTEMPTS:
                time.sleep(_READ_RETRY_DELAY_SECONDS * (attempt + 1))
        except ValueError as e:
            # json.JSONDecodeError *and* UnicodeDecodeError - the latter is a
            # ValueError, not an OSError, so catching OSError alone let a
            # params.json written in the platform codepage escape both readers
            # uncaught and take the workflow page down with a raw traceback.
            raise InvalidParameterFileError(
                f"Could not read parameter file {params_file}: {e}"
            ) from e
    else:
        raise TransientParameterFileError(
            f"Could not read parameter file {params_file} after "
            f"{_READ_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    if not isinstance(params, dict):
        raise InvalidParameterFileError(
            f"Parameter file {params_file} does not hold a JSON object "
            f"(found {type(params).__name__})."
        )
    return params


def _write_parameter_file(params_file: Path, params: dict) -> None:
    """
    Write a parameter JSON file atomically: temp file, then ``os.replace()``.

    A truncate-then-rewrite that dies half way - an OOM kill, ENOSPC - leaves a
    file which is neither the old parameters nor the new ones. Every later
    strict read rejects it, so ``save_parameters()`` becomes a permanent silent
    no-op and the parameter page stops on every render, with no way out but the
    reset button. ``os.replace()`` is atomic on POSIX and on Windows, so a
    reader sees either the whole old file or the whole new one.

    This does not make concurrent writers safe - the last writer still wins the
    whole file, docs/storage-defect-register.md A2 - it only removes the torn file.

    The scratch name carries a uuid as well as the pid. The pid alone is not
    unique per writer: Streamlit serves every session from threads of ONE
    process, and in a container that process is pid 1 in every replica - so two
    sessions sharing a `?workspace=` link, or two pods now that the volume is
    genuinely ReadWriteMany, resolved to the same scratch path and interleaved
    their writes into it. Whichever one reached os.replace() second published a
    file the other was still writing, which is precisely the torn file this
    function exists to prevent.

    flush + fsync before the rename because os.replace() orders the directory
    entry, not the data behind it: on NFS a crash between the two can otherwise
    publish a name pointing at unwritten blocks.

    Deliberately not tempfile.mkstemp(): it creates at mode 0600, so params.json
    would quietly change permissions the first time it was rewritten.

    Args:
        params_file: Destination path.
        params: Parameters to store.
    """
    tmp_file = params_file.with_name(
        f".{params_file.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, params_file)
    except BaseException:
        # Never leave the scratch file behind next to params.json.
        try:
            tmp_file.unlink()
        except OSError:
            pass
        raise


def _streamlit_session_active() -> bool:
    """
    True only while running inside a real Streamlit script run.

    tasks.py builds a ParameterManager inside the RQ work horse, where there is
    no ScriptRunContext and st.error() is a silent no-op - so the user facing
    half of a message is skipped there and the log carries it instead.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        # suppress_warning, or every probe from the worker logs a "missing
        # ScriptRunContext!" warning next to the message it is deciding about.
        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:  # streamlit absent, mocked out, or internals moved
        return False


class ParameterManager:
    """
    Manages the parameters for a workflow, including saving parameters to a JSON file,
    loading parameters from the file, and resetting parameters to defaults. This class
    specifically handles parameters related to TOPP tools in a pyOpenMS context and
    general parameters stored in Streamlit's session state.

    Attributes:
        ini_dir (Path): Directory path where .ini files for TOPP tools are stored.
        params_file (Path): Path to the JSON file where parameters are saved.
        param_prefix (str): Prefix for general parameter keys in Streamlit's session state.
        topp_param_prefix (str): Prefix for TOPP tool parameter keys in Streamlit's session state.
        workflow_name (str): Name of the workflow, used for loading presets.
    """
    # Methods related to parameter handling
    def __init__(self, workflow_dir: Path, workflow_name: str = None):
        self.ini_dir = Path(workflow_dir, "ini")
        self.ini_dir.mkdir(parents=True, exist_ok=True)
        self.params_file = Path(workflow_dir, "params.json")
        self.param_prefix = f"{workflow_dir.stem}-param-"
        self.topp_param_prefix = f"{workflow_dir.stem}-TOPP-"
        # Store workflow name for preset loading; default to directory stem if not provided
        self.workflow_name = workflow_name or workflow_dir.stem
        # Presets the user saved in this workflow, and which preset was applied last
        self.user_presets_file = Path(workflow_dir, "user-presets.json")

    def bool_pairs_session_key(self) -> str:
        """Session state key holding a set of (tool name, param path) for bool TOPP params."""
        return f"{self.ini_dir.parent.stem}-topp-bool-pairs"

    def get_bool_param_pairs(self) -> set:
        """Return the cached set of (tool, param path) bool params; empty set if none."""
        return st.session_state.get(self.bool_pairs_session_key(), set())

    def _merge_bool_params_from_ini(self, tool: str) -> None:
        """Load tool.ini (XML) and merge type=bool parameter paths into session_state."""
        ini_path = Path(self.ini_dir, f"{tool}.ini")
        if not ini_path.exists():
            return
        try:
            sk = self.bool_pairs_session_key()
            if sk not in st.session_state:
                st.session_state[sk] = set()
            for short in bool_param_paths_from_param_xml_ini(ini_path, tool):
                st.session_state[sk].add((tool, short))
        except RuntimeError:
            # No Streamlit session (e.g. plain `python` import)
            pass

    def create_ini(self, tool: str) -> bool:
        """
        Create an ini file for a TOPP tool if it doesn't exist.

        Args:
            tool: Name of the TOPP tool (e.g., "CometAdapter")

        Returns:
            True if ini file exists (created or already existed), False if creation failed
        """
        ini_path = Path(self.ini_dir, tool + ".ini")
        if ini_path.exists():
            self._merge_bool_params_from_ini(tool)
            return True
        try:
            subprocess.call([tool, "-write_ini", str(ini_path)])
        except FileNotFoundError:
            return False
        if ini_path.exists():
            self._merge_bool_params_from_ini(tool)
        return ini_path.exists()

    def save_parameters(self) -> None:
        """
        Saves the current parameters from Streamlit's session state to a JSON file.
        It handles both general parameters and parameters specific to TOPP tools,
        ensuring that only non-default values are stored.
        """
        # Everything in session state which begins with self.param_prefix is saved to a json file
        json_params = {
            k.replace(self.param_prefix, ""): v
            for k, v in st.session_state.items()
            if k.startswith(self.param_prefix)
        }

        # Merge with parameters from json
        # Advanced parameters are only in session state if the view is active.
        # The read has to be strict: merging a tolerant empty dict from a failed
        # read and writing that back is what erases every stored value, so a
        # failed read aborts the write and leaves the file on disk untouched.
        try:
            stored_params = self.read_parameters_strict()
        except InvalidParameterFileError as e:
            self._report_unreadable_parameter_file(
                e, "Parameters were not saved, the existing file is left unchanged."
            )
            return
        json_params = stored_params | json_params

        # get a list of TOPP tools (or tool instance names) which are in session state
        current_topp_tools = list(
            set(
                [
                    k.replace(self.topp_param_prefix, "").split(":1:")[0]
                    for k in st.session_state.keys()
                    if k.startswith(f"{self.topp_param_prefix}")
                ]
            )
        )
        # Retrieve the instance-name → real-tool-name mapping (set by input_TOPP)
        tool_instance_map = st.session_state.get("_topp_tool_instance_map", {})
        # for each TOPP tool (or instance name), open the ini file
        for tool in current_topp_tools:
            # Resolve instance name to real tool name for create_ini / ini loading
            real_tool = tool_instance_map.get(tool, tool)
            if not self.create_ini(real_tool):
                # Could not create ini file - skip this tool
                continue
            ini_path = Path(self.ini_dir, f"{real_tool}.ini")
            if tool not in json_params:
                json_params[tool] = {}
            # load the param object
            param = poms.Param()
            poms.ParamXMLFile().load(str(ini_path), param)
            # get all session state param keys and values for this tool
            for key, value in st.session_state.items():
                if key.startswith(f"{self.topp_param_prefix}{tool}:1:"):
                    # Skip display keys used by multiselect widgets
                    if key.endswith("_display"):
                        continue
                    # get ini_key – map instance name back to real tool name
                    ini_key = key.replace(self.topp_param_prefix, "")
                    if tool != real_tool:
                        ini_key = ini_key.replace(f"{tool}:1:", f"{real_tool}:1:", 1)
                    ini_key = ini_key.encode()
                    # get ini (default) value by ini_key
                    ini_value = param.getValue(ini_key)
                    is_list_param = isinstance(ini_value, list)
                    # Effective default: _defaults value if present, else ini value
                    short_key = key.split(":1:")[1]
                    defaults = json_params.get("_defaults", {}).get(tool, {})
                    default_value = defaults.get(short_key, ini_value)
                    # check if value is different from effective default OR is an empty list parameter
                    if (
                        (default_value != value)
                        or (short_key in json_params[tool])
                        or (is_list_param and not value)  # Always save empty list params
                    ):
                        # store non-default value
                        json_params[tool][short_key] = value
        # Save to json file
        _write_parameter_file(self.params_file, json_params)

    def get_parameters_from_json(self) -> dict:
        """
        Loads parameters from the JSON file if it exists and returns them as a dictionary.
        If the file does not exist or cannot be read, it returns an empty dictionary.

        Tolerant on purpose, for the constructors and the read-only callers which
        have no way to handle a raise. Never use it as the read half of a
        read-modify-write: an empty dict from a failed read, merged over the
        stored parameters and written back, erases them. Use
        read_parameters_strict() there.

        Returns:
            dict: A dictionary containing the loaded parameters. Keys are parameter names,
                and values are parameter values.
        """
        try:
            return _read_parameter_file(self.params_file)
        except InvalidParameterFileError as e:
            self._report_unreadable_parameter_file(
                e, "Falling back to default parameters."
            )
            return {}

    def read_parameters_strict(self) -> dict:
        """
        Loads parameters from the JSON file, raising instead of hiding a failed read.

        This is the reader for every read-modify-write-back site.
        get_parameters_from_json() cannot be used there: its empty dict for an
        unreadable file gets merged with the current session's parameters and
        written back, permanently erasing everything the session does not hold -
        while the user is told it was a deliberate reset to defaults.

        Returns:
            dict: The stored parameters. Empty only if params.json does not exist.

        Raises:
            InvalidParameterFileError: params.json exists but is unreadable.
        """
        return _read_parameter_file(self.params_file)

    def write_parameters(self, params: dict) -> None:
        """
        Write params.json, atomically, for the write-back sites outside this class.

        StreamlitUI._input_TOPP_impl() seeds ``_flag_params`` and ``_defaults``
        by reading with read_parameters_strict(), merging, and writing straight
        back, so it needs the same atomic write save_parameters() uses - a torn
        file written there wedges the parameter page on every later render.

        Args:
            params: The complete parameter dict to store.
        """
        _write_parameter_file(self.params_file, params)

    def _report_unreadable_parameter_file(self, error: Exception, consequence: str) -> None:
        """
        Report an unreadable params.json, to the log always and to the user if there is one.

        logging is the sink which always works: tasks.py builds a
        ParameterManager inside the RQ work horse, where st.error() reaches
        nobody.

        Args:
            error: The read failure being reported.
            consequence: What the caller did about it, in the user's terms.
        """
        message = f"{error} {consequence}"
        logger.error(message)
        if _streamlit_session_active():
            st.error(f"**ERROR**: {message}")

    def get_merged_params(self, tool_instance_name: str, ini_params: dict = None) -> dict:
        """
        Three-layer parameter merge: ini defaults < _defaults < user overrides.

        Args:
            tool_instance_name: Instance name (or tool name) to look up in params.json.
            ini_params: Base parameters from the .ini file. Optional — callers that
                don't need the ini layer (e.g., run_topp, which passes -ini separately)
                can omit this.

        Returns:
            Merged dict with the effective value for each parameter.
        """
        params = self.get_parameters_from_json()
        defaults = params.get("_defaults", {}).get(tool_instance_name, {})
        user = params.get(tool_instance_name, {})

        merged = {}
        if ini_params:
            merged.update(ini_params)
        merged.update(defaults)
        merged.update(user)
        return merged

    def get_topp_parameters(self, tool: str, tool_instance_name: str = None) -> dict:
        """
        Get all parameters for a TOPP tool, merging defaults with user values.

        Args:
            tool: Name of the TOPP tool executable (e.g., "CometAdapter")
            tool_instance_name: Optional instance name used for parameter storage
                (e.g., "IDFilter_step1"). If not provided, defaults to tool name.

        Returns:
            Dict with parameter names as keys (without tool prefix) and their values.
            Returns empty dict if ini file doesn't exist.
        """
        instance_name = tool_instance_name or tool
        ini_path = Path(self.ini_dir, f"{tool}.ini")
        if not ini_path.exists():
            return {}

        # Load defaults from ini file
        param = poms.Param()
        poms.ParamXMLFile().load(str(ini_path), param)

        # Build dict from ini (extract short key names)
        prefix = f"{tool}:1:"
        ini_params = {}
        for key in param.keys():
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            if prefix in key_str:
                short_key = key_str.split(prefix, 1)[1]
                ini_params[short_key] = param.getValue(key)

        return self.get_merged_params(instance_name, ini_params=ini_params)

    def reset_to_default_parameters(self) -> Path | None:
        """
        Reset to defaults by moving the stored parameter file out of the way.

        Moved, not deleted. This is also the recovery offered when params.json
        cannot be read, and an unreadable file is very often a healthy file
        behind a storage blip, so deleting it there would turn a self-healing
        outage into permanent loss. The bytes are kept under a timestamped name
        beside the original and the caller is told where they went. A rename
        also copes with a directory in place of params.json, which
        ``unlink()`` cannot - that used to make the reset button itself raise,
        leaving the parameter page stopped on every render with no way out.

        Returns:
            Path: Where the previous parameters were moved, or None when there
                was nothing to reset.

        Raises:
            OSError: The file exists but could not be moved. Callers rendering
                a reset affordance must surface this rather than let it escape.
        """
        if not self.params_file.exists():
            return None

        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = self.params_file.with_name(f"{self.params_file.name}.{stamp}.bak")
        collision = 1
        while backup.exists():
            backup = self.params_file.with_name(
                f"{self.params_file.name}.{stamp}-{collision}.bak"
            )
            collision += 1

        self.params_file.rename(backup)
        logger.info("Reset parameters, previous file kept at %s", backup)
        return backup

    def load_presets(self) -> dict:
        """
        Load preset definitions from presets.json file.

        Returns:
            dict: Dictionary of presets for the current workflow, or empty dict if
                  presets.json doesn't exist or has no presets for this workflow.
        """
        presets_file = Path("presets.json")
        if not presets_file.exists():
            return {}

        try:
            with open(presets_file, "r", encoding="utf-8") as f:
                all_presets = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

        # Normalize workflow name to match preset keys (lowercase with hyphens)
        workflow_key = self.workflow_name.replace(" ", "-").lower()
        return all_presets.get(workflow_key, {})

    def get_preset_names(self) -> list:
        """
        Get list of available preset names for the current workflow.

        Returns:
            list: List of preset names (strings), excluding special keys like _description.
        """
        presets = self.load_presets()
        return [name for name in presets.keys() if not name.startswith("_")]

    def get_preset_description(self, preset_name: str) -> str:
        """
        Get the description for a specific preset.

        Args:
            preset_name: Name of the preset

        Returns:
            str: Description text for the preset, or empty string if not found.
        """
        presets = self.load_presets()
        preset = presets.get(preset_name) or self.load_user_presets().get(preset_name, {})
        return preset.get("_description", "")

    def _read_user_preset_state(self, strict: bool = False) -> dict:
        """
        The user-presets file: ``{"presets": {name: preset}, "applied": name}``.

        Entries that are not a named dict are dropped, and ``applied`` is a name
        or None, so callers can use the result without further checks.

        Args:
            strict: Raise instead of returning an empty state when the file
                exists but cannot be read. Every read-modify-write uses it, so a
                failed read never writes an empty state over the saved presets.

        Raises:
            InvalidParameterFileError: Only with ``strict``, as above.
        """
        empty = {"presets": {}, "applied": None}
        try:
            state = _read_parameter_file(self.user_presets_file)
        except InvalidParameterFileError:
            if strict:
                raise
            logger.exception("Could not read %s", self.user_presets_file)
            return empty
        presets = state.get("presets", {})
        if not isinstance(presets, dict):
            if strict:
                raise InvalidParameterFileError(
                    f"{self.user_presets_file} has no valid 'presets' object."
                )
            return empty
        valid = {}
        for name, preset in presets.items():
            if isinstance(name, str) and isinstance(preset, dict):
                if not isinstance(preset.get("_general", {}), dict):
                    preset = {k: v for k, v in preset.items() if k != "_general"}
                valid[name] = preset
        applied = state.get("applied")
        return {"presets": valid, "applied": applied if isinstance(applied, str) else None}

    def _read_user_preset_state_for_write(self, consequence: str) -> dict | None:
        """Strict read before a write-back; reports a failure and returns None."""
        try:
            return self._read_user_preset_state(strict=True)
        except InvalidParameterFileError as e:
            self._report_unreadable_parameter_file(e, consequence)
            return None

    def _write_user_preset_state(self, state: dict) -> None:
        _write_parameter_file(self.user_presets_file, state)

    def load_user_presets(self) -> dict:
        """Presets the user saved in this workflow, in the presets.json format."""
        return self._read_user_preset_state()["presets"]

    def get_user_preset_names(self) -> list:
        """Names of the presets the user saved, in the order they were saved."""
        return list(self.load_user_presets().keys())

    def _input_file_keys(self) -> set:
        """Parameter keys holding input file selections (one per input-files/<key> directory)."""
        input_dir = Path(self.params_file.parent, "input-files")
        if not input_dir.is_dir():
            return set()
        return {p.name for p in input_dir.iterdir() if p.is_dir()}

    def snapshot_preset(self) -> dict:
        """
        The current parameters as a preset: every TOPP tool's stored values and the
        custom parameters under ``_general``.

        Input file selections, ``max_threads`` and the reserved ``_``-keys are left
        out, so applying the preset later changes settings, not which files run or
        how many threads this machine uses.
        """
        params = self.get_parameters_from_json()
        skip = self._input_file_keys() | {"max_threads"}
        preset = {"_general": {}}
        for key, value in params.items():
            if key.startswith("_") or key in skip:
                continue
            if isinstance(value, dict):
                preset[key] = dict(value)
            else:
                preset["_general"][key] = value
        return preset

    def save_user_preset(self, name: str, description: str = "") -> bool:
        """
        Save the current parameters as a user preset called ``name``.

        Returns:
            bool: False when the name is empty or taken by a built-in preset.
        """
        name = name.strip()
        if not name or name.startswith("_") or name in self.load_presets():
            return False
        state = self._read_user_preset_state_for_write(
            "The preset was not saved, the existing presets are left unchanged."
        )
        if state is None:
            return False
        preset = self.snapshot_preset()
        if description:
            preset["_description"] = description
        state["presets"][name] = preset
        # The settings now are exactly this preset
        state["applied"] = name
        self._write_user_preset_state(state)
        return True

    def delete_user_preset(self, name: str) -> bool:
        """Delete a user preset; returns False if there is none of that name."""
        state = self._read_user_preset_state_for_write(
            "No preset was deleted, the existing presets are left unchanged."
        )
        if state is None or name not in state["presets"]:
            return False
        del state["presets"][name]
        if state.get("applied") == name:
            state["applied"] = None
        self._write_user_preset_state(state)
        return True

    def apply_preset(self, preset_name: str) -> bool:
        """
        Apply a preset by updating params.json and clearing relevant session_state keys.

        Uses the "delete-then-rerun" pattern: instead of overwriting session_state
        values (which widgets may not reflect immediately due to fragment caching),
        we delete the keys so widgets re-initialize fresh from params.json on rerun.

        A built-in preset (presets.json) changes only the values it names. A user
        preset is a full snapshot, so it first returns every TOPP parameter to its
        default and then sets the saved values.

        Args:
            preset_name: Name of the preset to apply

        Returns:
            bool: True if preset was applied successfully, False otherwise.
        """
        # Read strictly before params.json is written, which records the
        # applied preset afterwards and must not replace saved presets
        state = self._read_user_preset_state_for_write(
            "The preset was not applied, the existing files are left unchanged."
        )
        if state is None:
            return False
        preset = self.load_presets().get(preset_name)
        is_user_preset = False
        if not preset:
            preset = state["presets"].get(preset_name)
            is_user_preset = True
        if not preset:
            return False

        # Load existing parameters. Strict, because this is a read-modify-write
        # back too: a tolerant empty dict here would delete every parameter the
        # preset does not mention and still report success.
        try:
            current_params = self.read_parameters_strict()
        except InvalidParameterFileError as e:
            self._report_unreadable_parameter_file(
                e, "The preset was not applied, the existing file is left unchanged."
            )
            return False

        # Collect keys to delete from session_state
        keys_to_delete = []

        if is_user_preset:
            # Back to defaults for every TOPP tool before restoring the snapshot
            for key, value in list(current_params.items()):
                if isinstance(value, dict) and not key.startswith("_"):
                    current_params[key] = {}
            keys_to_delete.extend(
                k for k in st.session_state.keys() if k.startswith(self.topp_param_prefix)
            )

        for key, value in preset.items():
            # Skip description key
            if key == "_description":
                continue

            if key == "_general":
                # Handle general workflow parameters
                for param_name, param_value in (value if isinstance(value, dict) else {}).items():
                    session_key = f"{self.param_prefix}{param_name}"
                    keys_to_delete.append(session_key)
                    current_params[param_name] = param_value
            elif isinstance(value, dict) and not key.startswith("_"):
                # Handle TOPP tool parameters
                tool_name = key
                if tool_name not in current_params:
                    current_params[tool_name] = {}
                for param_name, param_value in value.items():
                    session_key = f"{self.topp_param_prefix}{tool_name}:1:{param_name}"
                    keys_to_delete.append(session_key)
                    current_params[tool_name][param_name] = param_value

        # Delete affected keys from session_state so widgets re-initialize fresh
        for session_key in keys_to_delete:
            if session_key in st.session_state:
                del st.session_state[session_key]

        # Save updated parameters to file
        _write_parameter_file(self.params_file, current_params)

        state["applied"] = preset_name
        self._write_user_preset_state(state)

        return True

    @staticmethod
    def _same_value(a, b) -> bool:
        """Equal, allowing for 20 vs 20.0 and a list stored as newline-joined text."""
        if isinstance(a, list) and isinstance(b, str):
            return "\n".join(map(str, a)) == b
        if isinstance(b, list) and isinstance(a, str):
            return "\n".join(map(str, b)) == a
        return a == b

    def applied_preset_status(self) -> tuple[str | None, bool]:
        """
        The preset applied last and whether the settings have changed since.

        A built-in preset counts as changed when a value it sets differs now. A
        user preset counts as changed when any setting differs from its snapshot.

        Returns:
            tuple: (preset name or None, changed since applying it).
        """
        name = self._read_user_preset_state().get("applied")
        if not name:
            return None, False
        builtin = self.load_presets().get(name)
        preset = builtin or self.load_user_presets().get(name)
        if not preset:
            return None, False
        current = self.snapshot_preset()
        for key, values in preset.items():
            if key == "_description" or not isinstance(values, dict):
                continue
            now = current.get(key, {})
            for param, value in values.items():
                if param not in now or not self._same_value(now[param], value):
                    return name, True
        if builtin is None:
            # Settings the snapshot left at their default but that are set now
            for key, values in current.items():
                saved = preset.get(key, {})
                if any(param not in saved for param in values):
                    return name, True
        return name, False

    def forget_applied_preset(self) -> None:
        """Clear the applied preset, e.g. after resetting to the default parameters."""
        state = self._read_user_preset_state_for_write(
            "The saved presets are left unchanged."
        )
        if state is not None and state.get("applied"):
            state["applied"] = None
            self._write_user_preset_state(state)

    def clear_parameter_session_state(self) -> None:
        """
        Clear all parameter-related keys from session_state.

        This forces widgets to re-initialize from params.json or defaults
        on the next rerun, rather than using potentially stale session_state values.
        """
        keys_to_delete = [
            key for key in list(st.session_state.keys())
            if key.startswith(self.param_prefix) or key.startswith(self.topp_param_prefix)
        ]
        for key in keys_to_delete:
            del st.session_state[key]