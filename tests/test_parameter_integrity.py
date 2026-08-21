"""
Parameter-file integrity tests.

These pin the contract that a *failed read* of ``params.json`` must never turn
into a *write* that erases it — the live data-loss bug recorded as A2 in
``node-distributed-denbi/DEFECTS.md`` and the first item of Step 1 in the
multi-node distribution plan.

The bug, end to end:

* ``ParameterManager.save_parameters()`` is a read-modify-write:
  ``ParameterManager.py:136`` does ``self.get_parameters_from_json() | json_params``.
* ``get_parameters_from_json()`` (``:193-212``) wraps the read in a bare
  ``except:`` that returns ``{}`` for *any* failure — a torn read from a
  concurrent truncate-then-rewrite, an unreadable file, anything.
* So one transient bad read makes the merge ``{} | this_session_params``, and
  that subset is written back, permanently deleting ``_defaults``,
  ``_flag_params`` and every other tool's stored values — while telling the user
  it was a deliberate "Reset to defaults".

``apply_preset()`` (``:345``) has the identical shape and is covered here too.
The plan's fix is to split the read: a tolerant ``get_parameters_from_json()``
that keeps returning ``{}`` for its read-only callers, and a strict
``read_parameters_strict()`` that **raises** on a malformed file and returns
``{}`` only for a genuinely absent one, used by the read-modify-write-back
sites. Conflating "absent" with "unreadable" *is* the bug, so both branches get
their own test.

The next group pins the shapes an unreadable file actually takes on a shared,
restartable filesystem — a bad encoding, JSON that is not an object, a directory
in its place, and a storage blip that clears by itself — plus the two halves of
the recovery: the write must be atomic, and the reset offered on failure must
not be the thing that destroys the data.

The last two groups cover G1: ``CommandExecutor._get_max_threads()`` reads
settings out of ``st.session_state``, which is empty inside the RQ work horse,
so the configured ``max_threads`` has been silently replaced by a hardcoded
``4``; and ``src/workflow/settings_io.load_settings()``, the Streamlit-free
loader it now reads them through.

Every test here is expected to fail before Step 1 lands.
"""
import builtins
import contextlib
import errno
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Import the modules under test with `streamlit` (and `pyopenms`) mocked at the
# sys.modules level, mirroring tests/test_topp_flag_parameters.py. Both modules
# do `import streamlit as st` at the top (ParameterManager also
# `import pyopenms as poms`); nothing exercised here needs more than a dict-like
# `st.session_state`, so the mocks keep the suite runnable without the heavy
# deps while still driving the real read/merge/write logic.
# ---------------------------------------------------------------------------
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_original_streamlit = sys.modules.get("streamlit")
_original_pyopenms = sys.modules.get("pyopenms")
sys.modules["streamlit"] = mock_streamlit
if _original_pyopenms is None:
    sys.modules["pyopenms"] = MagicMock()

from src.workflow.ParameterManager import ParameterManager
from src.workflow.CommandExecutor import CommandExecutor
from src.workflow.settings_io import load_settings

# Restore the original modules so other test files import the real ones. The
# classes imported above keep their module-level `st`/`poms` bound to the mocks.
if _original_streamlit is not None:
    sys.modules["streamlit"] = _original_streamlit
else:
    sys.modules.pop("streamlit", None)
if _original_pyopenms is None:
    sys.modules.pop("pyopenms", None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


# Name of the strict, raising reader introduced by Step 1 of the plan.
STRICT_READER_NAME = "read_parameters_strict"

# Reached through the class rather than imported, because the sys.modules
# entries for src.workflow.* are popped after the import block above - and
# because the name does not exist before Step 1, so importing it at module
# scope would turn this file into a collection error instead of a failure.
_MODULE_GLOBALS = ParameterManager.__init__.__globals__


def _error_class(name: str) -> type:
    """The named exception class from ParameterManager, or fail loudly."""
    cls = _MODULE_GLOBALS.get(name)
    if cls is None:
        pytest.fail(
            f"ParameterManager.{name} does not exist. Step 1 of the plan "
            "requires a read failure to be reported as its own exception type, "
            "so that every read-modify-write-back site can abort on it."
        )
    return cls


def invalid_parameter_file_error() -> type:
    """The exception a failed strict read raises."""
    return _error_class("InvalidParameterFileError")


def transient_parameter_file_error() -> type:
    """
    The subclass used for a read failure expected to clear by itself.

    A restarted NFS export makes clients ESTALE for a moment. Reporting that
    the same way as a corrupt file sends the user to a reset affordance which
    would delete a perfectly intact params.json.
    """
    return _error_class("TransientParameterFileError")


# The one general parameter whose widget is on screen in the tests below, i.e.
# the only key the saving session legitimately owns.
CHANGED_KEY = "example-general-param"

# A realistic, fully populated params.json: the reserved keys, two TOPP tools'
# stored values, and two general parameters. A session that is not currently
# rendering the TOPP widgets (a different page, a collapsed fragment, advanced
# view off) holds *none* of this in session state — which is exactly why
# save_parameters() merges the file back in, and exactly what a laundered `{}`
# destroys.
FULL_PARAMS = {
    "_defaults": {
        "FeatureFinderMetabo": {"algorithm:common:noise_threshold_int": 1000.0},
        "MetaboliteAdductDecharger": {
            "algorithm:MetaboliteFeatureDeconvolution:charge_max": 3
        },
    },
    "_flag_params": {"FeatureFinderMetabo": ["force"]},
    "max_threads": 3,
    "FeatureFinderMetabo": {
        "algorithm:common:noise_threshold_int": 500.0,
        "algorithm:mtd:mass_error_ppm": 10.0,
    },
    "MetaboliteAdductDecharger": {
        "algorithm:MetaboliteFeatureDeconvolution:charge_max": 2
    },
    CHANGED_KEY: "keep-me",
    "run-adduct-detection": True,
}


@pytest.fixture(autouse=True)
def reset_session_state():
    """Give each test a fresh, empty mocked session_state."""
    mock_streamlit.session_state = {}
    yield
    mock_streamlit.session_state = {}


def _assert_unparseable(text: str) -> None:
    """Guard the fixtures themselves: the corruption must really break json."""
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)


def _write_torn_params_file(pm: ParameterManager) -> str:
    """
    Leave params.json holding FULL_PARAMS plus a fragment of a second write.

    This is what a reader sees when a concurrent writer's truncate-then-rewrite
    interleaves with it: unparseable, but with every original byte still on
    disk and recoverable by hand — until something rewrites the file.

    Returns the full text that was written.
    """
    text = json.dumps(FULL_PARAMS, indent=4) + '\n{\n    "_defaults": {\n'
    _assert_unparseable(text)
    pm.params_file.write_text(text, encoding="utf-8")
    return text


def _require_strict_reader(pm: ParameterManager):
    """
    Return the strict reader from Step 1 of the plan, or fail loudly.

    Accepts either a ``ParameterManager`` method or a module-level function
    taking the params file path, since only the name and the behaviour are
    pinned by the plan. Uses ``pytest.fail`` (a BaseException) rather than
    letting an AttributeError escape, so that a ``pytest.raises(Exception)``
    around the call cannot mistake "not implemented yet" for "raised properly".
    """
    reader = getattr(pm, STRICT_READER_NAME, None)
    if reader is not None:
        return reader

    # sys.modules entries for src.workflow.* are popped after import above, so
    # reach the module namespace through the class instead.
    module_globals = ParameterManager.__init__.__globals__
    fn = module_globals.get(STRICT_READER_NAME)
    if fn is not None:
        return lambda: fn(pm.params_file)

    pytest.fail(
        f"ParameterManager.{STRICT_READER_NAME}() does not exist. Step 1 of the "
        "plan requires a strict reader that raises on a malformed params.json "
        "and returns {} only for an absent one, used by every "
        "read-modify-write-back site."
    )


# ---------------------------------------------------------------------------
# The erasure bug (DEFECTS.md A2)
# ---------------------------------------------------------------------------


def test_corrupt_read_does_not_erase(tmp_path):
    """
    A session holding a subset of the keys must not be able to delete the rest.

    Sequence: params.json holds two tools' values plus `_defaults` and
    `_flag_params`; a second process's write leaves the file momentarily
    unparseable; this session — which only ever rendered one general widget —
    saves. Whether save_parameters() refuses loudly or quietly is not pinned
    here; what is pinned is that nothing on disk is lost.
    """
    pm = ParameterManager(tmp_path)
    torn_text = _write_torn_params_file(pm)

    # Only one key is in session state: the widget this page actually rendered.
    mock_streamlit.session_state = {f"{pm.param_prefix}{CHANGED_KEY}": "changed"}

    # Narrow on purpose: aborting the write is the point, but it must abort on
    # the read failure and nothing else. A blanket suppress would let any crash
    # satisfy the assertions below.
    with contextlib.suppress(invalid_parameter_file_error()):
        pm.save_parameters()

    surviving_text = pm.params_file.read_text(encoding="utf-8")

    try:
        surviving = json.loads(surviving_text)
    except json.JSONDecodeError:
        # The file was left alone: still corrupt, but every byte is there and
        # it can be repaired. Nothing was laundered away.
        assert surviving_text == torn_text, (
            "params.json was partially rewritten after a failed read; it must "
            "be left intact so the stored parameters remain recoverable"
        )
        return

    # The file was rewritten, so it has to be at least as complete as before.
    for key, value in FULL_PARAMS.items():
        assert key in surviving, (
            f"'{key}' was erased from params.json by a save that could not read "
            "it first (DEFECTS.md A2): the failed read became an empty dict and "
            f"the merge wrote back only this session's subset {sorted(surviving)}"
        )
        if key != CHANGED_KEY:
            assert surviving[key] == value, (
                f"'{key}' lost its stored value after a failed read: "
                f"{surviving[key]!r} != {value!r}"
            )


def test_truncated_read_does_not_rewrite_params_file(tmp_path):
    """
    Same bug, second corruption shape: a half-written file.

    Here the tail of the original content is genuinely gone from disk, so the
    only safe behaviour is to touch nothing — a rewrite would replace a
    repairable file with a valid-JSON file that has silently lost everything.
    """
    pm = ParameterManager(tmp_path)
    full_text = json.dumps(FULL_PARAMS, indent=4)
    half_written = full_text[: len(full_text) // 2]
    _assert_unparseable(half_written)
    pm.params_file.write_text(half_written, encoding="utf-8")
    before = pm.params_file.read_bytes()

    mock_streamlit.session_state = {f"{pm.param_prefix}{CHANGED_KEY}": "changed"}

    with contextlib.suppress(invalid_parameter_file_error()):
        pm.save_parameters()

    assert pm.params_file.read_bytes() == before, (
        "params.json was rewritten from a session subset after a torn read; "
        "the unreadable file must be preserved, not replaced"
    )


def test_apply_preset_does_not_erase_on_corrupt_read(tmp_path, monkeypatch):
    """
    apply_preset() is the second read-modify-write-back site (:345).

    It has the same shape as save_parameters() — read, merge, write — so an
    unreadable file makes applying a preset delete every parameter the preset
    does not mention, and report success while doing it.
    """
    workflow_dir = tmp_path / "topp-workflow"
    workflow_dir.mkdir()
    pm = ParameterManager(workflow_dir, workflow_name="TOPP Workflow")
    torn_text = _write_torn_params_file(pm)

    # presets.json is read relative to the process CWD (ParameterManager.py:287).
    cwd = tmp_path / "app-root"
    cwd.mkdir()
    (cwd / "presets.json").write_text(
        json.dumps(
            {
                "topp-workflow": {
                    "High Sensitivity": {
                        "_description": "Tooltip text",
                        "FeatureFinderMetabo": {
                            "algorithm:common:noise_threshold_int": 50.0
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(cwd)

    result = None
    with contextlib.suppress(invalid_parameter_file_error()):
        result = pm.apply_preset("High Sensitivity")

    assert result is not True, (
        "apply_preset() reported success against a params.json it could not read"
    )

    surviving_text = pm.params_file.read_text(encoding="utf-8")
    try:
        surviving = json.loads(surviving_text)
    except json.JSONDecodeError:
        assert surviving_text == torn_text, (
            "params.json was partially rewritten while applying a preset over "
            "an unreadable file"
        )
        return

    for key in FULL_PARAMS:
        assert key in surviving, (
            f"'{key}' was erased by apply_preset() after a failed read; the "
            f"file now holds only {sorted(surviving)}"
        )


# ---------------------------------------------------------------------------
# Absent vs unreadable — the distinction whose absence causes the erasure
# ---------------------------------------------------------------------------


def test_absent_parameter_file_reads_as_empty(tmp_path):
    """An absent params.json is a first run, not a failure: {} is correct."""
    pm = ParameterManager(tmp_path)
    assert not pm.params_file.exists()

    assert pm.get_parameters_from_json() == {}
    assert _require_strict_reader(pm)() == {}, (
        "the strict reader must still return {} for a genuinely absent file — "
        "a first run has no parameters and that is not an error"
    )


def test_malformed_parameter_file_does_not_read_as_empty(tmp_path):
    """
    A malformed params.json must be distinguishable from an absent one.

    Returning {} for both is what lets save_parameters() merge an empty dict
    over real data. The tolerant reader keeps its {} contract for its read-only
    callers; the strict reader used by the write-back sites must raise.
    """
    pm = ParameterManager(tmp_path)
    _write_torn_params_file(pm)

    reader = _require_strict_reader(pm)
    with pytest.raises(invalid_parameter_file_error()):
        result = reader()
        pytest.fail(
            f"the strict reader returned {result!r} for an unreadable "
            "params.json instead of raising; an unreadable file must never be "
            "reported as 'no parameters'"
        )

    # Deliberate asymmetry: the tolerant reader keeps its signature and its {}
    # for the constructors and read-only callers that cannot handle a raise.
    assert pm.get_parameters_from_json() == {}


# ---------------------------------------------------------------------------
# max_threads outside a Streamlit session (DEFECTS.md G1)
# ---------------------------------------------------------------------------


def _executor_in_worker(
    tmp_path, monkeypatch, settings, params_json=None, cpu_quota=None
):
    """
    Build a CommandExecutor under the RQ work horse's real conditions.

    `cpu_quota` pins what detect_cpu_quota() reports. It defaults to None — "no
    readable CPU ceiling" — so the settings-driven tests below assert the
    setting rather than whatever cgroup the test host happens to have. Left
    unpinned they would pass on an unconstrained runner and fail the moment CI
    ran inside a container with a quota, which is a fixture reading the
    environment rather than a test.

    No ScriptRunContext means `st.session_state` is an empty global mock, so
    `st.session_state.get("settings", {})` yields {} and every configured value
    has to come from settings.json, which this repo resolves against the process
    CWD everywhere it is read (app.py:8, common.py:362, QueueManager.py:74,
    test_gui.py:14). The chdir happens before the executor is built so that
    memoising the lookup — which the plan requires, since run_topp() calls it
    twice and the two calls must agree — cannot serve a value read from some
    other directory.
    """
    cwd = tmp_path / "app-root"
    cwd.mkdir()
    (cwd / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    workflow_dir = tmp_path / "workflow"
    workflow_dir.mkdir()

    monkeypatch.chdir(cwd)
    monkeypatch.delenv("REDIS_URL", raising=False)
    # Reached through the function's own globals, not by dotted name: the
    # import block above pops src.workflow.* from sys.modules, so a string
    # target would re-import a *different* CommandExecutor module - one bound
    # to the real streamlit - and patch a copy this executor never calls.
    monkeypatch.setitem(
        CommandExecutor._get_max_threads.__globals__,
        "detect_cpu_quota",
        lambda: cpu_quota,
    )

    pm = ParameterManager(workflow_dir)
    if params_json is not None:
        pm.params_file.write_text(json.dumps(params_json), encoding="utf-8")

    mock_streamlit.session_state = {}
    return CommandExecutor(workflow_dir, MagicMock(), pm)


def test_max_threads_without_session_state(tmp_path, monkeypatch):
    """
    The worker must honour max_threads.online, not the hardcoded literal 4.

    `st.session_state.get("settings", {})` is {} inside the work horse, so the
    online branch of _get_max_threads() (CommandExecutor.py:41) is unreachable
    there and the local branch's hardcoded 4 wins — dead config since #333
    (DEFECTS.md G1), and a correctness bug once a worker has a hard memory
    limit sized for a known thread count.
    """
    executor = _executor_in_worker(
        tmp_path,
        monkeypatch,
        {"online_deployment": True, "max_threads": {"local": 9, "online": 6}},
    )

    assert executor._get_max_threads() == 6, (
        "max_threads.online was ignored outside a Streamlit session; a value of "
        "4 means the hardcoded literal was used instead of settings.json"
    )


def test_max_threads_local_without_session_state_uses_configured_local(
    tmp_path, monkeypatch
):
    """Same failure in local mode: the configured local value, not the literal 4."""
    executor = _executor_in_worker(
        tmp_path,
        monkeypatch,
        {"online_deployment": False, "max_threads": {"local": 9, "online": 6}},
    )

    assert executor._get_max_threads() == 9, (
        "max_threads.local from settings.json was ignored; 4 is the hardcoded "
        "fallback that only applies when the setting is missing entirely"
    )


def test_max_threads_online_ignores_workspace_params_json(tmp_path, monkeypatch):
    """
    In online mode the workspace's params.json must not set the thread budget.

    Workers are shared and params.json is user-supplied — the import uploader
    writes it verbatim, with no reserved-key filter (DEFECTS.md G2) — so the
    per-workspace value may only apply to the local, single-user deployment.
    """
    executor = _executor_in_worker(
        tmp_path,
        monkeypatch,
        {"online_deployment": True, "max_threads": {"local": 9, "online": 6}},
        params_json={"max_threads": 3, "example-general-param": "x"},
    )

    assert executor._get_max_threads() == 6, (
        "a workspace params.json overrode max_threads.online on a shared worker"
    )


# ---------------------------------------------------------------------------
# The shapes an unreadable params.json actually takes
# ---------------------------------------------------------------------------


def test_undecodable_parameter_file_does_not_read_as_empty(tmp_path):
    """
    A params.json that is not valid UTF-8 is unreadable, not empty.

    UnicodeDecodeError subclasses ValueError, not OSError, so a handler
    catching (JSONDecodeError, OSError) misses it entirely: it escapes the
    tolerant reader - which both constructors call, taking the whole page down
    - and escapes the strict reader as a type no `except
    InvalidParameterFileError` guard catches, so save_parameters() loses its
    "left unchanged" protection.

    Reachable in this repo: the parameter import uploader decodes the upload as
    utf-8 and writes it back out, and a torn write can also cut a multi-byte
    sequence in half.
    """
    pm = ParameterManager(tmp_path)
    # cp1252 bytes for {"note": "\u00b5m tolerance"} - 0xb5 is not valid UTF-8.
    pm.params_file.write_bytes(b'{"note": "\xb5m tolerance"}')
    before = pm.params_file.read_bytes()

    with pytest.raises(invalid_parameter_file_error()):
        _require_strict_reader(pm)()

    assert pm.get_parameters_from_json() == {}, (
        "the tolerant reader must keep degrading to {} - its two callers are "
        "constructors with no way to handle a raise"
    )

    mock_streamlit.session_state = {f"{pm.param_prefix}{CHANGED_KEY}": "changed"}
    with contextlib.suppress(invalid_parameter_file_error()):
        pm.save_parameters()

    assert pm.params_file.read_bytes() == before, (
        "params.json was rewritten from a session subset after an undecodable "
        "read"
    )


@pytest.mark.parametrize(
    "content", ["[1, 2, 3]", '"just a string"', "42", "null"], ids=["array", "string", "number", "null"]
)
def test_parameter_file_that_is_not_an_object_is_rejected(tmp_path, content):
    """
    Valid JSON that is not an object is still not a parameter dict.

    ``{} | ["a"]`` raises and ``{} | "x"`` raises, but a JSON ``null`` merges as
    nothing at all - so without this guard the strict reader would hand a
    non-dict to the merge and either crash the run or quietly erase the file.
    """
    pm = ParameterManager(tmp_path)
    pm.params_file.write_text(content, encoding="utf-8")

    with pytest.raises(invalid_parameter_file_error()):
        _require_strict_reader(pm)()

    assert pm.get_parameters_from_json() == {}


def test_directory_in_place_of_parameter_file_is_rejected(tmp_path):
    """
    A directory where params.json should be is unreadable, not absent.

    Raises IsADirectoryError on Linux and PermissionError on Windows; both are
    OSError, and neither may be reported as "no parameters stored".
    """
    pm = ParameterManager(tmp_path)
    pm.params_file.mkdir()

    with pytest.raises(invalid_parameter_file_error()):
        _require_strict_reader(pm)()

    assert pm.get_parameters_from_json() == {}
    assert pm.params_file.is_dir(), "the directory must be left in place"


def _flaky_open(monkeypatch, target: Path, failures: int, errno_value: int) -> None:
    """Make the first ``failures`` opens of ``target`` fail with ``errno_value``."""
    real_open = builtins.open
    remaining = {"n": failures}

    def fake_open(file, *args, **kwargs):
        if (
            isinstance(file, (str, os.PathLike))
            and Path(file) == target
            and remaining["n"] > 0
        ):
            remaining["n"] -= 1
            raise OSError(errno_value, os.strerror(errno_value))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    # The retry delay is real time; nothing here depends on its duration.
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


def test_transient_read_failure_is_retried(tmp_path, monkeypatch):
    """
    ESTALE from a restarted NFS export must not be reported as corruption.

    Invariant 2 of the plan expects the Ganesha pod to be restarted by
    upgrades, evictions and node drains. Every client ESTALEs while it comes
    back. With no retry, a routine restart puts the user in front of a "reset
    to defaults" button whose only effect would be to delete an intact file.
    """
    pm = ParameterManager(tmp_path)
    pm.params_file.write_text(json.dumps(FULL_PARAMS, indent=4), encoding="utf-8")
    _flaky_open(monkeypatch, pm.params_file, failures=1, errno_value=errno.ESTALE)

    assert _require_strict_reader(pm)() == FULL_PARAMS, (
        "a single ESTALE must be retried, not turned into a permanent failure"
    )


def test_persistent_transient_failure_is_reported_as_transient(tmp_path, monkeypatch):
    """
    A storage outage that outlasts the retries is still not corruption.

    It stays an InvalidParameterFileError - every write-back site must still
    abort, the content is unknown - but as a distinguishable subclass, so the
    UI can withhold the destructive reset affordance.
    """
    pm = ParameterManager(tmp_path)
    pm.params_file.write_text(json.dumps(FULL_PARAMS, indent=4), encoding="utf-8")
    _flaky_open(monkeypatch, pm.params_file, failures=99, errno_value=errno.ESTALE)

    with pytest.raises(transient_parameter_file_error()):
        _require_strict_reader(pm)()

    assert issubclass(
        transient_parameter_file_error(), invalid_parameter_file_error()
    ), (
        "it must stay a subclass, or every existing `except "
        "InvalidParameterFileError` write-back guard stops catching it"
    )


def test_permanent_read_failure_is_not_reported_as_transient(tmp_path):
    """The control: a corrupt file must not be misreported as a passing blip."""
    pm = ParameterManager(tmp_path)
    _write_torn_params_file(pm)

    with pytest.raises(invalid_parameter_file_error()) as excinfo:
        _require_strict_reader(pm)()

    assert not isinstance(excinfo.value, transient_parameter_file_error()), (
        "unparseable content will never clear by itself; offering 'try again' "
        "for it leaves the user with no way forward"
    )


def test_interrupted_write_leaves_the_previous_parameters_intact(tmp_path, monkeypatch):
    """
    A write that dies half way must not leave a file that is neither version.

    Truncate-then-rewrite plus an OOM kill or ENOSPC - the failure modes this
    deployment is being sized against - leaves a torn params.json which every
    later strict read rejects. save_parameters() then becomes a permanent
    silent no-op and the parameter page stops on every render, with only the
    destructive reset left as an escape.
    """
    pm = ParameterManager(tmp_path)
    pm.params_file.write_text(json.dumps(FULL_PARAMS, indent=4), encoding="utf-8")
    before = pm.params_file.read_bytes()

    def half_written_dump(obj, fp, **kwargs):
        fp.write('{\n    "_defaults": {')
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(json, "dump", half_written_dump)
    mock_streamlit.session_state = {f"{pm.param_prefix}{CHANGED_KEY}": "changed"}

    with pytest.raises(OSError):
        pm.save_parameters()

    monkeypatch.undo()

    assert pm.params_file.read_bytes() == before, (
        "params.json holds a half-written document; the write must go to a "
        "temporary file and be moved into place with os.replace()"
    )
    assert json.loads(pm.params_file.read_text(encoding="utf-8")) == FULL_PARAMS
    leftovers = [q.name for q in tmp_path.iterdir() if q.name.endswith(".tmp")]
    assert leftovers == [], f"scratch files left behind: {leftovers}"


def test_reset_keeps_the_previous_parameters(tmp_path):
    """
    The recovery offered for an unreadable file must not be the data loss.

    reset_to_default_parameters() backs the reading UI's "reset to defaults"
    button, which is offered exactly when the file could not be read - and an
    unreadable file is very often a healthy file behind a storage blip.
    Deleting it there converts a self-healing outage into permanent loss.
    """
    pm = ParameterManager(tmp_path)
    torn_text = _write_torn_params_file(pm)

    backup = pm.reset_to_default_parameters()

    assert not pm.params_file.exists(), "the workflow must start from defaults"
    assert backup is not None and backup.exists(), (
        "the previous parameter file must be kept, not unlinked"
    )
    assert backup.read_text(encoding="utf-8") == torn_text
    assert pm.get_parameters_from_json() == {}


def test_reset_handles_a_directory_in_place_of_the_parameter_file(tmp_path):
    """
    unlink() raises on a directory, so the reset button used to raise too -
    leaving the parameter page stopped on every render with no way out.
    """
    pm = ParameterManager(tmp_path)
    pm.params_file.mkdir()
    (pm.params_file / "unexpected.txt").write_text("x", encoding="utf-8")

    backup = pm.reset_to_default_parameters()

    assert not pm.params_file.exists()
    assert backup is not None and backup.is_dir()


def test_reset_with_no_stored_parameters_is_a_no_op(tmp_path):
    """Nothing stored, nothing to preserve - and no crash."""
    pm = ParameterManager(tmp_path)
    assert pm.reset_to_default_parameters() is None
    assert not pm.params_file.exists()


# ---------------------------------------------------------------------------
# settings_io.load_settings - the Streamlit-free loader _get_max_threads uses
# ---------------------------------------------------------------------------


def test_load_settings_reads_the_file_in_the_working_directory(tmp_path, monkeypatch):
    """The default path resolves against the CWD, as every other reader does."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "settings.json").write_text(
        json.dumps({"online_deployment": True}), encoding="utf-8"
    )

    assert load_settings() == {"online_deployment": True}


def test_load_settings_accepts_an_explicit_path(tmp_path):
    elsewhere = tmp_path / "config" / "settings.json"
    elsewhere.parent.mkdir()
    elsewhere.write_text(json.dumps({"max_threads": {"online": 6}}), encoding="utf-8")

    assert load_settings(elsewhere) == {"max_threads": {"online": 6}}


def test_load_settings_absent_file_is_empty(tmp_path):
    assert load_settings(tmp_path / "nothing-here.json") == {}


@pytest.mark.parametrize(
    "content",
    ["{not json", "[1, 2, 3]", '"a string"', ""],
    ids=["malformed", "array", "string", "empty"],
)
def test_load_settings_unusable_content_is_empty(tmp_path, content):
    """
    Total by construction, as its docstring promises and QueueManager relies on.

    QueueManager._load_settings() delegates here and is documented to return an
    empty dict on failure; it is called from QueueManager.__init__, which
    WorkflowManager.__init__ calls behind an `except ImportError` that would not
    catch anything else. CommandExecutor._get_max_threads() calls it inside the
    RQ work horse, where a raise kills the job.
    """
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(content, encoding="utf-8")

    assert load_settings(settings_file) == {}


def test_load_settings_survives_a_non_utf8_file(tmp_path):
    """
    A settings.json in the platform codepage must not be fatal here alone.

    app.py and src/common/common.py open it with the platform default encoding,
    so a file hand-edited on a Windows box loads in the UI. If this loader is
    the only strict reader, the same file starts the app and then kills the RQ
    worker - the exact split it was written to remove.
    """
    settings_file = tmp_path / "settings.json"
    # cp1252 for {"app-name": "M\u00fcller Lab", "online_deployment": true}
    settings_file.write_bytes(
        b'{"app-name": "M\xfcller Lab", "online_deployment": true}'
    )

    settings = load_settings(settings_file)

    assert settings.get("online_deployment") is True, (
        "an undecodable byte in one value must not lose the whole file"
    )


def test_load_settings_unreadable_file_is_empty(tmp_path):
    """A directory in place of settings.json is an OSError, not a crash."""
    settings_file = tmp_path / "settings.json"
    settings_file.mkdir()

    assert load_settings(settings_file) == {}


def test_max_threads_is_memoised(tmp_path, monkeypatch):
    """
    run_topp() consults _get_max_threads() twice - once for its own thread
    split, once inside run_multiple_commands() - and the two must agree, or the
    per-command budget and the parallelism are computed from different numbers.
    """
    executor = _executor_in_worker(
        tmp_path,
        monkeypatch,
        {"online_deployment": True, "max_threads": {"local": 9, "online": 6}},
    )

    first = executor._get_max_threads()
    Path("settings.json").write_text(
        json.dumps({"online_deployment": True, "max_threads": {"online": 1}}),
        encoding="utf-8",
    )

    assert executor._get_max_threads() == first, (
        "the thread budget was re-read mid-run; the two call sites in run_topp() "
        "would then disagree"
    )


# ---------------------------------------------------------------------------
# max_threads from the container's cgroup CPU quota
#
# The rq-worker runs at requests.cpu == limits.cpu (Guaranteed QoS), and the
# memory-tier components size that per deployment - 4 cpu on the low tier, 20
# on the high one. A single max_threads.online in settings.json cannot describe
# both, so where a real quota is readable it wins, and the setting stays as the
# fallback for deployments that have none.
# ---------------------------------------------------------------------------


def _settings_io_ns():
    """
    The real detect_cpu_quota and the module globals it reads its paths from.

    Same reason as the monkeypatch in _executor_in_worker: src.workflow.* is
    popped from sys.modules by the import block at the top of this file, so
    `from src.workflow import settings_io` would build a SECOND module object
    and patching its constants would leave the function under test reading the
    real /sys/fs/cgroup. Going through __globals__ reaches the namespace the
    live function actually closes over.
    """
    detect = CommandExecutor._get_max_threads.__globals__["detect_cpu_quota"]
    return detect, detect.__globals__


def test_cpu_quota_beats_configured_online_value(tmp_path, monkeypatch):
    """A readable quota is the allocation; max_threads.online is only a guess."""
    executor = _executor_in_worker(
        tmp_path,
        monkeypatch,
        {"online_deployment": True, "max_threads": {"local": 9, "online": 2}},
        cpu_quota=20,
    )

    assert executor._get_max_threads() == 20, (
        "the container's own CPU quota was ignored in favour of a static "
        "max_threads.online, which is wrong on every tier it was not written for"
    )


def test_cpu_quota_ignored_in_local_mode(tmp_path, monkeypatch):
    """
    Local mode keeps its params.json override.

    The Threads widget is rendered only locally and writing it must keep
    working, so quota detection has to stay confined to the online branch.
    """
    executor = _executor_in_worker(
        tmp_path,
        monkeypatch,
        {"online_deployment": False, "max_threads": {"local": 9, "online": 2}},
        params_json={"max_threads": 3},
        cpu_quota=20,
    )

    assert executor._get_max_threads() == 3, (
        "cgroup detection leaked into local mode and overrode the user's "
        "Threads setting"
    )


def test_configured_online_value_used_when_no_quota(tmp_path, monkeypatch):
    """No quota - bare metal, an unlimited container - falls back to settings."""
    executor = _executor_in_worker(
        tmp_path,
        monkeypatch,
        {"online_deployment": True, "max_threads": {"local": 9, "online": 6}},
        cpu_quota=None,
    )

    assert executor._get_max_threads() == 6


@pytest.mark.parametrize(
    "cpu_max, expected",
    [
        ("400000 100000", 4),      # cpu: 4
        ("2000000 100000", 20),    # cpu: 20, the high tier
        ("150000 100000", 2),      # cpu: 1500m rounds UP, not down
        ("50000 100000", 1),       # cpu: 500m floors at 1, never 0
        ("max 100000", None),      # unconstrained
        ("garbage", None),
        ("", None),
    ],
)
def test_detect_cpu_quota_cgroup_v2(tmp_path, monkeypatch, cpu_max, expected):
    """cgroup v2 writes '<quota> <period>', or 'max <period>' when unlimited."""
    detect, g = _settings_io_ns()

    cpu_file = tmp_path / "cpu.max"
    cpu_file.write_text(cpu_max, encoding="utf-8")
    monkeypatch.setitem(g, "CGROUP_V2_CPU_MAX", cpu_file)
    # Point v1 at somewhere absent, so a fallthrough cannot be mistaken for a
    # v2 read succeeding.
    monkeypatch.setitem(g, "CGROUP_V1_CPU_QUOTA", tmp_path / "nope" / "cfs_quota_us")

    assert detect() == expected


@pytest.mark.parametrize(
    "quota, period, expected",
    [
        ("400000", "100000", 4),
        ("-1", "100000", None),     # v1's documented "no limit"
        ("0", "100000", None),      # not a legal quota; never a 0 thread budget
    ],
)
def test_detect_cpu_quota_cgroup_v1(tmp_path, monkeypatch, quota, period, expected):
    """cgroup v1 splits the same information across two files, -1 meaning none."""
    detect, g = _settings_io_ns()

    quota_file = tmp_path / "cpu.cfs_quota_us"
    period_file = tmp_path / "cpu.cfs_period_us"
    quota_file.write_text(quota, encoding="utf-8")
    period_file.write_text(period, encoding="utf-8")
    monkeypatch.setitem(g, "CGROUP_V2_CPU_MAX", tmp_path / "absent-cpu.max")
    monkeypatch.setitem(g, "CGROUP_V1_CPU_QUOTA", quota_file)
    monkeypatch.setitem(g, "CGROUP_V1_CPU_PERIOD", period_file)

    assert detect() == expected


def test_detect_cpu_quota_absent_everywhere(tmp_path, monkeypatch):
    """
    Off Linux, or outside a container, the answer is None - never 1.

    A 1 here would silently serialise every workflow on a developer's laptop
    and look like a performance problem rather than a configuration one.
    """
    detect, g = _settings_io_ns()

    monkeypatch.setitem(g, "CGROUP_V2_CPU_MAX", tmp_path / "no-cpu.max")
    monkeypatch.setitem(g, "CGROUP_V1_CPU_QUOTA", tmp_path / "no-quota")
    monkeypatch.setitem(g, "CGROUP_V1_CPU_PERIOD", tmp_path / "no-period")

    assert detect() is None
